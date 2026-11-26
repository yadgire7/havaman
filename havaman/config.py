"""Load config.yaml and the taluka list, and refuse settings that cannot work."""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import yaml

IST = dt.timezone(dt.timedelta(hours=5, minutes=30), "IST")
TEXT_KEYS = (
    "site_title", "site_intro", "district_suffix", "all_districts", "talukas_count", "now",
    "feels_like", "high_low", "next_hours", "swipe_hint", "week", "today", "tomorrow", "weekdays",
    "alerts_title", "alert_storm", "alert_heavy_rain", "alert_rain", "alert_heat", "alert_wind",
    "no_alerts", "tile_rain", "tile_rain_note", "tile_humidity", "tile_wind", "tile_wind_note",
    "tile_uv", "uv_levels", "tile_sun", "unit_mm", "unit_kmh", "rain_chance_short",
    "district_alerts", "prices_link", "no_forecast", "updated", "point_note", "credit",
    "place_credit")
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
    pause = weather.get("pause_seconds")
    if not (isinstance(pause, (int, float)) and 0 <= pause <= 60):
        problems.append("weather.pause_seconds must be 0 to 60")
    if not (isinstance(every, int) and every >= 1 and 24 % every == 0):
        problems.append("weather.every_hours must divide 24")
    if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", str(weather.get("first_run_ist", ""))):
        problems.append("weather.first_run_ist must be HH:MM")
    if "talukas" in cfg:
        from havaman.weather import load_talukas
        try:
            load_talukas(cfg["talukas"], set(slugs))
        except ValueError as err:
            problems.append(str(err))

    limits = cfg.get("alerts") or {}
    for key in ("window_hours", "rain_chance", "heavy_rain_mm", "heat_c", "wind_gust_kmh"):
        value = limits.get(key)
        if not (isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0):
            problems.append(f"alerts.{key} must be a positive number")
    parts = cfg.get("day_parts_mr") or []
    hours = [p.get("from") for p in parts if isinstance(p, dict)]
    if (not parts or len(hours) != len(parts) or hours[0] != 0 or hours != sorted(set(hours))
            or not all(isinstance(h, int) and 0 <= h <= 23 for h in hours)
            or not all(p.get("mr") for p in parts)):
        problems.append("day_parts_mr must start at hour 0, with increasing hours and Marathi words")
    text = cfg.get("text_mr") or {}
    problems += [f"text_mr.{k} is missing" for k in TEXT_KEYS if k not in text]
    if len(text.get("weekdays") or []) != 7:
        problems.append("text_mr.weekdays needs 7 names, Monday first")
    if len(text.get("uv_levels") or []) != 5:
        problems.append("text_mr.uv_levels needs 5 words")

    if problems:
        raise ConfigError("config.yaml: " + "; ".join(problems))
