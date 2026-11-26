"""The static Marathi weather site: an index, one page per district, one per taluka.

Same rules as the price pages: plain HTML and one stylesheet, no JavaScript,
no outside resources, a Content-Security-Policy that blocks them, and every
value HTML-escaped. Inline styles are blocked too, so the 7-day temperature
bars are drawn with CSS classes (a 20-column grid), not style attributes.
"""
from __future__ import annotations

import datetime as dt
import html
import json
import math
import shutil
from pathlib import Path

from havaman import alerts as alert_rules
from havaman import marathi as mr
from havaman import sky

MARKER = ".havaman-site"
CSP = ("default-src 'none'; style-src 'self'; img-src 'self'; base-uri 'none'; "
       "form-action 'none'")
OPEN_METEO = "https://open-meteo.com/"
OSM = "https://www.openstreetmap.org/copyright"
BAR_STEPS = 20
BADGE = {"storm": "⛈️", "heavy_rain": "🌧️", "rain": "☔", "heat": "🌡️", "wind": "💨"}

STYLE = """\
:root { color-scheme: dark; --ink: #fff; --muted: rgba(255,255,255,.78);
  --card: rgba(0,0,0,.22); --line: rgba(255,255,255,.22); }
* { box-sizing: border-box; }
body { margin: 0; font-family: system-ui, -apple-system, "Noto Sans Devanagari", sans-serif;
  font-size: 16px; line-height: 1.5; color: var(--ink); min-height: 100vh;
  background: linear-gradient(180deg, #1f5a9e, #3a76b8); background-attachment: fixed; }
body.sky-clear { background-image: linear-gradient(180deg, #1f5a9e, #3a76b8); }
body.sky-clear-night { background-image: linear-gradient(180deg, #0b1d3a, #22355c); }
body.sky-cloudy { background-image: linear-gradient(180deg, #3e4f63, #5e6e82); }
body.sky-fog { background-image: linear-gradient(180deg, #4a5560, #66717c); }
body.sky-rain { background-image: linear-gradient(180deg, #2b3d50, #485d70); }
body.sky-storm { background-image: linear-gradient(180deg, #24262f, #42465a); }
a { color: var(--ink); }
.wrap { max-width: 40rem; margin: 0 auto; padding: 1rem; }
nav { font-size: .95rem; color: var(--muted); }
nav a { color: var(--muted); }
.hero { text-align: center; padding: 1.25rem 0 1rem; }
.hero h1 { margin: .2rem 0 0; font-size: 1.9rem; font-weight: 600; }
.hero .sub { margin: 0; color: var(--muted); font-size: .95rem; }
.now-temp { font-size: 5rem; font-weight: 200; line-height: 1; margin: .5rem 0 .25rem; }
.now-sky { font-size: 1.2rem; margin: 0; }
.hilo, .feels { margin: .15rem 0 0; color: var(--muted); }
.card { background: var(--card); border-radius: 1rem; padding: .9rem 1rem; margin: 0 0 .9rem;
  backdrop-filter: blur(6px); }
.card h2 { margin: 0 0 .6rem; font-size: .9rem; font-weight: 600; color: var(--muted);
  border-bottom: 1px solid var(--line); padding-bottom: .45rem; }
.alerts ul { margin: 0; padding-left: 0; list-style: none; }
.alerts li { padding: .3rem 0; }
.alerts.none p { margin: 0; color: var(--muted); }
.hint { float: right; font-weight: 400; }
.hours { display: flex; gap: .25rem; overflow-x: auto; margin: 0; padding: 0 0 .4rem;
  list-style: none; scroll-snap-type: x mandatory; -webkit-overflow-scrolling: touch; }
.hours li { flex: 0 0 4.3rem; scroll-snap-align: start; text-align: center;
  display: flex; flex-direction: column; gap: .2rem; padding: .2rem 0; }
.h-time { font-size: .85rem; color: var(--muted); white-space: nowrap; }
.h-icon { font-size: 1.5rem; line-height: 1.6rem; }
.h-temp { font-size: 1.1rem; font-weight: 600; }
.h-rain { font-size: .8rem; color: #bfe3ff; min-height: 1.2em; }
.days { margin: 0; padding: 0; list-style: none; }
.days li { display: grid; grid-template-columns: 3.6rem 2rem 3.4rem 2.4rem 1fr 2.4rem;
  align-items: center; gap: .35rem; padding: .5rem 0; border-top: 1px solid var(--line); }
.days li:first-child { border-top: 0; }
.d-name { font-weight: 600; }
.d-icon { font-size: 1.4rem; text-align: center; }
.d-rain { font-size: .8rem; color: #bfe3ff; }
.d-min { color: var(--muted); text-align: right; }
.d-max { font-weight: 600; }
.d-bar { display: grid; grid-template-columns: repeat(20, 1fr); height: .4rem;
  background: rgba(255,255,255,.18); border-radius: .2rem; overflow: hidden; }
.range { grid-row: 1; border-radius: .2rem;
  background: linear-gradient(90deg, #8fd3ff, #ffd36b, #ff9a5a); }
.tiles { display: grid; grid-template-columns: 1fr 1fr; gap: .9rem; margin-bottom: .9rem; }
.tiles .card { margin: 0; }
.tiles h3 { margin: 0 0 .3rem; font-size: .85rem; font-weight: 600; color: var(--muted); }
.big { font-size: 1.6rem; margin: 0; }
.small { font-size: .85rem; color: var(--muted); margin: .2rem 0 0; }
.list { margin: 0; padding: 0; list-style: none; }
.list li { border-top: 1px solid var(--line); }
.list li:first-child { border-top: 0; }
.list a { display: grid; grid-template-columns: 2rem 1fr auto; gap: .6rem; align-items: center;
  padding: .7rem .1rem; text-decoration: none; min-height: 44px; }
.list .name { font-weight: 600; }
.list .en { display: block; font-size: .8rem; color: var(--muted); font-weight: 400; }
.list .temps { text-align: right; white-space: nowrap; }
.list .temps small { display: block; color: #bfe3ff; }
.badge { font-size: .8rem; background: rgba(255,170,60,.35); border-radius: .5rem;
  padding: 0 .4rem; margin-left: .3rem; white-space: nowrap; }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: .5rem; margin: 0; padding: 0;
  list-style: none; }
.grid a { display: block; background: var(--card); border-radius: .8rem; padding: .7rem .8rem;
  text-decoration: none; min-height: 44px; }
.grid small { display: block; color: var(--muted); }
footer { color: var(--muted); font-size: .85rem; padding: 1rem 0 2rem; }
footer p { margin: .3rem 0; }
footer a { color: var(--muted); }
@media (min-width: 40rem) { .grid { grid-template-columns: 1fr 1fr 1fr; }
  .tiles { grid-template-columns: 1fr 1fr 1fr; } }
""" + "".join(f".s{i} {{ grid-column-start: {i + 1}; }}\n" for i in range(BAR_STEPS)) \
    + "".join(f".e{i} {{ grid-column-end: {i + 1}; }}\n" for i in range(1, BAR_STEPS + 1))


