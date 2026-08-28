"""Config router: per-user config CRUD + starter presets."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..db import get_db
from ..models import Config as ConfigModel
from ..models import User
from ..schemas import ConfigOut, ConfigUpdate
from ..scoring import config_from_dict

router = APIRouter(prefix="/config", tags=["config"])


def _get_or_create(db: Session, user: User) -> ConfigModel:
    row = db.query(ConfigModel).filter(ConfigModel.user_id == user.id).first()
    if row is None:
        row = ConfigModel(user_id=user.id, data="{}")
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


@router.get("", response_model=ConfigOut)
def get_config(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ConfigOut:
    row = _get_or_create(db, user)
    stored = json.loads(row.data or "{}")
    if stored:
        return ConfigOut(data=stored)

    # No stored config: fall back to the default config file (e.g. a saved GUI
    # profile) so the app highlights with the same colors/keywords as the web GUI.
    from ..settings import get_settings

    default_path = get_settings().default_config_path
    if default_path:
        path = Path(default_path).expanduser()
        if path.exists():
            with path.open("r", encoding="utf-8") as fh:
                return ConfigOut(data=json.load(fh))

    return ConfigOut(data={})


@router.put("", response_model=ConfigOut)
def put_config(
    body: ConfigUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConfigOut:
    row = _get_or_create(db, user)
    row.data = json.dumps(body.data, ensure_ascii=False)
    db.commit()
    db.refresh(row)
    return ConfigOut(data=json.loads(row.data))


@router.patch("", response_model=ConfigOut)
def patch_config(
    body: ConfigUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConfigOut:
    row = _get_or_create(db, user)
    current = json.loads(row.data or "{}")
    current.update(body.data)
    row.data = json.dumps(current, ensure_ascii=False)
    db.commit()
    db.refresh(row)
    return ConfigOut(data=json.loads(row.data))


@router.get("/presets", response_model=list[str])
def list_presets() -> list[str]:
    from arxiv_digest import preset_names

    return preset_names()


@router.post("/presets/{name}/merge", response_model=ConfigOut)
def merge_preset(
    name: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConfigOut:
    from arxiv_digest import merge_preset

    row = _get_or_create(db, user)
    cfg = config_from_dict(json.loads(row.data or "{}"))
    try:
        merged = merge_preset(cfg, name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown preset '{name}'") from exc
    row.data = json.dumps(_config_to_dict(merged), ensure_ascii=False)
    db.commit()
    db.refresh(row)
    return ConfigOut(data=json.loads(row.data))


def _config_to_dict(cfg) -> dict:
    from dataclasses import asdict

    return asdict(cfg)
