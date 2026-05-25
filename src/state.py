"""Local state/artifacts for cloudflared."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CloudflaredPaths:
    config_path: Path
    token_path: Path


def write_token(token: str) -> CloudflaredPaths:
    base = Path("./cloudflared")
    base.mkdir(parents=True, exist_ok=True)
    token_path = base / "token.txt"
    token_path.write_text(token + "\n", encoding="utf-8")

    config_path = base / "config.yml"
    return CloudflaredPaths(config_path=config_path, token_path=token_path)


def write_config(tunnel_id: str, hostname: str, origin_url: str) -> CloudflaredPaths:
    base = Path("./cloudflared")
    base.mkdir(parents=True, exist_ok=True)
    config_path = base / "config.yml"
    config_contents = (
        f"tunnel: {tunnel_id}\n"
        f"credentials-file: ./cloudflared/{tunnel_id}.json\n"
        "ingress:\n"
        f"  - hostname: {hostname}\n"
        f"    service: {origin_url}\n"
        "  - service: http_status:404\n"
    )
    config_path.write_text(config_contents, encoding="utf-8")

    token_path = base / "token.txt"
    return CloudflaredPaths(config_path=config_path, token_path=token_path)