def esc(value) -> str:
    return html.escape(str(value), quote=True)


def _page(title: str, body_class: str, depth: int, body: str, text: dict, updated: str) -> str:
    up = "../" * depth
    return (
        "<!DOCTYPE html>\n<html lang=\"mr\">\n<head>\n<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        f"<meta http-equiv=\"Content-Security-Policy\" content=\"{CSP}\">\n"
        "<meta name=\"referrer\" content=\"no-referrer\">\n"
        f"<title>{esc(title)}</title>\n<link rel=\"stylesheet\" href=\"{up}style.css\">\n"
        f"</head>\n<body class=\"{esc(body_class)}\">\n<div class=\"wrap\">\n{body}\n"
        "<footer>\n"
        f"<p>{esc(updated)}</p>\n<p>{esc(text['point_note'])}</p>\n"
        f"<p>{esc(text['credit'])}: <a href=\"{OPEN_METEO}\" rel=\"noopener\">Open-Meteo.com</a> "
        "(CC BY 4.0) · "
        f"{esc(text['place_credit'])}: <a href=\"{OSM}\" rel=\"noopener\">© OpenStreetMap</a></p>\n"
        "</footer>\n</div>\n</body>\n</html>\n")


def _hour(forecast: dict, i: int) -> dict:
    return {k: v[i] for k, v in forecast["hourly"].items()}


