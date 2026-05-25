"""Configuration loading for Wormhole."""

from __future__ import annotations

from dataclasses import dataclass
import os

from dotenv import load_dotenv


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Config:
    api_token: str
    account_id: str
    domain_name: str


def load_config() -> Config:
    load_dotenv()

    api_token = os.getenv("CF_API_TOKEN") or os.getenv("CLOUDFLARE_API_TOKEN")
    if not api_token:
        raise ConfigError("Missing required environment variable: CF_API_TOKEN")

    account_id = os.getenv("CF_ACCOUNT_ID")
    if not account_id:
        raise ConfigError("Missing required environment variable: CF_ACCOUNT_ID")

    domain_name = os.getenv("CF_DOMAIN_NAME")
    if not domain_name:
        raise ConfigError("Missing required environment variable: CF_DOMAIN_NAME")

    return Config(
        api_token=api_token,
        account_id=account_id,
        domain_name=domain_name,
    )
