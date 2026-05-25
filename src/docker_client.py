"""Docker operations for Wormhole."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import docker


class DockerError(RuntimeError):
    pass


@dataclass(frozen=True)
class BuildResult:
    image_id: str
    labels: dict[str, str]


@dataclass(frozen=True)
class NetworkResources:
    network_name: str
    origin_container_name: str
    cloudflared_container_name: str


def build_image(dockerfile_path: Path) -> BuildResult:
    client = docker.from_env()
    dockerfile_path = dockerfile_path.resolve()
    if not dockerfile_path.exists():
        raise DockerError(f"Dockerfile not found: {dockerfile_path}")

    context_path = dockerfile_path.parent
    image, _ = client.images.build(
        path=str(context_path),
        dockerfile=str(dockerfile_path),
        rm=True,
    )

    labels = image.labels or {}
    return BuildResult(image_id=image.id, labels=labels)


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
    network.remove()


def run_origin_container(image_id: str, name: str, network: str) -> None:
    client = docker.from_env()
    try:
        existing = client.containers.get(name)
    except docker.errors.NotFound:
        existing = None
    if existing:
        existing.stop()
        existing.remove()
    client.containers.run(
        image=image_id,
        name=name,
        detach=True,
        network=network,
    )


def run_cloudflared_container(name: str, network: str, token: str) -> None:
    client = docker.from_env()
    client.images.pull("cloudflare/cloudflared:latest")
    try:
        existing = client.containers.get(name)
    except docker.errors.NotFound:
        existing = None
    if existing:
        existing.stop()
        existing.remove()
    client.containers.run(
        image="cloudflare/cloudflared:latest",
        name=name,
        detach=True,
        network=network,
        command=["tunnel", "--no-autoupdate", "run", "--token", token],
    )


def cleanup_container(name: str) -> None:
    client = docker.from_env()
    try:
        container = client.containers.get(name)
    except docker.errors.NotFound:
        return
    container.stop()
    container.remove()
