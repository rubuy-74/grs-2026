"""Docker label handling for Wormhole."""

from __future__ import annotations

from dataclasses import dataclass


class LabelError(RuntimeError):
    pass


@dataclass(frozen=True)
class TunnelLabels:
    hostname: str
    protocol: str
    port: str | None = None


def parse_tunnel_labels(labels: dict[str, str]) -> TunnelLabels:
    hostname = labels.get("com.wormhole.hostname", "").strip()
    protocol = labels.get("com.wormhole.protocol", "http").strip()
    port = labels.get("com.wormhole.port", "").strip()

    if not hostname:
        raise LabelError("Missing label: com.wormhole.hostname")
    
    return TunnelLabels(
        hostname=hostname, 
        protocol=protocol,
        port=port if port else None
    )
