# grs-2026

## Cloudflare Tunnel setup

### Prerequisites
- Create a Cloudflare API token with:
  - Account: Cloudflare Tunnel:Edit (and Read)
  - Zone: DNS:Edit (and Read)
- Capture your Account ID and Zone ID from the Cloudflare dashboard.

### Configure environment
1. Copy `.env.example` to `.env` and fill in the values.
2. Keep `.env` out of git.

### Install dependencies
```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

This uses the official Cloudflare Python SDK (`cloudflare`).

### Run the Wormhole CLI
```bash
python -m wormhole create --docker_compose ./docker-compose.yml
```

### Run cloudflared
The CLI starts `cloudflared` in a Docker container on the same network.

### Verify
- Visit `CF_TUNNEL_HOSTNAME` and confirm it routes to `CF_ORIGIN_URL`.
- Check Zero Trust → Tunnels and confirm the tunnel is healthy.
