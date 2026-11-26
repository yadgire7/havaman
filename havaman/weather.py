"""Weather forecasts for every taluka, from Open-Meteo.

Open-Meteo needs no key and, unlike data.gov.in, answers GitHub's servers, so
this part runs on GitHub alone. One run asks for all talukas in batches,
checks every value, and saves one compact file. Nothing from the API is
trusted: each value must be a number in a plausible range (or a known
weather code), every series must match the hour list, and the location that
comes back must be the one asked for. Bad values become empty (None) and are
listed; a taluka with nothing usable is left out and listed.

Data: Open-Meteo.com, CC BY 4.0 (pages must credit and link it). The free API
is for non-commercial use, under 10,000 calls a day.
"""
from __future__ import annotations

import datetime as dt
import gzip
import json
import math
import os
import tempfile
import time
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path

from havaman.http import urllib_fetch

API = "https://api.open-meteo.com/v1/forecast"
VERSION = 1
RETRIES = 2
RATE_LIMIT_WAIT_S = 65   # Open-Meteo's per-minute limit resets after a minute
SECOND_TRY_WAIT_S = 30   # before retrying the batches that failed
MAX_GAP_DEG = 0.1   # Open-Meteo snaps to its grid; anything further is the wrong place

# Every variable we ask for, with the range a real value can have.
HOURLY = {
    "temperature_2m": (-10, 55),
    "apparent_temperature": (-20, 65),
    "relative_humidity_2m": (0, 100),
    "precipitation_probability": (0, 100),
    "precipitation": (0, 300),          # mm in one hour
    "weather_code": "wmo",
    "wind_speed_10m": (0, 250),         # km/h
    "wind_gusts_10m": (0, 300),
    "is_day": (0, 1),
}
DAILY = {
    "weather_code": "wmo",
    "temperature_2m_max": (-10, 55),
    "temperature_2m_min": (-10, 55),
    "precipitation_sum": (0, 1500),      # mm in one day
    "precipitation_probability_max": (0, 100),
    "uv_index_max": (0, 20),
    "sunrise": "time",
    "sunset": "time",
}
# WMO weather interpretation codes that Open-Meteo uses.
WMO_CODES = {0, 1, 2, 3, 45, 48, 51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 71, 73, 75, 77,
             80, 81, 82, 85, 86, 95, 96, 99}


class WeatherError(Exception):
    """Open-Meteo could not be used for this run. `retry` is False when Open-Meteo
    rejected the request itself (a 4xx other than 429): trying again cannot help."""

    def __init__(self, message: str, retry: bool = True):
        super().__init__(message)
        self.retry = retry


@dataclass
class Taluka:
    district: str
    slug: str
    name: str
    mr: str
    lat: float
    lon: float

    @property
    def key(self) -> str:
        return f"{self.district}/{self.slug}"


@dataclass
class Result:
    fetched_at: dt.datetime
    forecasts: dict[str, dict] = field(default_factory=dict)   # taluka key -> forecast
    problems: list[str] = field(default_factory=list)


def load_talukas(data: dict, district_slugs: set[str]) -> list[Taluka]:
    """The committed taluka list, checked: known districts, unique, inside Maharashtra."""
    rows = (data or {}).get("talukas")
    if not isinstance(rows, list) or not rows:
        raise ValueError("talukas file needs a non-empty 'talukas' list")
    out, seen, problems = [], set(), []
    for i, r in enumerate(rows):
        try:
            t = Taluka(str(r["district"]), str(r["slug"]), str(r["name"]), str(r["mr"]),
                       float(r["lat"]), float(r["lon"]))
        except (KeyError, TypeError, ValueError):
            problems.append(f"entry {i} is incomplete")
            continue
        if t.district not in district_slugs:
            problems.append(f"{t.name}: unknown district {t.district!r}")
        if not (15.5 < t.lat < 22.2 and 72.5 < t.lon < 81.0):
            problems.append(f"{t.name}: point {t.lat},{t.lon} is outside Maharashtra")
        if not t.slug or not all(c.isalnum() or c == "-" for c in t.slug) or not t.slug.isascii():
            problems.append(f"{t.name}: slug {t.slug!r} must be a-z, 0-9 and -")
        if t.key in seen:
            problems.append(f"{t.key} is listed twice")
        seen.add(t.key)
        out.append(t)
    if problems:
        raise ValueError("talukas file: " + "; ".join(problems[:10]))
    return out


def build_url(batch: list[Taluka], days: int) -> str:
    query = {
        "latitude": ",".join(f"{t.lat:.4f}" for t in batch),
        "longitude": ",".join(f"{t.lon:.4f}" for t in batch),
        "hourly": ",".join(HOURLY), "daily": ",".join(DAILY),
        "timezone": "Asia/Kolkata", "forecast_days": str(days),
    }
    return API + "?" + urllib.parse.urlencode(query, safe=",")


def get_json(url: str, fetch=urllib_fetch, sleep=time.sleep):
    problem, wait, retry = "no attempt made", 0, True
    for attempt in range(RETRIES + 1):
        if attempt:
            sleep(wait or 2 ** attempt)
            wait = 0
        try:
            status, body = fetch(url)
        except OSError as err:
            reason = getattr(err, "reason", None) or err
            problem = f"network error: {type(err).__name__}: {str(reason)[:200]}"
            continue
        if status == 200:
            try:
                return json.loads(body)
            except ValueError:
                problem = "HTTP 200 but the body was not JSON"
                continue
        problem = f"HTTP {status}: {body[:200].decode('utf-8', 'replace').strip()}"
        if status == 429:
            wait = RATE_LIMIT_WAIT_S   # "try again in one minute"
        elif 400 <= status < 500:
            retry = False
            break
    raise WeatherError(problem, retry)


