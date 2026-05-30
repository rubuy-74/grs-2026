"""Docker operations for Wormhole."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import yaml
import typer
import docker


class DockerError(RuntimeError):
    pass

@dataclass(frozen=True)
class NetworkResources:
    network_name: str
    origin_container_name: str
    cloudflared_container_name: str

@dataclass(frozen=True)
class ServiceBuildResult:
    service_name: str
    image_id: str
    labels: dict[str, object]
    ports: dict[int, int]
    environment: dict[str, str]


def build_compose_services(compose_path: Path) -> dict[str, ServiceBuildResult]:
    client = docker.from_env()
    compose_path = compose_path.resolve()
    if not compose_path.exists():
        raise DockerError(f"Compose file not found: {compose_path}")

    with open(compose_path, "r") as f:
        compose_data = yaml.safe_load(f)

    services = compose_data.get("services", {})
    res = {}
    compose_dir = compose_path.parent

    for service_name, service_config in services.items():
        build_cfg = service_config["build"]
        context_path = compose_dir / build_cfg
        dockerfile_name = "Dockerfile"

        dockerfile_path = context_path / dockerfile_name

        if not dockerfile_path.exists():
            print(f"Warning: Dockerfile not found for {service_name} at {dockerfile_path}")
            continue

        image, _ = client.images.build(
                path=str(context_path.resolve()),
                dockerfile=str(dockerfile_path.resolve()),
                rm=True,
            )
        
        labels_dict = {}
        compose_labels = service_config.get("labels", {})
        if isinstance(compose_labels, list):
            for label in compose_labels:
                if "=" in label:
                    k, v = label.split("=", 1)
                    labels_dict[k.strip()] = v.strip()
        elif isinstance(compose_labels, dict):
            labels_dict = compose_labels
        
        # Remove non wormhole labels
        labels_dict = {
            k: v
            for k, v in labels_dict.items()
                if k.startswith("com.wormhole.")
        }

        ports_dict = {}
        compose_ports = service_config.get("ports", [])


        if isinstance(compose_ports, list):
            for port in compose_ports:
                if isinstance(port, str) and ":" in port:
                    parts = port.split(":")
                    try:
                        host_port = int(parts[-2])
                        container_port = int(parts[-1].split("/")[0])
                        ports_dict[host_port] = container_port
                    except ValueError:
                        print(f"Warning: Could not parse port mapping '{port}' into integers.")
        elif isinstance(compose_ports, dict):
            for k, v in compose_ports.items():
                ports_dict[int(k)] = int(v)

        compose_env = service_config.get("environment", {})
        env_dict = {}
        if isinstance(compose_env, list):
            for env in compose_env:
                if "=" in env:
                    k, v = env.split("=", 1)
                    env_dict[k.strip()] = v.strip()
        elif isinstance(compose_env, dict):
            for k, v in compose_env.items():
                env_dict[k] = "" if v is None else str(v)

        res[service_name] = ServiceBuildResult(
            service_name=service_name,
            image_id=image.id,
            labels=labels_dict,
            ports=ports_dict,
            environment=env_dict,
        )



    return res

def create_network(name: str) -> None:
    client = docker.from_env()
    try:
        client.networks.get(name)
    except docker.errors.NotFound:
        client.networks.create(name, driver="bridge")


def remove_network(name: str) -> None:
    client = docker.from_env()
    try:
        network = client.networks.get(name)
    except docker.errors.NotFound:
        return
    network.reload()
    if network.containers:
        for container in network.containers:
            try:
                network.disconnect(container, force=True)
            except docker.errors.APIError:
                pass

    try:
        network.remove()
    except docker.errors.APIError as e:
        if "has active endpoints" in str(e):
            typer.echo("Found orphaned endpoints. Attempting forceful disconnection...")
            
            # Extract container/endpoint names from the error message or forcefully disconnect manually
            net_inspect = client.api.inspect_network(network.id)
            containers_in_net = net_inspect.get("Containers", {})
            
            for container_id in containers_in_net.keys():
                try:
                    client.api.disconnect_network_from_container(network.id, container_id, force=True)
                except docker.errors.APIError:
                    pass
                    
            # Retry the removal
            network.remove()
        else:
            raise e


def run_origin_container(image_id: str, name: str, network: str, environment: dict[str, str] | None = None, 
                         ports: dict[int, int] | None = None) -> None:
    client = docker.from_env()
    try:
        existing = client.containers.get(name)
    except docker.errors.NotFound:
        existing = None
    if existing:
        existing.stop()
        existing.remove()

    run_kwargs = {}
    if environment:
        run_kwargs['environment'] = environment
    if ports:
        ports_mapping = { f"{container_port}/tcp": host_port
                          for host_port, container_port in ports.items() }
        run_kwargs['ports'] = ports_mapping
    try:
        client.containers.run(
            image=image_id,
            name=name,
            detach=True,
            network=network,
            **run_kwargs,
        )
    except docker.errors.APIError as e:
        # Surface a clearer error for common failures (eg. port already in use)
        explanation = getattr(e, "explanation", None) or str(e)
        raise DockerError(f"Failed to start container {name}: {explanation}")
    except docker.errors.DockerException as e:
        # Generic Docker client errors
        raise DockerError(f"Docker error while starting container {name}: {e}")


def run_cloudflared_container(name: str, network: str, token: str) -> None:
    client = docker.from_env()
    try:
        client.images.pull("cloudflare/cloudflared:latest")
    except docker.errors.DockerException as e:
        # Common cause: docker credential helper misconfigured in WSL/remote env.
        raise DockerError(
            "Failed to pull 'cloudflare/cloudflared:latest'. "
            "You can try running 'docker pull cloudflare/cloudflared:latest' manually or fix your Docker credentials/config (~/.docker/config.json). "
            f"Original error: {e}"
        )

    try:
        existing = client.containers.get(name)
    except docker.errors.NotFound:
        existing = None
    if existing:
        existing.stop()
        existing.remove()
    try:
        client.containers.run(
            image="cloudflare/cloudflared:latest",
            name=name,
            detach=True,
            network=network,
            command=["tunnel", "--no-autoupdate", "run", "--token", token],
        )
    except docker.errors.APIError as e:
        explanation = getattr(e, "explanation", None) or str(e)
        raise DockerError(f"Failed to start cloudflared container {name}: {explanation}")


def cleanup_container(container_name):
    try:
        client = docker.from_env()
        container = client.containers.get(container_name)
        container.stop()
        container.remove(force=True)
    except docker.errors.NotFound:
        pass