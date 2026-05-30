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

### Daemon Mode
Automatically manage tunnels for containers on the `wormhole-public` network.

```bash
docker compose -f docker-compose.daemon.yml up -d
```

#### Service Labels
- `com.wormhole.hostname=myapp` (required)
- `com.wormhole.protocol=http` (optional, default: http)
- `com.wormhole.port=8080` (optional, auto-detected if exposed)

### Verify
- Visit `CF_TUNNEL_HOSTNAME` and confirm it routes to `CF_ORIGIN_URL`.
- Check Zero Trust → Tunnels and confirm the tunnel is healthy.