def _number(value, rule):
    if rule == "time":
        try:
            dt.datetime.fromisoformat(str(value))
            return str(value)
        except ValueError:
            return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    if rule == "wmo":
        return int(value) if value == int(value) and int(value) in WMO_CODES else None
    lo, hi = rule
    return value if lo <= value <= hi else None


def check_location(t: Taluka, loc, days: int, now: dt.datetime) -> tuple[dict | None, list[str]]:
    """One location from the response, cleaned. None if nothing usable."""
    problems = []
    if not isinstance(loc, dict):
        return None, [f"{t.key}: not an object"]
    try:
        gap = max(abs(float(loc["latitude"]) - t.lat), abs(float(loc["longitude"]) - t.lon))
    except (KeyError, TypeError, ValueError):
        return None, [f"{t.key}: no location in the answer"]
    if gap > MAX_GAP_DEG:
        return None, [f"{t.key}: answer is for another place ({gap:.2f} degrees away)"]

    out = {"elevation": _number(loc.get("elevation"), (-100, 9000))}
    for part, spec, expected in (("hourly", HOURLY, days * 24), ("daily", DAILY, days)):
        block = loc.get(part)
        if not isinstance(block, dict) or not isinstance(block.get("time"), list):
            return None, [f"{t.key}: no {part} data"]
        times = [_number(x, "time") for x in block["time"]]
        if None in times or len(times) != expected:
            return None, [f"{t.key}: {part} times are missing or not {expected} long"]
        clean = {"time": times}
        for name, rule in spec.items():
            series = block.get(name)
            if not isinstance(series, list) or len(series) != len(times):
                problems.append(f"{t.key}: {part} {name} missing or wrong length")
                clean[name] = [None] * len(times)
                continue
            values = [_number(v, rule) for v in series]
            bad = sum(1 for v, raw in zip(values, series) if v is None and raw is not None)
            if bad:
                problems.append(f"{t.key}: {bad} {part} {name} values out of range, left empty")
            clean[name] = values
        out[part] = clean
    if all(v is None for v in out["hourly"]["temperature_2m"]):
        return None, problems + [f"{t.key}: no usable temperatures"]
    first = dt.datetime.fromisoformat(out["hourly"]["time"][0]).date()
    if abs((first - now.date()).days) > 1:
        return None, problems + [f"{t.key}: forecast starts on {first}, not today"]
    return out, problems


def fetch_all(talukas: list[Taluka], now: dt.datetime, days: int = 7, batch_size: int = 50,
              fetch=urllib_fetch, sleep=time.sleep, pause: float = 15.0) -> Result:
    """All talukas in batches, `pause` seconds apart: Open-Meteo allows 600 calls a
    minute, and each location with our 17 variables counts as about 1.7. Batches
    that fail (a timeout, an outage) get one more try at the end."""
    result = Result(now)
    batches = [talukas[i:i + batch_size] for i in range(0, len(talukas), batch_size)]
    failed: list[tuple[int, list[Taluka], str]] = []
    for round_ in (1, 2):
        todo = list(enumerate(batches)) if round_ == 1 else [(n, b) for n, b, _ in failed]
        if round_ == 2:
            if not todo:
                break
            failed = []
            sleep(SECOND_TRY_WAIT_S)
        for k, (n, batch) in enumerate(todo):
            label = f"talukas {n * batch_size + 1}-{n * batch_size + len(batch)}"
            try:
                data = get_json(build_url(batch, days), fetch, sleep)
            except WeatherError as err:
                if err.retry and round_ == 1:
                    failed.append((n, batch, f"{label}: {err}"))
                else:
                    result.problems.append(f"{label}: {err}"
                                           + (" (also on the second try)" if round_ == 2 else ""))
            else:
                if isinstance(data, dict) and len(batch) == 1:
                    data = [data]                      # one location comes back as an object
                if not isinstance(data, list) or len(data) != len(batch):
                    result.problems.append(f"{label}: answer does not have one forecast per taluka")
                else:
                    for t, loc in zip(batch, data):
                        forecast, problems = check_location(t, loc, days, now)
                        result.problems += problems
                        if forecast is not None:
                            result.forecasts[t.key] = forecast
            if k + 1 < len(todo):
                sleep(pause)
    return result


def save(path: Path, result: Result) -> None:
    data = {"version": VERSION, "source": "Open-Meteo.com (CC BY 4.0)",
            "fetched_at": result.fetched_at.isoformat(timespec="seconds"),
            "problems": result.problems[:200], "forecasts": result.forecasts}
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".weather-", suffix=".gz")
    with os.fdopen(fd, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as fh:
        fh.write(json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)


def load(path: Path) -> Result:
    with gzip.open(path, "rb") as fh:
        data = json.loads(fh.read(100_000_000))
    if not isinstance(data, dict) or data.get("version") != VERSION:
        raise ValueError(f"{path.name} is not a version {VERSION} weather file")
    return Result(dt.datetime.fromisoformat(data["fetched_at"]),
                  dict(data.get("forecasts") or {}), list(data.get("problems") or []))
