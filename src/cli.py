"""Wormhole CLI."""

from __future__ import annotations

import signal
from pathlib import Path

import typer

from . import cloudflare_api
from . import config as config_module
from . import docker_client
from .labels import parse_tunnel_labels
from . import state

app = typer.Typer(no_args_is_help=True)


@app.command()
def create(
    docker_compose: Path = typer.Option(..., "--docker_compose", exists=True, file_okay=True),
    hostname: str | None = typer.Option(None, "--hostname"),
    port: str | None = typer.Option(None, "--port"),
    protocol: str | None = typer.Option(None, "--protocol"),
    name: str | None = typer.Option(None, "--name"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Create a Cloudflare tunnel for a Dockerfile."""
    cfg = config_module.load_config()

    build_result = docker_client.build_compose_services(docker_compose)

    base_tunnel_name = name or docker_compose.parent.name

    # Phase 1: Parse configuration and build deployment manifests
    services_to_deploy = []

    for service_name, result in build_result.items():
        labels = parse_tunnel_labels(result.labels)

        if not labels:
            typer.echo(f"Skipping service '{service_name}': No Wormhole labels specified.")
            continue

        # Use explicitly provided CLI port, or default to all ports found in the compose result
        if port:
            tunnel_ports = [port]
        else:
            tunnel_ports = list(result.ports.values()) if result.ports else []
        
        if not tunnel_ports:
            typer.echo(f"Skipping service '{service_name}': No port specified.")
            continue

        service_network = f"wormhole-{base_tunnel_name}-{service_name}"
        origin_container_name = f"wormhole-origin-{base_tunnel_name}-{service_name}"
        
        tunnels = []
        port_count = 0
        for tunnel_port in tunnel_ports:
            tunnel_name = f"{base_tunnel_name}-{service_name}{port_count if port_count != 0 else ''}"
            cloudflared_container_name = f"wormhole-cloudflared-{tunnel_name}"
            
            tunnel_protocol = protocol or labels.protocol or "http"
            origin_url = f"{tunnel_protocol}://{origin_container_name}:{tunnel_port}"
            
            tunnel_hostname = hostname or labels.hostname
            # Avoid hostname collisions on Cloudflare when a container exposes multiple ports
            if port_count > 0:
                full_hostname = f"{tunnel_hostname}-{tunnel_port}.{cfg.domain_name}"
            else:
                full_hostname = f"{tunnel_hostname}.{cfg.domain_name}"

            tunnels.append({
                "tunnel_name": tunnel_name,
                "cloudflared_container_name": cloudflared_container_name,
                "origin_url": origin_url,
                "full_hostname": full_hostname,
            })
            port_count += 1

        services_to_deploy.append({
            "service_name": service_name,
            "image_id": result.image_id,
            "network_name": service_network,
            "origin_container_name": origin_container_name,
            "tunnels": tunnels,
        })

    # TODO: add dry_run validation logic here if needed

    # Phase 2: Define tracking cleanup and signal safety handlers
    def cleanup() -> None:
        for s in services_to_deploy:
            for t in s["tunnels"]:
                docker_client.cleanup_container(t["cloudflared_container_name"])
            docker_client.cleanup_container(s["origin_container_name"])
            docker_client.remove_network(s["network_name"])

    def handle_signal(_signum: int, _frame: object) -> None:
        cleanup()
        raise typer.Exit(code=0)

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    # Phase 3: Execution and Infrastructure Provisioning
    cf = cloudflare_api.create_client(cfg.api_token)
    zone_id = cloudflare_api.get_zone_id(cf, cfg.domain_name)

    for s in services_to_deploy:
        # Create a unified backend network for this specific service
        docker_client.create_network(s["network_name"])
        
        # Spin up the core origin container application
        docker_client.run_origin_container(
            image_id=s["image_id"],
            name=s["origin_container_name"],
            network=s["network_name"],
        )

        # Provision unique Cloudflare Tunnels and sidecar cloudflared routing daemons per port
        for t in s["tunnels"]:
            tunnel_id = cloudflare_api.get_or_create_tunnel(cf, cfg.account_id, t["tunnel_name"])
            token = cloudflare_api.get_tunnel_token(cf, cfg.account_id, tunnel_id)
            state.write_token(token)

            cloudflare_api.configure_tunnel(
                cf,
                cfg.account_id,
                tunnel_id,
                t["full_hostname"],
                t["origin_url"],
            )
            cloudflare_api.upsert_cname(cf, zone_id, t["full_hostname"], tunnel_id)

            docker_client.run_cloudflared_container(
                name=t["cloudflared_container_name"],
                network=s["network_name"],
                token=token,
            )

            typer.echo(f"Tunnel ready. ID: {tunnel_id}. Public URL: https://{t['full_hostname']}")

    # Block processing and await interruption
    try:
        signal.pause()
    finally:
        cleanup()


@app.callback()
def main() -> None:
    """Wormhole: expose containers with Cloudflare Tunnels."""