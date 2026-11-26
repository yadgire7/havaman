"""Fixed-rule alerts for the next 24 hours, per taluka and per district.

Every rule and limit lives in config.yaml (alerts:). No forecast is judged by
anything but these comparisons.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from havaman import sky

KINDS = ("storm", "heavy_rain", "rain", "heat", "wind")   # most serious first


@dataclass
class Alert:
    kind: str
    value: float        # the number that crossed the limit (%, mm, °C, km/h)
    at: dt.datetime     # when (the hour, or the start of the day)


def now_index(hourly: dict, now: dt.datetime) -> int:
    """The forecast hour that contains `now` (0 if the clock does not match)."""
    stamp = now.strftime("%Y-%m-%dT%H:00")
    times = hourly.get("time") or []
    return times.index(stamp) if stamp in times else 0


def _peak(values, times, start, hours):
    best = None
    for i in range(start, min(start + hours, len(values))):
        v = values[i]
        if v is not None and (best is None or v > best[0]):
            best = (v, dt.datetime.fromisoformat(times[i]))
    return best


def for_taluka(forecast: dict | None, now: dt.datetime, limits: dict) -> list[Alert]:
    if not forecast:
        return []
    h, d = forecast["hourly"], forecast["daily"]
    start, hours = now_index(h, now), int(limits["window_hours"])
    times = h["time"]
    out = []
    storms = [i for i in range(start, min(start + hours, len(times)))
              if h["weather_code"][i] in sky.STORM]
    if storms:
        out.append(Alert("storm", h["weather_code"][storms[0]], dt.datetime.fromisoformat(times[storms[0]])))
    for i in range(min(2, len(d["time"]))):          # today and tomorrow
        rain = d["precipitation_sum"][i]
        if rain is not None and rain >= limits["heavy_rain_mm"]:
            out.append(Alert("heavy_rain", rain, dt.datetime.fromisoformat(d["time"][i])))
            break
    for kind, series, limit in (("rain", "precipitation_probability", "rain_chance"),
                                ("heat", "temperature_2m", "heat_c"),
                                ("wind", "wind_gusts_10m", "wind_gust_kmh")):
        peak = _peak(h[series], times, start, hours)
        if peak and peak[0] >= limits[limit]:
            out.append(Alert(kind, peak[0], peak[1]))
    return sorted(out, key=lambda a: KINDS.index(a.kind))


def by_district(alerts: dict[str, list[Alert]], talukas) -> dict[str, dict[str, list[str]]]:
    """district slug -> alert kind -> taluka slugs, for districts with any alert."""
    out: dict[str, dict[str, list[str]]] = {}
    for t in talukas:
        for a in alerts.get(t.key, []):
            out.setdefault(t.district, {}).setdefault(a.kind, []).append(t.slug)
    return out
