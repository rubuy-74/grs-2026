import time
import logging
import docker
from . import docker_client
from . import cloudflare_api
from . import config as config_module
from .labels import parse_tunnel_labels, LabelError

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

NETWORK_NAME = "wormhole-public"

class WormholeDaemon:
    def __init__(self):
        self.cfg = config_module.load_config()
        self.cf = cloudflare_api.create_client(self.cfg.api_token)
        self.zone_id = cloudflare_api.get_zone_id(self.cf, self.cfg.domain_name)
        self.client = docker.from_env()

    def run(self, interval: int = 30):
        logger.info(f"Starting Wormhole Daemon. Polling network: {NETWORK_NAME} every {interval}s")
        
        # Ensure the network exists
        docker_client.create_network(NETWORK_NAME)

        while True:
            try:
                self.reconcile()
            except Exception as e:
                logger.error(f"Error during reconciliation: {e}")
            
            time.sleep(interval)

    def reconcile(self):
        # 1. Get current state
        target_containers = docker_client.get_containers_on_network(NETWORK_NAME)
        managed_containers = docker_client.get_managed_cloudflared_containers()

        # 2. Identify desired tunnels
        desired_tunnels = {}
        for container in target_containers:
            try:
                # Reload container to get latest attributes
                container.reload()
                labels = parse_tunnel_labels(container.labels)
                
                # Determine target port
                target_port = labels.port
                if not target_port:
                    # If not specified, try to find an exposed port
                    ports = container.attrs.get('Config', {}).get('ExposedPorts', {})
                    if ports:
                        # Just take the first one
                        target_port = list(ports.keys())[0].split('/')[0]
                    else:
                        target_port = "80" # Fallback

                # Use a unique tunnel name per container ID to avoid name collisions in Cloudflare
                # if containers are renamed or replaced quickly.
                short_id = container.id[:12]
                tunnel_name = f"wormhole-{container.name}-{short_id}"
                desired_tunnels[container.id] = {
                    "tunnel_name": tunnel_name,
                    "container_name": container.name,
                    "container_id": container.id,
                    "labels": labels,
                    "target_port": target_port
                }
            except LabelError:
                continue # Skip containers without correct labels

        # 3. Identify running tunnels
        running_tunnels = {}
        for mc in managed_containers:
            owner_id = mc.labels.get("com.wormhole.owner_id")
            if owner_id:
                running_tunnels[owner_id] = mc

        # 4. Remove orphaned tunnels (running but not desired)
        for owner_id, mc in running_tunnels.items():
            if owner_id not in desired_tunnels:
                logger.info(f"Cleaning up orphaned tunnel for container ID {owner_id[:12]} ({mc.name})")
                docker_client.cleanup_container(mc.name)

        # 5. Create missing tunnels (desired but not running)
        for container_id, info in desired_tunnels.items():
            if container_id not in running_tunnels:
                self.create_tunnel_for_service(info["tunnel_name"], info)

    def create_tunnel_for_service(self, tunnel_name: str, info: dict):
        container_name = info["container_name"]
        labels = info["labels"]
        target_port = info["target_port"]
        
        logger.info(f"Creating tunnel for {container_name} ({labels.hostname})")

        try:
            tunnel_id = cloudflare_api.get_or_create_tunnel(self.cf, self.cfg.account_id, tunnel_name)
            token = cloudflare_api.get_tunnel_token(self.cf, self.cfg.account_id, tunnel_id)
            
            full_hostname = f"{labels.hostname}.{self.cfg.domain_name}"
            origin_url = f"{labels.protocol}://{container_name}:{target_port}"

            cloudflare_api.configure_tunnel(
                self.cf,
                self.cfg.account_id,
                tunnel_id,
                full_hostname,
                origin_url,
            )
            cloudflare_api.upsert_cname(self.cf, self.zone_id, full_hostname, tunnel_id)

            cloudflared_container_name = f"wormhole-cloudflared-{container_name}"
            docker_client.run_cloudflared_container(
                name=cloudflared_container_name,
                network=NETWORK_NAME,
                token=token,
                labels={
                    "com.wormhole.owner_id": info["container_id"],
                    "com.wormhole.owner_name": container_name
                }
            )
            logger.info(f"Tunnel created successfully: https://{full_hostname}")
        except Exception as e:
            logger.error(f"Failed to create tunnel for {container_name}: {e}")
