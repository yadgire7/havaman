"""WMO weather codes as Marathi words, an emoji and a background style.

Labels are drafts for the admin's review; emoji keep the pages free of image
files and outside resources.
"""
from __future__ import annotations

# code: (Marathi label, day emoji, night emoji, background)
SKY = {
    0: ("निरभ्र आकाश", "☀️", "🌙", "clear"),
    1: ("बहुतांश निरभ्र", "🌤️", "🌙", "clear"),
    2: ("अंशतः ढगाळ", "⛅", "☁️", "cloudy"),
    3: ("ढगाळ", "☁️", "☁️", "cloudy"),
    45: ("धुके", "🌫️", "🌫️", "fog"),
    48: ("दाट धुके", "🌫️", "🌫️", "fog"),
    51: ("हलकी रिमझिम", "🌦️", "🌧️", "rain"),
    53: ("रिमझिम", "🌦️", "🌧️", "rain"),
    55: ("दाट रिमझिम", "🌧️", "🌧️", "rain"),
    56: ("गोठणारी रिमझिम", "🌧️", "🌧️", "rain"),
    57: ("गोठणारी दाट रिमझिम", "🌧️", "🌧️", "rain"),
    61: ("हलका पाऊस", "🌦️", "🌧️", "rain"),
    63: ("पाऊस", "🌧️", "🌧️", "rain"),
    65: ("मुसळधार पाऊस", "🌧️", "🌧️", "rain"),
    66: ("गोठणारा पाऊस", "🌧️", "🌧️", "rain"),
    67: ("गोठणारा मुसळधार पाऊस", "🌧️", "🌧️", "rain"),
    71: ("हलकी हिमवृष्टी", "🌨️", "🌨️", "cloudy"),
    73: ("हिमवृष्टी", "🌨️", "🌨️", "cloudy"),
    75: ("जोरदार हिमवृष्टी", "🌨️", "🌨️", "cloudy"),
    77: ("हिमकण", "🌨️", "🌨️", "cloudy"),
    80: ("हलक्या सरी", "🌦️", "🌧️", "rain"),
    81: ("पावसाच्या सरी", "🌧️", "🌧️", "rain"),
    82: ("जोरदार सरी", "🌧️", "🌧️", "rain"),
    85: ("हिमवृष्टीच्या सरी", "🌨️", "🌨️", "cloudy"),
    86: ("जोरदार हिमवृष्टीच्या सरी", "🌨️", "🌨️", "cloudy"),
    95: ("विजांसह वादळी पाऊस", "⛈️", "⛈️", "storm"),
    96: ("गारपिटीसह वादळ", "⛈️", "⛈️", "storm"),
    99: ("जोरदार गारपिटीसह वादळ", "⛈️", "⛈️", "storm"),
}
STORM = {95, 96, 99}
UNKNOWN = ("माहिती नाही", "❔", "❔", "cloudy")


def label(code) -> str:
    return SKY.get(code, UNKNOWN)[0]


def icon(code, is_day=1) -> str:
    entry = SKY.get(code, UNKNOWN)
    return entry[1] if is_day != 0 else entry[2]


def background(code, is_day=1) -> str:
    """CSS class for the page: sky-clear, sky-clear-night, sky-rain, ..."""
    base = SKY.get(code, UNKNOWN)[3]
    return f"sky-{base}-night" if base == "clear" and is_day == 0 else f"sky-{base}"


def uv_level(uv, words: list[str]) -> str:
    """WHO UV index bands: low, moderate, high, very high, extreme."""
    if uv is None:
        return ""
    for limit, word in zip((3, 6, 8, 11), words):
        if uv < limit:
            return word
    return words[4]
