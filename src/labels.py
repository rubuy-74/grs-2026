"""Docker label handling for Wormhole."""

from __future__ import annotations

from dataclasses import dataclass


class LabelError(RuntimeError):
    pass


@dataclass(frozen=True)
class TunnelLabels:
    hostname: str
    #port: str
    protocol: str


def parse_tunnel_labels(labels: dict[str, str]) -> TunnelLabels:
    hostname = labels.get("com.wormhole.hostname", "").strip()
    # TODO Check if port is really necessary since we parse the "ports" section in docker compose
    # port = labels.get("com.wormhole.port", "").strip()
    protocol = labels.get("com.wormhole.protocol", "").strip()

    if not hostname:
        raise LabelError("Missing label: com.wormhole.hostname")
    #if not port:
    #    raise LabelError("Missing label: com.wormhole.port")
    if not protocol:
        raise LabelError("Missing label: com.wormhole.protocol")

    return TunnelLabels(hostname=hostname, protocol=protocol)
