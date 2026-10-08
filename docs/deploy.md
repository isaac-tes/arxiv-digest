# Share settings across devices (digest server)

The iOS app has three connection modes (Settings → Connection):

| Mode | Where config + removed papers live | Synced? | Needs a server? |
|---|---|---|---|
| **On this device** (default) | on the phone | no | no |
| **Server** | on the digest server | **yes**: every device pointing at the same server shares them | yes |
| **Demo** | in memory (sample papers) | no | no |

To share keywords, authors, feeds, weights and removed papers between devices
(iPhone, iPad, a Mac), run the **digest server** (`server/`, a FastAPI app around
the same `arxiv_digest.py` engine as the CLI and GUI) somewhere all of them can
reach, and switch each device to **Server**.

!!! note "What does not sync yet"
    The web GUI (`arxiv-gui`) keeps its own `arxiv_config.json` / profiles and
    does not read the server's config. You can **seed** the server from a GUI
    profile once (step 3), but later edits don't flow back. **On this device**
    data also stays on the phone: switching to Server starts from the server's
    config.

---

## 1. Requirements

- Python 3.12+ and [uv](https://docs.astral.sh/uv/) (installs into your home
  directory, no root needed):
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```
- The **whole repository**, not just `server/`: the server imports the engine
  (`arxiv_digest.py`) from the repo root.
  ```bash
  git clone https://github.com/isaac-tes/arxiv-digest.git
  cd arxiv-digest
  git switch feat/swift_ios   # until the iOS work is merged into main
  ```

## 2. Start the server

```bash
cd server
uv sync
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Check it from the same machine:

```bash
curl http://127.0.0.1:8000/health      # {"status":"ok","mode":"local"}
```

- `--host 127.0.0.1` accepts connections from this machine only. To let other
  devices on your network in, use `--host 0.0.0.0` (see the warning in step 4).
- The first past-week load fetches from arXiv (~20–40 s); later loads come from
  the server's 1 h cache.
- Stop it with `Ctrl-C`. Your config and removed papers are kept in
  `server/digest.db` (SQLite), so restarting doesn't lose them.

## 3. Optional: start from your GUI settings

Point the server at a saved GUI profile; it is used as the config for a user who
has none stored yet:

```bash
DIGEST_DEFAULT_CONFIG_PATH=~/.arxiv_scraper/profiles/<name>.json \
  uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

This seeds the server once. Edits made later in the app are stored on the
server and don't change the profile file.

## 4. Make it reachable from your devices

Pick the first option that fits:

| Setup | Server command | URL to enter on each device |
|---|---|---|
| **Same Wi-Fi at home** (Mac or Linux box) | `--host 0.0.0.0` | `http://<server-LAN-IP>:8000` |
| **From anywhere, private**: [Tailscale](https://tailscale.com) on the server and every device | `--host 0.0.0.0` | `http://<server-tailscale-IP>:8000` |
| **Remote Linux machine, Mac only**: SSH tunnel | `--host 127.0.0.1` | on the Mac: `ssh -N -L 8000:127.0.0.1:8000 you@host`, then `http://127.0.0.1:8000` |

Find the LAN IP with `ipconfig getifaddr en0` (Mac) or `hostname -I` (Linux).
If a device can't connect, open `http://<url>/health` in its browser first;
firewalls and guest/eduroam networks that isolate devices are the usual cause.

!!! warning "The default server has no login"
    It runs in `local` mode: no authentication, one shared user. Expose it only
    on networks you trust (home Wi-Fi, Tailscale, an SSH tunnel), never directly
    on the public internet. See [Going public](#going-public-remote-mode).

## 5. Connect each device

**iPhone / iPad**: Settings → Connection → **Server** → enter the URL from
step 4 → **Connect**. The status line reads *Connected · local mode*. Allow
**Local Network** access when iOS asks (needed for LAN addresses).

**Mac**: on Apple-silicon Macs the iOS app also runs as a Mac app. In Xcode,
open `ios/ArxivDigest.xcodeproj`, choose the destination **My Mac (Designed for
iPad)**, run it, and connect it to the same URL. (Not yet tested on this
project; report problems.)

Now a keyword added on the phone, a removal on the Mac, or a preset loaded on
either is saved to the server and shows on the other device after its next load
(pull to refresh).

## 6. Keep it running

=== "Linux with sudo (systemd)"

    A template unit is in `deploy/arxiv-digest.service`. Fill in `<youruser>`
    and the checkout path, then:

    ```bash
    sudo cp deploy/arxiv-digest.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable --now arxiv-digest
    systemctl status arxiv-digest
    ```

    Without root but with user lingering enabled (`loginctl enable-linger $USER`,
    which some distributions allow without sudo), copy the unit to
    `~/.config/systemd/user/`, remove its `User=` line, and use
    `systemctl --user enable --now arxiv-digest`.

=== "Linux without root (tmux)"

    Check first that long-running processes are allowed on the machine.

    ```bash
    tmux new -s digest
    cd ~/arxiv-digest/server && uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
    # detach: Ctrl-b then d · reattach: tmux attach -t digest
    ```

    tmux sessions don't survive a reboot; start it again afterwards.

=== "Mac (while logged in)"

    Run the step 2 command in a Terminal window, or in a
    `tmux`/`screen` session. The Mac must be awake for other devices to sync.

**Updating**:
```bash
cd ~/arxiv-digest && git pull
cd server && uv sync
# then restart: Ctrl-C and rerun, or `sudo systemctl restart arxiv-digest`
```

## 7. Back up

Everything is in `server/digest.db`. Copy it while the server is stopped, e.g.
`cp server/digest.db ~/digest-backup-$(date +%F).db`.

---

## Reference

### Server settings (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `DIGEST_MODE` | `local` | `local`: no auth, SQLite. `remote`: JWT login, multi-user |
| `DIGEST_DATABASE_URL` | `sqlite:///./digest.db` | Database (Postgres for `remote`) |
| `DIGEST_DEFAULT_CONFIG_PATH` | – | GUI profile used for users without a stored config |
| `DIGEST_JWT_SECRET` | `dev-secret-change-me` | **Change** in `remote` mode |
| `DIGEST_CORS_ORIGINS` | `["*"]` | Allowed browser origins |
| `ZOTERO_API_KEY`, `ZOTERO_LIBRARY_ID` | – | Enable *Save to Zotero* from the app via the Zotero Web API |

Without the Zotero variables the app offers **Share to Zotero** (the iOS share
sheet hands the paper to the Zotero app), and everything else works.

### Going public (`remote` mode)

```bash
export DIGEST_MODE=remote
export DIGEST_JWT_SECRET="$(openssl rand -hex 32)"
export DIGEST_DATABASE_URL="postgresql+psycopg://user:pass@host/db"
export DIGEST_CORS_ORIGINS='["https://yourapp.example"]'
```

Users register with `POST /auth/register` and log in with `POST /auth/token`.
The iOS app has no login screen yet, so `remote` mode isn't usable from the
app today. Put HTTPS in front (e.g. Caddy) before exposing it, and expect arXiv
to rate-limit a busy shared server; the server caches fetches for an hour.
