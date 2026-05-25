"""Cloudflare API helpers."""

from __future__ import annotations

import base64
import os

import CloudFlare


class CloudflareError(RuntimeError):
    pass


def create_client(api_token: str) -> CloudFlare.CloudFlare:
    return CloudFlare.CloudFlare(token=api_token)


def get_zone_id(cf: CloudFlare.CloudFlare, domain_name: str) -> str:
    zones = cf.zones.get(params={"name": domain_name})
    if not zones:
        raise CloudflareError(f"Zone not found for domain: {domain_name}")
    return zones[0]["id"]


def _generate_tunnel_secret() -> str:
    return base64.b64encode(os.urandom(32)).decode("ascii")


def get_or_create_tunnel(
    cf: CloudFlare.CloudFlare, account_id: str, tunnel_name: str
) -> str:
    tunnels = cf.accounts.cfd_tunnel.get(account_id)
    for tunnel in tunnels:
        if tunnel.get("name") == tunnel_name:
            return tunnel["id"]

    tunnel_secret = _generate_tunnel_secret()
    tunnel = cf.accounts.cfd_tunnel.post(
        account_id,
        data={
            "name": tunnel_name,
            "tunnel_secret": tunnel_secret,
        },
    )
    return tunnel["id"]


def get_tunnel_token(
    cf: CloudFlare.CloudFlare, account_id: str, tunnel_id: str
) -> str:
    return cf.accounts.cfd_tunnel.token.get(account_id, tunnel_id)


def configure_tunnel(
    cf: CloudFlare.CloudFlare,
    account_id: str,
    tunnel_id: str,
    hostname: str,
    origin_url: str,
) -> None:
    cf.accounts.cfd_tunnel.configurations.put(
        account_id,
        tunnel_id,
        data={
            "config": {
                "ingress": [
                    {"hostname": hostname, "service": origin_url},
                    {"service": "http_status:404"},
                ]
            }
        },
    )


def upsert_cname(
    cf: CloudFlare.CloudFlare,
    zone_id: str,
    hostname: str,
    tunnel_id: str,
) -> None:
    records = cf.zones.dns_records.get(
        zone_id,
        params={
            "type": "CNAME",
            "name": hostname,
        },
    )
    payload = {
        "type": "CNAME",
        "name": hostname,
        "content": f"{tunnel_id}.cfargotunnel.com",
        "ttl": 1,
        "proxied": True,
    }
    if records:
        cf.zones.dns_records.put(zone_id, records[0]["id"], data=payload)
    else:
        cf.zones.dns_records.post(zone_id, data=payload)
