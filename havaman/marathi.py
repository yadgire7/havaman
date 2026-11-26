"""Devanagari numbers, dates and times. Numbers are converted by code, not
translated, so they are always exact. Words come from config.yaml."""
from __future__ import annotations

import datetime as dt

DIGITS = str.maketrans("0123456789", "०१२३४५६७८९")
MONTHS = ("जाने", "फेब्रु", "मार्च", "एप्रि", "मे", "जून", "जुलै", "ऑग", "सप्टें",
          "ऑक्टो", "नोव्हें", "डिसें")


def digits(value) -> str:
    return str(value).translate(DIGITS)


def whole(value) -> str:
    """A rounded whole number in Devanagari digits; '–' when there is no value."""
    return "–" if value is None else digits(int(round(value)))


def degrees(value) -> str:
    return "–" if value is None else whole(value) + "°"


def short_date(d: dt.date) -> str:
    return f"{digits(d.day)} {MONTHS[d.month - 1]}"


def day_part(hour: int, parts: list[dict]) -> str:
    started = [p for p in parts if p["from"] <= hour]
    return (started or parts)[-1]["mr"]


def clock(moment: dt.datetime, parts: list[dict], minutes: bool = True) -> str:
    """'सकाळ ६:३६', 'दुपार २' (12-hour clock with the configured part of day)."""
    hour12 = moment.hour % 12 or 12
    text = f"{hour12}:{moment.minute:02d}" if minutes else str(hour12)
    return f"{day_part(moment.hour, parts)} {digits(text)}"


def day_name(d: dt.date, today: dt.date, text: dict) -> str:
    if d == today:
        return text["today"]
    if d == today + dt.timedelta(days=1):
        return text["tomorrow"]
    return text["weekdays"][d.weekday()]
