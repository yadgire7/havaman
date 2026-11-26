# हवामान: weather for every Maharashtra taluka

Hourly and 7-day weather for all 358 talukas of Maharashtra (plus Mumbai City),
as Marathi web pages at **havaman.shetkarishala.com**, for the
[शेतकरी शाळा](https://www.youtube.com/@shetkarishalaMH) YouTube channel. It is
the companion of the mandi price pages at
[bajarbhav.shetkarishala.com](https://bajarbhav.shetkarishala.com/)
([yadgire7/mandi-prices](https://github.com/yadgire7/mandi-prices)), and runs on
its own: its own schedule, its own site, no secrets.

Every step is a fixed rule in code: no AI, and no value is typed by hand.

**Status: part 1 done.** The taluka list and a checked forecast fetch. Next:
the weather pages, the 3-hourly schedule with GitHub Pages, and a small
`alerts.json` that the price run reads for the WhatsApp post.

## How it works

1. `talukas.yaml` lists every taluka: its district, Marathi name, LGD code and
   the point the forecast is for (the taluka headquarters where known).
2. `fetch_weather.py` asks [Open-Meteo](https://open-meteo.com/) for all of
   them in batches of 50 (about 20 seconds), checks every value (ranges,
   weather codes, hour counts, that each answer is for the right place) and
   saves one compact file, `out/weather/weather.json.gz`. Bad values are
   emptied and listed; it fails if fewer than 90% of talukas got a forecast.

## Commands

```bash
python3 -m venv .venv && ./.venv/bin/pip install --require-hashes -r requirements.txt
```

```bash
./.venv/bin/python fetch_weather.py
```

```bash
./.venv/bin/python -m unittest discover -s tests
```

On GitHub, run the "Weather" workflow from the Actions tab (or
`gh workflow run weather.yml -R yadgire7/havaman`).

## Security

- No secrets: Open-Meteo needs no key and failures are reported by GitHub's own
  failure emails.
- Workflows never run on `pull_request_target`, use read-only tokens, keep no
  credentials after checkout, and pin every action to a full commit SHA. A test
  enforces these rules. PyYAML is pinned by hash. Dependabot proposes updates.
- Every value from the API is checked before use.

## Licences and credits

- Weather data: © [Open-Meteo.com](https://open-meteo.com/), CC BY 4.0. Every
  page must credit and link it. The free API is for non-commercial use, under
  10,000 calls a day; this project uses about 5,000.
- Taluka list: © [OpenStreetMap](https://www.openstreetmap.org/copyright)
  contributors, ODbL 1.0, built by `scripts/build_talukas.py` (Mumbai
  Suburban's three talukas placed by hand). Marathi names need review.

## Files

| Path | What it is |
| --- | --- |
| `config.yaml` | Settings and the 35 districts (same slugs as the price pages) |
| `talukas.yaml` | Every taluka and its forecast point |
| `fetch_weather.py` | Fetches, checks and saves the forecast |
| `havaman/` | The code: config, HTTP, weather checks |
| `scripts/build_talukas.py` | Rebuilds `talukas.yaml` from OpenStreetMap downloads (by hand) |
| `tests/` | Tests, with no network needed |
| `.github/` | The weather and test workflows, Dependabot |
