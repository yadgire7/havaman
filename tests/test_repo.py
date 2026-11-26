"""Config checks, and the security rules every workflow must follow."""
import copy
import sys
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from havaman.config import ConfigError, load_config, validate_config  # noqa: E402

CFG = load_config(ROOT / "config.yaml")


class ConfigTests(unittest.TestCase):
    def test_rejects_bad_settings(self):
        cases = [lambda c: c["site"].update(base_url="http://insecure.example"),
                 lambda c: c["site"].update(prices_url='https://x.io/"><script>'),
                 lambda c: c["districts"].append(dict(c["districts"][0])),
                 lambda c: c["districts"][0].update(slug="../etc")]
        for change in cases:
            cfg = copy.deepcopy(CFG)
            change(cfg)
            with self.subTest(change), self.assertRaises(ConfigError):
                validate_config(cfg)

    def test_districts_match_the_price_pages(self):
        self.assertEqual(len(CFG["districts"]), 35)


class WorkflowTests(unittest.TestCase):
    FLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))

    @staticmethod
    def triggers(flow):
        return flow.get("on", flow.get(True))  # YAML 1.1 reads a bare `on` as true

    def test_workflows_follow_the_security_rules(self):
        self.assertTrue(self.FLOWS)
        for path in self.FLOWS:
            flow = yaml.safe_load(path.read_text(encoding="utf-8"))
            with self.subTest(path.name):
                self.assertNotIn("pull_request_target", self.triggers(flow))
                self.assertIn("permissions", flow, "set token permissions explicitly")
                self.assertNotIn("secrets.", path.read_text(encoding="utf-8"), "this repo uses no secrets")
                for job in flow["jobs"].values():
                    for step in job["steps"]:
                        if "uses" in step:
                            self.assertRegex(step["uses"], r"^[\w.-]+/[\w.-]+@[0-9a-f]{40}$",
                                             "pin every action to a full commit SHA")
                        if step.get("uses", "").startswith("actions/checkout@"):
                            self.assertIs(step.get("with", {}).get("persist-credentials"), False)
                        self.assertNotRegex(step.get("run", ""), r"\$\{\{",
                                            "${{ }} inside a shell script is an injection risk")

    def test_schedule_matches_config(self):
        import datetime as dt
        from havaman.config import IST
        flow = yaml.safe_load((ROOT / ".github/workflows/weather.yml").read_text(encoding="utf-8"))
        got = set()
        for entry in self.triggers(flow)["schedule"]:
            minute, hour = entry["cron"].split()[:2]
            span, _, step = hour.partition("/")
            lo, _, hi = span.partition("-")
            hours = range(int(lo), int(hi or lo) + 1, int(step or 1))
            got |= {(h, int(minute)) for h in hours}
        every = CFG["weather"]["every_hours"]
        hh, mm = (int(x) for x in CFG["weather"]["first_run_ist"].split(":"))
        first = dt.datetime(2026, 1, 1, hh, mm, tzinfo=IST)
        expected = {((first + dt.timedelta(hours=k * every)).astimezone(dt.timezone.utc).hour,
                     (first + dt.timedelta(hours=k * every)).astimezone(dt.timezone.utc).minute)
                    for k in range(24 // every)}
        self.assertEqual(got, expected, "weather.yml cron no longer matches config.yaml")

    def test_requirements_are_hash_pinned(self):
        text = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        self.assertRegex(text, r"(?m)^PyYAML==[\d.]+ ")
        self.assertRegex(text, r"--hash=sha256:[0-9a-f]{64}")


if __name__ == "__main__":
    unittest.main()