def _alert_line(a, text: dict, parts: list, today: dt.date) -> str:
    when = (mr.clock(a.at, parts, minutes=False) if a.kind in ("storm", "rain")
            else mr.day_name(a.at.date(), today, text))
    value = mr.whole(a.value) if a.kind != "heavy_rain" else mr.digits(f"{a.value:.0f}")
    return text[f"alert_{a.kind}"].format(when=when, value=value)


def _taluka_body(t, district: dict, forecast: dict | None, found: list, now: dt.datetime,
                 cfg: dict) -> tuple[str, str]:
    text, parts = cfg["text_mr"], cfg["day_parts_mr"]
    nav = (f"<nav><a href=\"../../\">{esc(text['all_districts'])}</a> › "
           f"<a href=\"../\">{esc(district['mr'])}</a></nav>")
    head = (f"<h1>{esc(t.mr)}</h1>\n<p class=\"sub\">{esc(t.name)} · {esc(district['mr'])} "
            f"{esc(text['district_suffix'])}</p>")
    prices = (f"<p><a href=\"{esc(cfg['site']['prices_url'].rstrip('/'))}/{esc(district['slug'])}/\">"
              f"{esc(text['prices_link'].format(district=district['mr']))}</a></p>")
    if not forecast:
        return (f"{nav}\n<header class=\"hero\">{head}</header>\n<section class=\"card\"><p>"
                f"{esc(text['no_forecast'])}</p></section>\n{prices}", "sky-cloudy")

    h, d = forecast["hourly"], forecast["daily"]
    start = alert_rules.now_index(h, now)
    cur = _hour(forecast, start)
    today = dt.date.fromisoformat(d["time"][0])
    hero = (f"<header class=\"hero\">{head}\n<p class=\"now-temp\">{mr.degrees(cur['temperature_2m'])}</p>\n"
            f"<p class=\"now-sky\">{sky.icon(cur['weather_code'], cur['is_day'])} "
            f"{esc(sky.label(cur['weather_code']))}</p>\n"
            f"<p class=\"hilo\">{esc(text['high_low'].format(max=mr.degrees(d['temperature_2m_max'][0]), min=mr.degrees(d['temperature_2m_min'][0])))}</p>\n"
            f"<p class=\"feels\">{esc(text['feels_like'].format(t=mr.degrees(cur['apparent_temperature'])))}</p>\n"
            "</header>")

    if found:
        items = "".join(f"<li>{esc(_alert_line(a, text, parts, today))}</li>\n" for a in found)
        warn = f"<section class=\"card alerts\"><h2>{esc(text['alerts_title'])}</h2>\n<ul>\n{items}</ul></section>"
    else:
        warn = f"<section class=\"card alerts none\"><p>{esc(text['no_alerts'])}</p></section>"

    hours = []
    for i in range(start, min(start + 24, len(h["time"]))):
        x = _hour(forecast, i)
        when = text["now"] if i == start else mr.clock(dt.datetime.fromisoformat(x["time"]), parts, minutes=False)
        p = x["precipitation_probability"]
        rain = text["rain_chance_short"].format(p=mr.whole(p)) if p is not None and p >= 10 else ""
        hours.append(f"<li><span class=\"h-time\">{esc(when)}</span>"
                     f"<span class=\"h-icon\">{sky.icon(x['weather_code'], x['is_day'])}</span>"
                     f"<span class=\"h-temp\">{mr.degrees(x['temperature_2m'])}</span>"
                     f"<span class=\"h-rain\">{esc(rain)}</span></li>\n")
    strip = (f"<section class=\"card\"><h2>{esc(text['next_hours'])} "
             f"<span class=\"hint\">{esc(text['swipe_hint'])}</span></h2>\n"
             f"<ol class=\"hours\">\n{''.join(hours)}</ol></section>")

    lows = [v for v in d["temperature_2m_min"] if v is not None]
    highs = [v for v in d["temperature_2m_max"] if v is not None]
    lo, hi = (min(lows), max(highs)) if lows and highs else (0, 1)
    span = max(hi - lo, 1)
    days = []
    for i, day in enumerate(d["time"]):
        tmin, tmax = d["temperature_2m_min"][i], d["temperature_2m_max"][i]
        if tmin is None or tmax is None:
            bar = ""
        else:
            s = min(BAR_STEPS - 1, int((tmin - lo) / span * BAR_STEPS))
            e = max(s + 1, min(BAR_STEPS, math.ceil((tmax - lo) / span * BAR_STEPS)))
            bar = f"<span class=\"range s{s} e{e}\"></span>"
        p = d["precipitation_probability_max"][i]
        rain = text["rain_chance_short"].format(p=mr.whole(p)) if p is not None and p >= 10 else ""
        days.append(f"<li><span class=\"d-name\">{esc(mr.day_name(dt.date.fromisoformat(day), today, text))}</span>"
                    f"<span class=\"d-icon\">{sky.icon(d['weather_code'][i])}</span>"
                    f"<span class=\"d-rain\">{esc(rain)}</span>"
                    f"<span class=\"d-min\">{mr.degrees(tmin)}</span>"
                    f"<span class=\"d-bar\">{bar}</span>"
                    f"<span class=\"d-max\">{mr.degrees(tmax)}</span></li>\n")
    week = f"<section class=\"card\"><h2>{esc(text['week'])}</h2>\n<ol class=\"days\">\n{''.join(days)}</ol></section>"

    def tile(title, big, small=""):
        return (f"<section class=\"card\"><h3>{esc(title)}</h3><p class=\"big\">{esc(big)}</p>"
                + (f"<p class=\"small\">{esc(small)}</p>" if small else "") + "</section>\n")

    rain_mm = d["precipitation_sum"][0]
    sunrise = dt.datetime.fromisoformat(d["sunrise"][0]) if d["sunrise"][0] else None
    sunset = dt.datetime.fromisoformat(d["sunset"][0]) if d["sunset"][0] else None
    uv = d["uv_index_max"][0]
    tiles = ("<div class=\"tiles\">\n"
             + tile(text["tile_rain"], "–" if rain_mm is None else f"{mr.digits(f'{rain_mm:.1f}')} {text['unit_mm']}",
                    text["tile_rain_note"])
             + tile(text["tile_humidity"], "–" if cur["relative_humidity_2m"] is None
                    else f"{mr.whole(cur['relative_humidity_2m'])}%")
             + tile(text["tile_wind"], f"{mr.whole(cur['wind_speed_10m'])} {text['unit_kmh']}",
                    text["tile_wind_note"].format(g=mr.whole(cur["wind_gusts_10m"])))
             + tile(text["tile_uv"], mr.whole(uv), sky.uv_level(uv, text["uv_levels"]))
             + tile(text["tile_sun"], mr.clock(sunrise, parts) if sunrise else "–",
                    mr.clock(sunset, parts) if sunset else "")
             + "</div>")
    body = "\n".join([nav, hero, warn, strip, week, tiles, prices])
    return body, sky.background(cur["weather_code"], cur["is_day"])


