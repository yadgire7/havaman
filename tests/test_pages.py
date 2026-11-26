"""The weather site: structure, links, alert rules, and the security rules."""
import copy
import datetime as dt
import json
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from havaman import alerts, marathi, pages, weather  # noqa: E402
from havaman.config import IST, load_config  # noqa: E402
from test_weather import NOW, location  # noqa: E402

CFG = load_config(ROOT / "config.yaml")
PARTS = CFG["day_parts_mr"]
LIMITS = CFG["alerts"]
TALUKAS = [weather.Taluka("latur", "ausa", "Ausa", "औसा", 18.2468, 76.4983),
           weather.Taluka("latur", "nilanga", "Nilanga", "निलंगा", 18.12, 76.75),
           weather.Taluka("pune", "haveli", "Haveli", "हवेली", 18.51, 73.92)]
ALLOWED_TAGS = {"html", "head", "meta", "title", "link", "body", "div", "nav", "a", "header", "h1",
                "h2", "h3", "p", "section", "ul", "ol", "li", "span", "small", "footer"}
ALLOWED_ATTRS = {"lang", "charset", "name", "content", "http-equiv", "rel", "href", "class"}


def forecast(t, changes=None):
    """A checked forecast for taluka t, with some hourly or daily values replaced."""
    f, problems = weather.check_location(t, location(t), 7, NOW)
    assert not problems, problems
    for (part, name, index), value in (changes or {}).items():
        f[part][name][index] = value
    return f


class Tags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags, self.attrs, self.hrefs, self.text = set(), set(), [], []

    def handle_starttag(self, tag, attrs):
        self.tags.add(tag)
        for name, value in attrs:
            self.attrs.add(name)
            if name == "href":
                self.hrefs.append(value)

    def handle_data(self, data):
        self.text.append(data)


def parse(path: Path) -> Tags:
    t = Tags()
    t.feed(path.read_text(encoding="utf-8"))
    return t


class Site:
    def __init__(self, test, forecasts, talukas=TALUKAS, cfg=CFG):
        tmp = tempfile.TemporaryDirectory()
        test.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name) / "site"
        self.built = pages.build_site(self.dir, cfg, talukas, weather.Result(NOW, forecasts))

    def page(self, *parts):
        return (self.dir.joinpath(*parts) / "index.html").read_text(encoding="utf-8")


class AlertRuleTests(unittest.TestCase):
    """Each rule fires at its limit and not just below it."""
    t = TALUKAS[0]
    start = alerts.now_index(forecast(t)["hourly"], NOW)

    def kinds(self, f):
        return [a.kind for a in alerts.for_taluka(f, NOW, LIMITS)]

    def test_quiet_weather_gives_no_alerts(self):
        self.assertEqual(self.kinds(forecast(self.t)), [])

    def test_each_rule_at_and_below_its_limit(self):
        s = self.start + 5
        cases = {"rain": (("hourly", "precipitation_probability", s), LIMITS["rain_chance"]),
                 "heat": (("hourly", "temperature_2m", s), LIMITS["heat_c"]),
                 "wind": (("hourly", "wind_gusts_10m", s), LIMITS["wind_gust_kmh"]),
                 "heavy_rain": (("daily", "precipitation_sum", 1), LIMITS["heavy_rain_mm"])}
        for kind, (where, limit) in cases.items():
            with self.subTest(kind):
                self.assertEqual(self.kinds(forecast(self.t, {where: limit})), [kind])
                self.assertEqual(self.kinds(forecast(self.t, {where: limit - 0.5})), [])

    def test_storm_and_order_most_serious_first(self):
        s = self.start + 3
        f = forecast(self.t, {("hourly", "weather_code", s): 95,
                                ("hourly", "precipitation_probability", s): 90})
        self.assertEqual(self.kinds(f), ["storm", "rain"])

    def test_only_the_next_24_hours_count(self):
        late = self.start + LIMITS["window_hours"] + 2
        f = forecast(self.t, {("hourly", "precipitation_probability", late): 95,
                                ("hourly", "weather_code", late): 95})
        self.assertEqual(self.kinds(f), [])

    def test_missing_values_never_raise_an_alert(self):
        f = forecast(self.t)
        f["hourly"]["temperature_2m"] = [None] * len(f["hourly"]["temperature_2m"])
        self.assertEqual(self.kinds(f), [])
        self.assertEqual(alerts.for_taluka(None, NOW, LIMITS), [])


