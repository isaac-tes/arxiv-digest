# Deploying the digest service

The iOS/Android apps are thin clients; the FastAPI **digest service** (`server/`)
holds the whole fetch/score/highlight engine. This is how to run it somewhere
always-on so the app works without your laptop.

## Two modes (`server/app/settings.py`)

| | `local` (default) | `remote` |
|---|---|---|
| Auth | **no-op** — a default user is auto-created; no login | JWT (OAuth2 password flow) |
| DB | SQLite file (`server/digest.db`) | Postgres (`DIGEST_DATABASE_URL`) |
| Use | personal / single-user, LAN or private network | public / multi-user |

Selected by `DIGEST_MODE`. Everything else has a working default, so
`uvicorn app.main:app` runs out of the box in `local` mode.

> **Never expose `local` mode to the public internet** — it has no auth by design.
> Fine on your home LAN or a private network (Tailscale). For public, use `remote`.

## Important: clone the whole repo, not just `server/`

The server imports the shared engine (`arxiv_digest.py`) from the **repo root** via
a `sys.path` insert (`REPO_ROOT` in `server/app/settings.py`). The `server/`
directory alone will not run — keep it nested inside a full checkout.

## Personal deploy on an always-on Linux box (local mode)

```bash
# 1. Install uv (Python package manager) if missing
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Clone the WHOLE repo
git clone <your-repo-url> arxiv_scraper_cli
cd arxiv_scraper_cli/server

# 3. Install deps into a project venv
uv sync

# 4. Run (local mode is the default)
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Verify from another machine on the network:

```bash
curl http://<box-ip>:8000/health     # -> {"status":"ok","mode":"local"}
```

### Keep it running across reboots/crashes — systemd

A template unit lives at [`deploy/arxiv-digest.service`](../deploy/arxiv-digest.service).
Fill in `<youruser>` and the checkout path, then:

```bash
sudo cp deploy/arxiv-digest.service /etc/systemd/system/arxiv-digest.service
# edit User=, WorkingDirectory=, ExecStart= paths to match your box
sudo systemctl daemon-reload
sudo systemctl enable --now arxiv-digest
systemctl status arxiv-digest
```

Update later:

```bash
cd ~/arxiv_scraper_cli && git pull && sudo systemctl restart arxiv-digest
```

## Reaching it from your phone — pick one

- **Same home Wi-Fi:** point the app's Settings → Server at `http://<box-lan-ip>:8000`.
  Open the port if a firewall is on: `sudo ufw allow 8000`.
- **From anywhere, private (recommended for personal use):** install
  [Tailscale](https://tailscale.com) on the box and the phone; point the app at the
  box's Tailscale IP, e.g. `http://100.x.y.z:8000`. No public exposure, no TLS, no
  port-forwarding.
- **From anywhere, public:** put a reverse proxy with automatic HTTPS in front
  (Caddy is ~2 lines for a domain) and port-forward 80/443. Only do this together
  with the `remote`-mode hardening below.

## Going public (`remote` mode) — checklist

```bash
export DIGEST_MODE=remote
export DIGEST_JWT_SECRET="$(openssl rand -hex 32)"     # never ship the default
export DIGEST_DATABASE_URL="postgresql+psycopg://user:pass@host/db"
# optionally lock CORS instead of the "*" default:
export DIGEST_CORS_ORIGINS='["https://yourapp.example"]'
```

- Change `jwt_secret` off `dev-secret-change-me` (above).
- Add a **caching layer** for arXiv fetches so N users don't trigger N scrapes —
  arXiv may throttle/block a server IP that scrapes aggressively. Treat this as a
  prerequisite, not a nice-to-have.
- Users register via `POST /auth/register` and log in via `POST /auth/token`; the
  app stores the bearer token (see `AuthStore` on the client).

## Optional: Zotero web-save

Set these in the environment (or the systemd unit) to enable "Save to Zotero"
(web mode) in the app:

```bash
export ZOTERO_API_KEY=...
export ZOTERO_LIBRARY_ID=...
```

Without them the app shows "Zotero saving not configured on the server" and every
other feature still works.

## Data / backups

`local` mode keeps everything in `server/digest.db` (your config, lists,
feedback). Back it up if that state matters. `remote` mode keeps it in Postgres.
