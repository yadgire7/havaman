#!/usr/bin/env python3
"""Fetch the weather forecast for every taluka from Open-Meteo, check it, save it.

    python fetch_weather.py                          # writes out/weather/weather.json.gz
    python fetch_weather.py --out some/file.json.gz

Exit code 1 if fewer than 90% of talukas got a usable forecast. Pages and the
post read the saved file; they never call Open-Meteo themselves.
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

from havaman import weather
from havaman.config import IST, load_config

HERE = Path(__file__).resolve().parent
MIN_SHARE = 0.9


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--config", type=Path, default=HERE / "config.yaml")
    p.add_argument("--out", type=Path, default=HERE / "out" / "weather" / "weather.json.gz")
    args = p.parse_args(argv)

    cfg = load_config(args.config)
    settings = cfg["weather"]
    talukas = weather.load_talukas(cfg["talukas"], {d["slug"] for d in cfg["districts"]})
    now = dt.datetime.now(IST)
    result = weather.fetch_all(talukas, now, settings["forecast_days"], settings["batch_size"],
                               pause=settings["pause_seconds"])
    weather.save(args.out, result)

    share = len(result.forecasts) / len(talukas)
    print(f"Weather {now:%Y-%m-%d %H:%M} IST: {len(result.forecasts)} of {len(talukas)} talukas "
          f"({share:.0%}), {len(result.problems)} problems, saved to {args.out}")
    for problem in result.problems[:20]:
        print(f"- {problem}")
    return 0 if share >= MIN_SHARE else 1


if __name__ == "__main__":
    sys.exit(main())
