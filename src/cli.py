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

    if dry_run:
        cf = cloudflare_api.create_client(cfg.api_token)
        cloudflare_api.get_zone_id(cf, cfg.domain_name)
        typer.echo("Cloudflare API & Zone validation: OK")

    base_tunnel_name = name or docker_compose.parent.name

    for service_name, result in build_result.items():
        labels = parse_tunnel_labels(result.labels)

        if not labels:
            typer.echo(f"Skipping service '{service_name}': No Wormhole labels specified.")
            continue

        tunnel_hostname = hostname or (labels.hostname if labels else None)
        tunnel_ports = result.ports.values or []
        tunnel_protocol = protocol or (labels.protocol if labels else "http")
        

    tunnel_name = name or docker_compose.parent.name or Path.cwd().name
    tunnel_hostname = hostname or labels.hostname
    tunnel_port = port or labels.port
    tunnel_protocol = protocol or labels.protocol

    origin_container_name = f"wormhole-origin-{tunnel_name}"
    origin_url = f"{tunnel_protocol}://{origin_container_name}:{tunnel_port}"
    full_hostname = f"{tunnel_hostname}.{cfg.domain_name}"

    if dry_run:
        cf = cloudflare_api.create_client(cfg.api_token)
        cloudflare_api.get_zone_id(cf, cfg.domain_name)
        typer.echo("Dry run OK")
        raise typer.Exit(code=0)

    network_name = f"wormhole-{tunnel_name}"
    cloudflared_container_name = f"wormhole-cloudflared-{tunnel_name}"

    def cleanup() -> None:
        docker_client.cleanup_container(cloudflared_container_name)
        docker_client.cleanup_container(origin_container_name)
        docker_client.remove_network(network_name)

    def handle_signal(_signum: int, _frame: object) -> None:
        cleanup()
        raise typer.Exit(code=0)

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    docker_client.create_network(network_name)
    docker_client.run_origin_container(
        image_id=build_result.image_id,
        name=origin_container_name,
        network=network_name,
    )

    cf = cloudflare_api.create_client(cfg.api_token)
    zone_id = cloudflare_api.get_zone_id(cf, cfg.domain_name)
    tunnel_id = cloudflare_api.get_or_create_tunnel(cf, cfg.account_id, tunnel_name)
    token = cloudflare_api.get_tunnel_token(cf, cfg.account_id, tunnel_id)
    state.write_token(token)

    cloudflare_api.configure_tunnel(
        cf,
        cfg.account_id,
        tunnel_id,
        full_hostname,
        origin_url,
    )
    cloudflare_api.upsert_cname(cf, zone_id, full_hostname, tunnel_id)

    docker_client.run_cloudflared_container(
        name=cloudflared_container_name,
        network=network_name,
        token=token,
    )

    typer.echo(f"Tunnel ready. ID: {tunnel_id}. Public URL: https://{full_hostname}")

    try:
        signal.pause()
    finally:
        cleanup()


@app.callback()
def main() -> None:
    """Wormhole: expose containers with Cloudflare Tunnels."""
