#!/usr/bin/env python3
"""Check whether the current API token can create/edit DNS records."""

from __future__ import annotations

import os
import sys
import uuid
from dataclasses import dataclass

import CloudFlare
from dotenv import load_dotenv


class CloudflareAPIError(RuntimeError):
    pass


@dataclass
class Config:
    api_token: str
    zone_id: str


def load_config() -> Config:
    load_dotenv()

    api_token = os.getenv("CF_API_TOKEN") or os.getenv("CLOUDFLARE_API_TOKEN")
    if not api_token:
        raise CloudflareAPIError(
            "Missing required environment variable: CF_API_TOKEN"
        )

    zone_id = os.getenv("CF_ZONE_ID")
    if not zone_id:
        raise CloudflareAPIError("Missing required environment variable: CF_ZONE_ID")

    return Config(api_token=api_token, zone_id=zone_id)


def create_client(config: Config) -> CloudFlare.CloudFlare:
    return CloudFlare.CloudFlare(token=config.api_token)


def get_zone_name(cf: CloudFlare.CloudFlare, zone_id: str) -> str:
    zone = cf.zones.get(zone_id)
    return zone["name"]


def main() -> int:
    try:
        config = load_config()
        cf = create_client(config)

        zone_name = get_zone_name(cf, config.zone_id)
        test_name = f"_cf_perm_check_{uuid.uuid4().hex}.{zone_name}"

        created_record = None
        try:
            created_record = cf.zones.dns_records.post(
                config.zone_id,
                data={
                    "type": "TXT",
                    "name": test_name,
                    "content": "cloudflare-permission-check",
                    "ttl": 120,
                },
            )

            cf.zones.dns_records.put(
                config.zone_id,
                created_record["id"],
                data={
                    "type": "TXT",
                    "name": test_name,
                    "content": "cloudflare-permission-check-updated",
                    "ttl": 120,
                },
            )

            print("OK: token can create and edit DNS records.")
            return 0
        finally:
            if created_record:
                cf.zones.dns_records.delete(
                    config.zone_id,
                    created_record["id"],
                )
    except (CloudflareAPIError, CloudFlare.exceptions.CloudFlareAPIError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
