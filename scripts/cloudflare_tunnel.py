#!/usr/bin/env python3
"""Create or update a Cloudflare Tunnel using the Cloudflare SDK."""

from __future__ import annotations

import base64
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import CloudFlare
from dotenv import load_dotenv


class CloudflareAPIError(RuntimeError):
    pass


@dataclass
class Config:
    api_token: str
    account_id: str
    zone_id: str
    tunnel_name: str
    tunnel_hostname: str
    origin_url: str
    credentials_path: Path


def load_config() -> Config:
    load_dotenv()

    def require_env(name: str) -> str:
        value = os.getenv(name)
        if not value:
            raise CloudflareAPIError(f"Missing required environment variable: {name}")
        return value

    api_token = os.getenv("CF_API_TOKEN") or os.getenv("CLOUDFLARE_API_TOKEN")
    if not api_token:
        raise CloudflareAPIError(
            "Missing required environment variable: CF_API_TOKEN"
        )

    credentials_path = Path(
        os.getenv("CF_TUNNEL_CREDENTIALS_PATH", "./tunnel-credentials.json")
    ).expanduser()

    return Config(
        api_token=api_token,
        account_id=require_env("CF_ACCOUNT_ID"),
        zone_id=require_env("CF_ZONE_ID"),
        tunnel_name=require_env("CF_TUNNEL_NAME"),
        tunnel_hostname=require_env("CF_TUNNEL_HOSTNAME"),
        origin_url=require_env("CF_ORIGIN_URL"),
        credentials_path=credentials_path,
    )


def create_client(config: Config) -> CloudFlare.CloudFlare:
    return CloudFlare.CloudFlare(token=config.api_token)


def list_tunnels(
    cf: CloudFlare.CloudFlare, config: Config
) -> list[dict[str, Any]]:
    return cf.accounts.cfd_tunnel.get(config.account_id)


def find_tunnel(tunnels: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    for tunnel in tunnels:
        if tunnel.get("name") == name:
            return tunnel
    return None


def generate_tunnel_secret() -> str:
    return base64.b64encode(os.urandom(32)).decode("ascii")


def create_tunnel(
    cf: CloudFlare.CloudFlare, config: Config, tunnel_secret: str
) -> dict[str, Any]:
    return cf.accounts.cfd_tunnel.post(
        config.account_id,
        data={
            "name": config.tunnel_name,
            "tunnel_secret": tunnel_secret,
        },
    )


def ensure_tunnel(
    cf: CloudFlare.CloudFlare, config: Config
) -> tuple[dict[str, Any], str | None]:
    tunnels = list_tunnels(cf, config)
    tunnel = find_tunnel(tunnels, config.tunnel_name)
    if tunnel:
        return tunnel, None
    tunnel_secret = generate_tunnel_secret()
    return create_tunnel(cf, config, tunnel_secret), tunnel_secret


def get_tunnel_token(
    cf: CloudFlare.CloudFlare, config: Config, tunnel_id: str
) -> str:
    return cf.accounts.cfd_tunnel.token.get(config.account_id, tunnel_id)


def write_credentials_file(
    credentials_path: Path,
    tunnel_id: str,
    account_id: str,
    tunnel_secret: str,
) -> None:
    credentials_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "AccountTag": account_id,
        "TunnelSecret": tunnel_secret,
        "TunnelID": tunnel_id,
    }
    credentials_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_token_file(tunnel_id: str, token: str) -> Path:
    token_path = Path("./cloudflared/token.txt")
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(token + "\n", encoding="utf-8")
    return token_path


def update_tunnel_config(
    cf: CloudFlare.CloudFlare,
    config: Config,
    tunnel_id: str,
) -> dict[str, Any]:
    return cf.accounts.cfd_tunnel.configurations.put(
        config.account_id,
        tunnel_id,
        data={
            "config": {
                "ingress": [
                    {
                        "hostname": config.tunnel_hostname,
                        "service": config.origin_url,
                    },
                    {
                        "service": "http_status:404",
                    },
                ],
            }
        },
    )


def create_dns_record(
    cf: CloudFlare.CloudFlare,
    config: Config,
    tunnel_id: str,
) -> dict[str, Any]:
    return cf.zones.dns_records.post(
        config.zone_id,
        data={
            "type": "CNAME",
            "name": config.tunnel_hostname,
            "content": f"{tunnel_id}.cfargotunnel.com",
            "ttl": 1,
            "proxied": True,
        },
    )


def ensure_dns_record(
    cf: CloudFlare.CloudFlare,
    config: Config,
) -> dict[str, Any] | None:
    results = cf.zones.dns_records.get(
        config.zone_id,
        params={
            "type": "CNAME",
            "name": config.tunnel_hostname,
        },
    )
    if results:
        return results[0]
    return None


def create_or_update_dns_record(
    cf: CloudFlare.CloudFlare,
    config: Config,
    tunnel_id: str,
) -> dict[str, Any]:
    existing = ensure_dns_record(cf, config)
    if not existing:
        return create_dns_record(cf, config, tunnel_id)

    return cf.zones.dns_records.put(
        config.zone_id,
        existing["id"],
        data={
            "type": "CNAME",
            "name": config.tunnel_hostname,
            "content": f"{tunnel_id}.cfargotunnel.com",
            "ttl": 1,
            "proxied": True,
        },
    )


def write_cloudflared_config(config: Config, tunnel_id: str) -> Path:
    config_path = Path("./cloudflared/config.yml")
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_contents = (
        "tunnel: "
        + tunnel_id
        + "\n"
        + "credentials-file: "
        + str(config.credentials_path)
        + "\n"
        + "ingress:\n"
        + "  - hostname: "
        + config.tunnel_hostname
        + "\n"
        + "    service: "
        + config.origin_url
        + "\n"
        + "  - service: http_status:404\n"
    )
    config_path.write_text(config_contents, encoding="utf-8")
    return config_path


def main() -> int:
    try:
        config = load_config()
        cf = create_client(config)

        tunnel, tunnel_secret = ensure_tunnel(cf, config)
        tunnel_id = tunnel["id"]

        credentials_ready = config.credentials_path.exists()
        if tunnel_secret:
            write_credentials_file(
                config.credentials_path,
                tunnel_id,
                config.account_id,
                tunnel_secret,
            )
            credentials_ready = True

        update_tunnel_config(cf, config, tunnel_id)
        create_or_update_dns_record(cf, config, tunnel_id)

        config_path = None
        token_path = None
        if credentials_ready:
            config_path = write_cloudflared_config(config, tunnel_id)
        else:
            token = get_tunnel_token(cf, config, tunnel_id)
            token_path = write_token_file(tunnel_id, token)

        print("Tunnel configured successfully.")
        print(f"Tunnel ID: {tunnel_id}")
        if config_path:
            print(f"Credentials file: {config.credentials_path}")
            print(f"cloudflared config: {config_path}")
            print("Next step: run cloudflared with the generated config.")
        elif token_path:
            print(f"Tunnel token file: {token_path}")
            print(
                "Next step: run cloudflared with the tunnel token (remote config)."
            )
        return 0
    except (CloudflareAPIError, CloudFlare.exceptions.CloudFlareAPIError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
