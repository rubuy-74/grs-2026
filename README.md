# grs-2026

## Cloudflare Tunnel setup

### Prerequisites
- Create a Cloudflare API token with:
  - Account: Cloudflare Tunnel:Edit (and Read)
  - Zone: DNS:Edit (and Read)
- Capture your Account ID and Zone ID from the Cloudflare dashboard.

### Configure environment
1. Copy `.env.example` to `.env` and fill in the values.
2. Keep `.env` and `tunnel-credentials.json` out of git.

### Install dependencies
```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

This uses the official Cloudflare Python SDK (`cloudflare`).

### Run the tunnel setup script
```bash
python scripts/cloudflare_tunnel.py
```

### Run cloudflared
Install `cloudflared` on the origin host.

If this project created `cloudflared/config.yml` and `tunnel-credentials.json`, run:
```bash
cloudflared tunnel --config ./cloudflared/config.yml run
```

If the script created `cloudflared/token.txt` instead, run:
```bash
cloudflared tunnel --token "$(cat ./cloudflared/token.txt)" run
```

### Verify
- Visit `CF_TUNNEL_HOSTNAME` and confirm it routes to `CF_ORIGIN_URL`.
- Check Zero Trust → Tunnels and confirm the tunnel is healthy.
