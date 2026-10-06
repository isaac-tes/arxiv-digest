"""Config router: per-user config CRUD + starter presets.

Every response carries the *effective* config: the stored blob (or the default
config file, or built-in defaults) hydrated through `arxiv_digest.Config`, so
the app edits exactly the values the scorer uses, with every field present.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..db import get_db
from ..models import Config as ConfigModel
from ..models import User
from ..schemas import ConfigOut, ConfigUpdate, PresetInfo
from ..scoring import config_from_dict, load_user_config

router = APIRouter(prefix="/config", tags=["config"])


def _get_or_create(db: Session, user: User) -> ConfigModel:
    row = db.query(ConfigModel).filter(ConfigModel.user_id == user.id).first()
    if row is None:
        row = ConfigModel(user_id=user.id, data="{}")
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def _hydrate(data: dict[str, Any]) -> dict[str, Any]:
    """Validate a config blob and return it with every field filled in."""
    try:
        return asdict(config_from_dict(data))
    except (TypeError, ValueError, AttributeError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid config: {exc}") from exc


def _store(db: Session, user: User, data: dict[str, Any]) -> ConfigOut:
    row = _get_or_create(db, user)
    row.data = json.dumps(data, ensure_ascii=False)
    db.commit()
    return ConfigOut(data=data)


@router.get("", response_model=ConfigOut)
def get_config(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ConfigOut:
    return ConfigOut(data=asdict(load_user_config(db, user)))


@router.put("", response_model=ConfigOut)
def put_config(
    body: ConfigUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConfigOut:
    return _store(db, user, _hydrate(body.data))


@router.patch("", response_model=ConfigOut)
def patch_config(
    body: ConfigUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConfigOut:
    current = asdict(load_user_config(db, user))
    return _store(db, user, _hydrate({**current, **body.data}))


@router.get("/defaults", response_model=ConfigOut)
def get_defaults() -> ConfigOut:
    """Built-in defaults, for the app's per-section "Reset to defaults"."""
    from arxiv_digest import Config

    return ConfigOut(data=asdict(Config()))


@router.get("/presets", response_model=list[str])
def list_presets() -> list[str]:
    from arxiv_digest import preset_names

    return preset_names()


@router.get("/presets/info", response_model=list[PresetInfo])
def list_preset_info() -> list[PresetInfo]:
    from arxiv_digest import preset_description, preset_names

    return [PresetInfo(name=n, description=preset_description(n)) for n in preset_names()]


@router.post("/presets/{name}/merge", response_model=ConfigOut)
def merge_preset(
    name: str,
    body: ConfigUpdate | None = None,
    save: bool = True,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConfigOut:
    """GUI "Add preset": union the preset into a config.

    The base is `body.data` (the app's unsaved working config) when given, else
    the stored config. With `save=false` nothing is stored, matching the GUI,
    where Load/Add change only the working config until the user saves.
    """
    from arxiv_digest import merge_preset as ad_merge_preset

    base = config_from_dict(_hydrate(body.data)) if body is not None else load_user_config(db, user)
    try:
        merged = asdict(ad_merge_preset(base, name))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown preset '{name}'") from exc
    return _store(db, user, merged) if save else ConfigOut(data=merged)


@router.post("/presets/{name}/load", response_model=ConfigOut)
def load_preset(
    name: str,
    save: bool = True,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConfigOut:
    """GUI "Load preset": replace the config with the preset (defaults elsewhere).

    With `save=false` the preset config is returned without being stored.
    """
    from arxiv_digest import preset_config

    try:
        data = asdict(preset_config(name))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown preset '{name}'") from exc
    return _store(db, user, data) if save else ConfigOut(data=data)
