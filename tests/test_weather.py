"""Weather: the taluka list, the Open-Meteo answer checks, and the saved file."""
import copy
import datetime as dt
import json
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from havaman import weather  # noqa: E402
from havaman.config import IST, ConfigError, load_config, validate_config  # noqa: E402

CFG = load_config(ROOT / "config.yaml")
SLUGS = {d["slug"] for d in CFG["districts"]}
NOW = dt.datetime(2026, 11, 26, 8, 46, tzinfo=IST)
AUSA = weather.Taluka("latur", "ausa", "Ausa", "औसा", 18.2468, 76.4983)


def location(t=AUSA, days=7, temp=24.5, **overrides):
    """One location as Open-Meteo returns it."""
    start = dt.datetime.combine(NOW.date(), dt.time())
    hours = [(start + dt.timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M") for i in range(days * 24)]
    dates = [(NOW.date() + dt.timedelta(days=i)).isoformat() for i in range(days)]
    hourly = {"time": hours, "temperature_2m": [temp] * len(hours),
              "apparent_temperature": [temp + 2] * len(hours),
              "relative_humidity_2m": [60] * len(hours), "precipitation_probability": [10] * len(hours),
              "precipitation": [0.0] * len(hours), "weather_code": [1] * len(hours),
              "wind_speed_10m": [8.0] * len(hours), "wind_gusts_10m": [15.0] * len(hours),
              "is_day": [1] * len(hours)}
    daily = {"time": dates, "weather_code": [1] * days, "temperature_2m_max": [30.0] * days,
             "temperature_2m_min": [20.0] * days, "precipitation_sum": [0.0] * days,
             "precipitation_probability_max": [10] * days, "uv_index_max": [6.0] * days,
             "sunrise": [d + "T06:36" for d in dates], "sunset": [d + "T17:45" for d in dates]}
    loc = {"latitude": t.lat + 0.02, "longitude": t.lon - 0.01, "elevation": 633.0,
           "hourly": hourly, "daily": daily}
    loc.update(overrides)
    return loc


class TalukaListTests(unittest.TestCase):
    def test_committed_list_covers_every_district(self):
        talukas = weather.load_talukas(CFG["talukas"], SLUGS)
        self.assertEqual(len(talukas), 359)            # 358 talukas + Mumbai City
        per_district = Counter(t.district for t in talukas)
        self.assertEqual(set(per_district), SLUGS)      # every district page gets weather
        self.assertEqual((per_district["pune"], per_district["nashik"], per_district["dhule"]),
                         (14, 15, 4))
        self.assertTrue(all(t.mr for t in talukas))

    def test_bad_entries_are_refused(self):
        good = {"district": "latur", "slug": "ausa", "name": "Ausa", "mr": "औसा",
                "lat": 18.25, "lon": 76.5}
        cases = {"unknown district": {**good, "district": "goa"},
                 "outside Maharashtra": {**good, "lat": 28.6, "lon": 77.2},
                 "must be a-z": {**good, "slug": "../x"},
                 "incomplete": {k: v for k, v in good.items() if k != "lat"}}
        for words, bad in cases.items():
            with self.subTest(words), self.assertRaisesRegex(ValueError, words):
                weather.load_talukas({"talukas": [good, bad] if words != "listed twice" else [good]}, SLUGS)
        with self.assertRaisesRegex(ValueError, "listed twice"):
            weather.load_talukas({"talukas": [good, dict(good)]}, SLUGS)

    def test_config_rejects_bad_weather_settings(self):
        for key, value in (("forecast_days", 16), ("batch_size", 0), ("every_hours", 5)):
            cfg = copy.deepcopy(CFG)
            cfg["weather"][key] = value
            with self.subTest(key), self.assertRaises(ConfigError):
                validate_config(cfg)


class AnswerCheckTests(unittest.TestCase):
    def check(self, loc, t=AUSA):
        return weather.check_location(t, loc, 7, NOW)

    def test_good_location_passes_unchanged(self):
        forecast, problems = self.check(location())
        self.assertEqual(problems, [])
        self.assertEqual(len(forecast["hourly"]["time"]), 168)
        self.assertEqual(forecast["hourly"]["temperature_2m"][0], 24.5)
        self.assertEqual(forecast["daily"]["sunrise"][0], "2026-11-26T06:36")

    def test_impossible_values_are_emptied_and_listed(self):
        loc = location()
        loc["hourly"]["temperature_2m"][3] = 85
        loc["hourly"]["precipitation_probability"][4] = 140
        loc["hourly"]["weather_code"][5] = 42            # not a WMO code
        loc["hourly"]["wind_speed_10m"][6] = float("nan")
        loc["hourly"]["relative_humidity_2m"][7] = "<script>"
        forecast, problems = self.check(loc)
        h = forecast["hourly"]
        self.assertEqual((h["temperature_2m"][3], h["precipitation_probability"][4],
                          h["weather_code"][5], h["wind_speed_10m"][6], h["relative_humidity_2m"][7]),
                         (None, None, None, None, None))
        self.assertEqual(len(problems), 5)

    def test_answer_for_another_place_is_dropped(self):
        forecast, problems = self.check(location(latitude=19.9, longitude=73.8))
        self.assertIsNone(forecast)
        self.assertIn("another place", problems[0])

    def test_broken_shapes_are_dropped(self):
        short = location()
        short["hourly"]["time"] = short["hourly"]["time"][:100]
        old = location()
        old["hourly"]["time"] = [t.replace("2026-11-26", "2026-11-20") for t in old["hourly"]["time"]]
        for loc in (short, location(hourly=None), "text", location(temp=99), old):
            with self.subTest(loc=str(loc)[:30]):
                self.assertIsNone(self.check(loc)[0])

    def test_series_with_wrong_length_becomes_empty_not_shifted(self):
        loc = location()
        loc["hourly"]["precipitation"] = [0.0] * 10
        forecast, problems = self.check(loc)
        self.assertEqual(forecast["hourly"]["precipitation"], [None] * 168)
        self.assertIn("wrong length", problems[0])


class FetchTests(unittest.TestCase):
    TALUKAS = [AUSA, weather.Taluka("nashik", "niphad", "Niphad", "निफाड", 20.08, 74.11),
               weather.Taluka("pune", "haveli", "Haveli", "हवेली", 18.51, 73.92)]

    def fake(self, answers):
        calls = []

        def fetch(url):
            calls.append(url)
            answer = answers.pop(0)
            if isinstance(answer, Exception):
                raise answer
            return answer
        return fetch, calls

    def test_batches_ask_for_every_variable_in_indian_time(self):
        locs = [location(t) for t in self.TALUKAS]
        fetch, calls = self.fake([(200, json.dumps(locs[:2]).encode()), (200, json.dumps(locs[2]).encode())])
        result = weather.fetch_all(self.TALUKAS, NOW, 7, 2, fetch=fetch, sleep=lambda s: None)
        self.assertEqual(sorted(result.forecasts), ["latur/ausa", "nashik/niphad", "pune/haveli"])
        self.assertEqual(len(calls), 2)
        self.assertTrue(calls[0].startswith("https://api.open-meteo.com/v1/forecast?"))
        for name in list(weather.HOURLY) + ["timezone=Asia%2FKolkata", "forecast_days=7"]:
            self.assertIn(name, calls[0])

    def test_one_failed_batch_does_not_stop_the_rest(self):
        locs = [location(t) for t in self.TALUKAS]
        fetch, calls = self.fake([(503, b"down"), (503, b"down"), (503, b"down"),
                                  (200, json.dumps(locs[2]).encode())])
        result = weather.fetch_all(self.TALUKAS, NOW, 7, 2, fetch=fetch, sleep=lambda s: None)
        self.assertEqual(list(result.forecasts), ["pune/haveli"])
        self.assertIn("HTTP 503", result.problems[0])

    def test_rejected_request_is_not_retried(self):
        fetch, calls = self.fake([(400, b'{"error":true,"reason":"bad"}')])
        result = weather.fetch_all(self.TALUKAS[:1], NOW, 7, 5, fetch=fetch, sleep=lambda s: None)
        self.assertEqual((len(calls), result.forecasts), (1, {}))

    def test_answer_count_must_match_the_batch(self):
        fetch, _ = self.fake([(200, json.dumps([location()]).encode())])
        result = weather.fetch_all(self.TALUKAS[:2], NOW, 7, 2, fetch=fetch, sleep=lambda s: None)
        self.assertEqual(result.forecasts, {})
        self.assertIn("one forecast per taluka", result.problems[0])

    def test_save_and_load_round_trip(self):
        fetch, _ = self.fake([(200, json.dumps(location()).encode())])
        result = weather.fetch_all([AUSA], NOW, 7, 1, fetch=fetch, sleep=lambda s: None)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "w.json.gz"
            weather.save(path, result)
            back = weather.load(path)
        self.assertEqual((back.fetched_at, back.forecasts), (NOW, result.forecasts))

    def test_daily_call_budget_stays_well_under_the_free_limit(self):
        # Open-Meteo counts a location with more than 10 variables or 7 days as
        # more than one call; this rough count keeps a wide margin under 10,000.
        settings = CFG["weather"]
        variables = len(weather.HOURLY) + len(weather.DAILY)
        per_location = max(1, variables / 10) * max(1, settings["forecast_days"] / 7)
        per_day = len(CFG["talukas"]["talukas"]) * per_location * (24 / settings["every_hours"])
        self.assertLess(per_day, 7000)


if __name__ == "__main__":
    unittest.main()
