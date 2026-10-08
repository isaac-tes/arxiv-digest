"""Load a saved GUI profile JSON into the digest server's stored config.

The mobile app reads its config from the server (per-user, DB-backed). This
seeds the local user's config row from a profile file (e.g. one saved by the
Streamlit GUI under ~/.arxiv_scraper/profiles/), so the app scores and
highlights with exactly those preferences.

Usage (from server/):
    uv run python scripts/load_profile.py ~/.arxiv_scraper/profiles/topology-mode.json

Re-running overwrites the stored config with the file's contents.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Make the `app` package importable when run as a script from server/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.auth import hash_password  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402
from app.models import Config as ConfigModel  # noqa: E402
from app.models import User  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2

    path = Path(sys.argv[1]).expanduser()
    if not path.exists():
        print(f"error: profile not found: {path}", file=sys.stderr)
        return 1

    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)

    init_db()
    db = SessionLocal()
    try:
        # Same default-user resolution as local-mode auth.
        user = db.query(User).order_by(User.id).first()
        if user is None:
            user = User(email="local@digest.local", hashed_password=hash_password("local"))
            db.add(user)
            db.commit()
            db.refresh(user)

        row = db.query(ConfigModel).filter(ConfigModel.user_id == user.id).first()
        if row is None:
            row = ConfigModel(user_id=user.id, data="{}")
            db.add(row)
        row.data = json.dumps(data, ensure_ascii=False)
        db.commit()

        keywords = data.get("core_keywords", [])
        print(f"Loaded '{path.name}' into config for user {user.email}:")
        print(f"  {len(keywords)} keywords, top_n={data.get('top_n')}, "
              f"feeds={data.get('default_feeds')}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
