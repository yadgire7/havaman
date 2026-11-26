"""Load config.yaml and the taluka list, and refuse settings that cannot work."""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import yaml

IST = dt.timezone(dt.timedelta(hours=5, minutes=30), "IST")
SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


class ConfigError(ValueError):
    pass


def load_config(path: Path | str) -> dict:
    path = Path(path)
    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
    weather = cfg.get("weather") if isinstance(cfg, dict) else None
    if isinstance(weather, dict) and weather.get("talukas_file"):
        talukas_path = (path.parent / weather["talukas_file"]).resolve()
        if talukas_path.parent != path.parent.resolve():
            raise ConfigError("weather.talukas_file must sit next to config.yaml")
        cfg["talukas"] = yaml.safe_load(talukas_path.read_text(encoding="utf-8")) or {}
    validate_config(cfg)
    return cfg


def validate_config(cfg) -> None:
    if not isinstance(cfg, dict):
        raise ConfigError("config must be a mapping")
    problems: list[str] = []

    site = cfg.get("site") or {}
    for key in ("base_url", "prices_url"):
        url = str(site.get(key) or "")
        if not re.fullmatch(r"https://[a-z0-9.-]+(/[a-z0-9._/-]*)?", url):
            problems.append(f"site.{key} must be a plain https:// address")

    districts = cfg.get("districts") or []
    slugs = [d.get("slug") for d in districts if isinstance(d, dict)]
    if not districts or len(slugs) != len(districts):
        problems.append("districts must be a non-empty list of mappings")
    if len(set(slugs)) != len(slugs):
        problems.append("district slugs must be unique")
    for d in districts:
        if not (isinstance(d, dict) and SLUG.match(str(d.get("slug"))) and d.get("name") and d.get("mr")):
            problems.append(f"district {d!r} needs a slug (a-z, 0-9, -), a name and a Marathi name")

    weather = cfg.get("weather") or {}
    days, batch, every = (weather.get(k) for k in ("forecast_days", "batch_size", "every_hours"))
    if not (isinstance(days, int) and 1 <= days <= 7):
        problems.append("weather.forecast_days must be 1 to 7 (more counts as extra API calls)")
    if not (isinstance(batch, int) and 1 <= batch <= 100):
        problems.append("weather.batch_size must be 1 to 100")
    if not (isinstance(every, int) and every >= 1 and 24 % every == 0):
        problems.append("weather.every_hours must divide 24")
    if "talukas" in cfg:
        from havaman.weather import load_talukas
        try:
            load_talukas(cfg["talukas"], set(slugs))
        except ValueError as err:
            problems.append(str(err))

    if problems:
        raise ConfigError("config.yaml: " + "; ".join(problems))