class SiteTests(unittest.TestCase):
    def setUp(self):
        s = alerts.now_index(forecast(TALUKAS[0])["hourly"], NOW) + 2
        self.site = Site(self, {
            "latur/ausa": forecast(TALUKAS[0], {("hourly", "precipitation_probability", s): 70}),
            "pune/haveli": forecast(TALUKAS[2])})          # Nilanga: no forecast this run

    def test_every_page_exists_and_every_link_resolves(self):
        self.assertEqual(self.site.built["pages"], len(TALUKAS) + len(CFG["districts"]) + 1)
        for path in self.site.dir.rglob("index.html"):
            for href in parse(path).hrefs:
                if href.startswith("https://"):
                    continue
                target = (path.parent / href).resolve()
                with self.subTest(page=str(path.relative_to(self.site.dir)), href=href):
                    self.assertTrue(target.is_file() or (target / "index.html").is_file())

    def test_taluka_page_has_now_24_hours_and_7_days(self):
        html = self.site.page("latur", "ausa")
        self.assertEqual(html.count("<li><span class=\"h-time\">"), 24)
        self.assertIn(f"<span class=\"h-time\">{CFG['text_mr']['now']}</span>", html)
        self.assertEqual(html.count("<li><span class=\"d-name\">"), 7)
        self.assertIn(CFG["text_mr"]["today"], html)
        self.assertIn("औसा", html)

    def test_alert_shows_on_taluka_district_and_alerts_json(self):
        self.assertIn("☔", self.site.page("latur", "ausa"))
        self.assertIn("⚠", self.site.page())
        data = json.loads((self.site.dir / "alerts.json").read_text(encoding="utf-8"))
        self.assertEqual(data["districts"], {"latur": {"rain": ["ausa"]}})
        self.assertEqual(data["generated_at"], NOW.isoformat(timespec="seconds"))

    def test_taluka_without_forecast_still_has_a_page(self):
        self.assertIn(CFG["text_mr"]["no_forecast"], self.site.page("latur", "nilanga"))

    def test_temperature_bars_use_classes_in_range(self):
        import re
        bars = re.findall(r'class="range s(\d+) e(\d+)"', self.site.page("latur", "ausa"))
        self.assertEqual(len(bars), 7)
        for s, e in bars:
            self.assertTrue(0 <= int(s) < int(e) <= pages.BAR_STEPS)

    def test_credits_and_price_link(self):
        html = self.site.page("pune", "haveli")
        self.assertIn('href="https://open-meteo.com/"', html)
        self.assertIn('href="https://www.openstreetmap.org/copyright"', html)
        self.assertIn('href="https://bajarbhav.shetkarishala.com/pune/"', html)

    def test_site_folder_not_made_by_pipeline_is_never_deleted(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "keep.txt").write_text("mine")
            with self.assertRaises(RuntimeError):
                pages.build_site(Path(tmp), CFG, TALUKAS, weather.Result(NOW, {}))
            self.assertTrue((Path(tmp) / "keep.txt").exists())


class SecurityTests(unittest.TestCase):
    def test_every_page_is_static_and_locked_down(self):
        site = Site(self, {"latur/ausa": forecast(TALUKAS[0])})
        allowed_links = ("https://open-meteo.com/", "https://www.openstreetmap.org/copyright",
                         "https://bajarbhav.shetkarishala.com/")
        for path in site.dir.rglob("index.html"):
            html = path.read_text(encoding="utf-8")
            tags = parse(path)
            with self.subTest(str(path.relative_to(site.dir))):
                self.assertIn(f'content="{pages.CSP}"', html)
                self.assertLessEqual(tags.tags, ALLOWED_TAGS)
                self.assertLessEqual(tags.attrs, ALLOWED_ATTRS)    # no style=, no on*=, no src=
                for href in tags.hrefs:
                    self.assertFalse(href.startswith(("http:", "//", "javascript:", "data:")))
                    if href.startswith("https://"):
                        self.assertTrue(href.startswith(allowed_links), href)

    def test_hostile_names_are_escaped(self):
        evil = weather.Taluka("latur", "evil", '<script>alert(1)</script>', '"><img src=x onerror=1>',
                              18.25, 76.5)
        cfg = copy.deepcopy(CFG)
        cfg["districts"][0]["mr"] = "<b onclick=x>"
        site = Site(self, {"latur/evil": forecast(evil)}, talukas=[evil], cfg=cfg)
        for path in site.dir.rglob("index.html"):
            tags = parse(path)
            with self.subTest(str(path.relative_to(site.dir))):
                self.assertLessEqual(tags.tags, ALLOWED_TAGS)
                self.assertLessEqual(tags.attrs, ALLOWED_ATTRS)


class MarathiTests(unittest.TestCase):
    def test_times_and_days(self):
        at = lambda h, m=0: dt.datetime(2026, 11, 26, h, m, tzinfo=IST)
        self.assertEqual(marathi.clock(at(6, 36), PARTS), "सकाळ ६:३६")
        self.assertEqual(marathi.clock(at(0), PARTS, minutes=False), "सकाळ १२")
        self.assertEqual(marathi.clock(at(14), PARTS, minutes=False), "दुपार २")
        self.assertEqual(marathi.clock(at(19, 5), PARTS), "संध्याकाळ ७:०५")
        today = dt.date(2026, 11, 26)                      # a Thursday
        text = CFG["text_mr"]
        names = [marathi.day_name(today + dt.timedelta(days=i), today, text) for i in range(4)]
        self.assertEqual(names, ["आज", "उद्या", "शनि", "रवि"])
        self.assertEqual(marathi.degrees(29.6), "३०°")
        self.assertEqual(marathi.degrees(None), "–")


if __name__ == "__main__":
    unittest.main()