def _taluka_row(t, forecast, found, now, text, href: str) -> str:
    if forecast:
        h, d = forecast["hourly"], forecast["daily"]
        cur = _hour(forecast, alert_rules.now_index(h, now))
        p = d["precipitation_probability_max"][0]
        icon = sky.icon(cur["weather_code"], cur["is_day"])
        temps = (f"{mr.degrees(d['temperature_2m_max'][0])} / {mr.degrees(d['temperature_2m_min'][0])}"
                 + (f"<small>{esc(text['rain_chance_short'].format(p=mr.whole(p)))}</small>"
                    if p is not None and p >= 10 else ""))
    else:
        icon, temps = "❔", "–"
    badge = f"<span class=\"badge\">{''.join(BADGE[a.kind] for a in found)}</span>" if found else ""
    return (f"<li><a href=\"{esc(href)}\"><span class=\"h-icon\">{icon}</span>"
            f"<span class=\"name\">{esc(t.mr)}{badge}<span class=\"en\">{esc(t.name)}</span></span>"
            f"<span class=\"temps\">{temps}</span></a></li>\n")


def build_site(site_dir: Path, cfg: dict, talukas: list, result) -> dict:
    """Write the whole site. Returns counts and the per-district alerts."""
    site_dir = Path(site_dir)
    if site_dir.exists():
        if any(site_dir.iterdir()) and not (site_dir / MARKER).exists():
            raise RuntimeError(f"{site_dir} was not made by this pipeline; not deleting it")
        shutil.rmtree(site_dir)
    site_dir.mkdir(parents=True)
    (site_dir / MARKER).write_text("built by havaman; safe to delete\n", encoding="utf-8")
    (site_dir / "style.css").write_text(STYLE, encoding="utf-8")

    text, parts = cfg["text_mr"], cfg["day_parts_mr"]
    now = result.fetched_at
    updated = text["updated"].format(when=f"{mr.short_date(now.date())} {mr.digits(now.year)}, "
                                          f"{mr.clock(now, parts)}")
    districts = {d["slug"]: d for d in cfg["districts"]}
    found = {t.key: alert_rules.for_taluka(result.forecasts.get(t.key), now, cfg["alerts"])
             for t in talukas}
    pages = 0
    for t in talukas:
        body, bg = _taluka_body(t, districts[t.district], result.forecasts.get(t.key), found[t.key], now, cfg)
        out = site_dir / t.district / t.slug / "index.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(_page(f"{t.mr} हवामान", bg, 2, body, text, updated), encoding="utf-8")
        pages += 1

    index_items = []
    for slug, d in districts.items():
        mine = [t for t in talukas if t.district == slug]
        warned = sum(1 for t in mine if found[t.key])
        rows = "".join(_taluka_row(t, result.forecasts.get(t.key), found[t.key], now, text, f"{t.slug}/")
                       for t in mine)
        summary = (f"<p>{esc(text['district_alerts'].format(n=mr.digits(warned)))}</p>" if warned
                   else f"<p>{esc(text['no_alerts'])}</p>")
        body = (f"<nav><a href=\"../\">{esc(text['all_districts'])}</a></nav>\n"
                f"<header class=\"hero\"><h1>{esc(d['mr'])} {esc(text['district_suffix'])}</h1>\n"
                f"<p class=\"sub\">{esc(text['talukas_count'].format(n=mr.digits(len(mine))))}</p></header>\n"
                f"<section class=\"card alerts{'' if warned else ' none'}\">{summary}</section>\n"
                f"<section class=\"card\"><ul class=\"list\">\n{rows}</ul></section>\n"
                f"<p><a href=\"{esc(cfg['site']['prices_url'].rstrip('/'))}/{esc(slug)}/\">"
                f"{esc(text['prices_link'].format(district=d['mr']))}</a></p>")
        (site_dir / slug).mkdir(exist_ok=True)
        (site_dir / slug / "index.html").write_text(
            _page(f"{d['mr']} हवामान", "sky-clear", 1, body, text, updated), encoding="utf-8")
        pages += 1
        badge = f"<span class=\"badge\">⚠ {mr.digits(warned)}</span>" if warned else ""
        index_items.append(f"<li><a href=\"{esc(slug)}/\">{esc(d['mr'])}{badge}"
                           f"<small>{esc(text['talukas_count'].format(n=mr.digits(len(mine))))}</small></a></li>\n")

    body = (f"<header class=\"hero\"><h1>{esc(text['site_title'])}</h1>\n"
            f"<p class=\"sub\">{esc(text['site_intro'])}</p></header>\n"
            f"<ul class=\"grid\">\n{''.join(index_items)}</ul>")
    (site_dir / "index.html").write_text(_page(text["site_title"], "sky-clear", 0, body, text, updated),
                                         encoding="utf-8")
    pages += 1

    district_alerts = alert_rules.by_district(found, talukas)
    (site_dir / "alerts.json").write_text(json.dumps({
        "version": 1, "generated_at": now.isoformat(timespec="seconds"),
        "window_hours": cfg["alerts"]["window_hours"],
        "districts": district_alerts}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return {"pages": pages, "alerts": district_alerts,
            "talukas_with_alerts": sum(1 for v in found.values() if v)}
