#!/usr/bin/env python3
"""Build the weather site from a saved forecast file.

    python build_site.py                                  # out/weather/weather.json.gz -> site/
    python build_site.py --from file.json.gz --site dir

Writes an index, a page per district and per taluka, style.css and
alerts.json (the next-24-hour alerts per district, read by the price posts).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from havaman import pages, weather
from havaman.config import load_config

HERE = Path(__file__).resolve().parent


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--config", type=Path, default=HERE / "config.yaml")
    p.add_argument("--from", dest="source", type=Path, default=HERE / "out" / "weather" / "weather.json.gz")
    p.add_argument("--site", type=Path, default=HERE / "site")
    args = p.parse_args(argv)

    cfg = load_config(args.config)
    talukas = weather.load_talukas(cfg["talukas"], {d["slug"] for d in cfg["districts"]})
    result = weather.load(args.source)
    built = pages.build_site(args.site, cfg, talukas, result)
    print(f"Built {built['pages']} pages into {args.site}; "
          f"{built['talukas_with_alerts']} talukas with alerts in {len(built['alerts'])} districts.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
