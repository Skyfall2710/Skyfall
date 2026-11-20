# tests/test_skyfall.py — unit tests for Skyfall OSINT Helper.
#
# Run:
#   python3 -m unittest discover -s tests -v
#
# The tests do not access the network and do not launch external OSINT tools:
# subprocess/requests are mocked.

import json
import os
import tempfile
import unittest
from unittest import mock

import main
from tools.diablinda import _extract_json, parse_diablinda_json
from tools.holehe import parse_holehe_output
from tools.theharvester import parse_theharvester_output
from tools.threatfox import check_ioc


HOLEHE_SAMPLE = """
    target@example.com
*************************

[+] github.com
[+] google.com recovery@mail.com / +79990000000 / FullName John Doe
[-] twitter.com
[+] Email used
[-] Email not used
[x] Rate limit
[+] Twitter : @johndoe
[x] reddit.com
[+] localhost
[+] user@example.com
[+] http://not-a-domain.com
"""


class TestHoleheParser(unittest.TestCase):
    def test_only_valid_domains_from_plus_lines(self):
        parsed = parse_holehe_output(HOLEHE_SAMPLE)
        sites = [item["site"] for item in parsed["found"]]

        self.assertEqual(sites, ["github.com", "google.com"])
        self.assertNotIn("Email used", sites)
        self.assertNotIn("Twitter", sites)
        self.assertNotIn("localhost", sites)
        self.assertNotIn("user@example.com", sites)

    def test_metadata_is_kept_as_details(self):
        parsed = parse_holehe_output(HOLEHE_SAMPLE)
        google = parsed["found"][1]
        self.assertEqual(google["site"], "google.com")
        self.assertIn("recovery@mail.com", google["details"])
        self.assertIn("FullName John Doe", google["details"])

    def test_rate_limited_domains(self):
        parsed = parse_holehe_output(HOLEHE_SAMPLE)
        self.assertEqual(parsed["rate_limited"], ["reddit.com"])


class TestTheHarvesterParser(unittest.TestCase):
    RAW = """
[*] IPs found: 2
-------------------
1.2.3.4
5.6.7.8
[*] Emails found: 2
----------------------
john@example.com
jane@example.com
[*] Hosts found: 3
---------------------
www.example.com:1.2.3.4
api.example.com
mail.example.com:5.6.7.8
[*] No people found.
"""

    def test_emails_subdomains_and_ips(self):
        parsed = parse_theharvester_output(self.RAW, "example.com")

        self.assertEqual(
            parsed["emails"],
            ["jane@example.com", "john@example.com"],
        )
        self.assertEqual(
            parsed["subdomains"],
            ["api.example.com", "mail.example.com", "www.example.com"],
        )
        self.assertEqual(parsed["ips"], ["1.2.3.4", "5.6.7.8"])

    def test_subdomains_are_full_hosts_not_last_label(self):
        # Old bug: findall with a group returned "www." instead of the FQDN.
        parsed = parse_theharvester_output(self.RAW, "example.com")
        self.assertIn("www.example.com", parsed["subdomains"])
        self.assertNotIn("www.", parsed["subdomains"])

    def test_host_ip_mapping(self):
        parsed = parse_theharvester_output(self.RAW, "example.com")
        mapping = {item["host"]: item["ip"] for item in parsed["hosts"]}
        self.assertEqual(mapping["www.example.com"], "1.2.3.4")
        self.assertEqual(mapping["mail.example.com"], "5.6.7.8")
        self.assertIsNone(mapping["api.example.com"])


class TestDiablindaParser(unittest.TestCase):
    PAYLOAD = {
        "email": "target@example.com",
        "hits": 2,
        "results": [
            {
                "id": "github",
                "service": "GitHub",
                "category": "tech",
                "exists": True,
                "metadata": {
                    "username": "octocat",
                    "avatarUrl": "https://avatars.githubusercontent.com/u/583231",
                    "profileUrl": "https://github.com/octocat",
                    "name": "The Octocat",
                    "bio": "Mascot",
                    "extra": {"verifiedByEmail": True},
                },
            },
            {
                "id": "reddit",
                "service": "Reddit",
                "exists": False,
                "metadata": {},
            },
        ],
        "dossier": {
            "names": ["The Octocat"],
            "usernames": ["octocat"],
            "avatars": ["https://avatars.githubusercontent.com/u/583231"],
            "externalLinks": [
                {"platform": "GitHub", "url": "https://github.com/octocat"}
            ],
        },
    }

    def test_found_services_with_metadata(self):
        parsed = parse_diablinda_json(self.PAYLOAD)
        self.assertEqual(parsed["email"], "target@example.com")
        self.assertEqual(len(parsed["found"]), 1)

        item = parsed["found"][0]
        self.assertEqual(item["service"], "GitHub")
        self.assertEqual(item["username"], "octocat")
        self.assertIn("avatars.githubusercontent.com", item["avatar"])
        self.assertEqual(item["profile_url"], "https://github.com/octocat")
        self.assertTrue(item["verified_by_email"])

    def test_dossier_is_normalized(self):
        parsed = parse_diablinda_json(self.PAYLOAD)
        self.assertEqual(parsed["dossier"]["usernames"], ["octocat"])
        self.assertEqual(
            parsed["dossier"]["external_links"],
            [{"platform": "GitHub", "url": "https://github.com/octocat"}],
        )

    def test_extract_json_with_npm_noise(self):
        raw = 'npm notice something\n{"email": "a@b.com", "results": []}\n'
        payload = _extract_json(raw)
        self.assertEqual(payload["email"], "a@b.com")


class TestThreatFox(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, {"THREATFOX_KEY": "test-key"})
        self.env.start()
        self.addCleanup(self.env.stop)

    @mock.patch("tools.threatfox.requests.post")
    def test_found_ioc(self, post):
        response = mock.Mock()
        response.status_code = 200
        response.json.return_value = {
            "query_status": "ok",
            "data": [{
                "ioc": "evil.example:443",
                "threat_type": "botnet_cc",
                "malware": "win.emotet",
                "malware_printable": "Emotet",
                "confidence_level": 100,
            }],
        }
        post.return_value = response

        result = check_ioc("evil.example")

        self.assertTrue(result["found"])
        self.assertEqual(result["malware"], "Emotet")
        self.assertEqual(result["confidence"], 100)
        self.assertEqual(result["threat_type"], "botnet_cc")

    @mock.patch("tools.threatfox.requests.post")
    def test_no_result(self, post):
        response = mock.Mock()
        response.status_code = 200
        response.json.return_value = {"query_status": "no_result", "data": []}
        post.return_value = response

        result = check_ioc("clean.example")

        self.assertFalse(result["found"])
        self.assertEqual(result["query_status"], "no_result")

    def test_missing_key_returns_clear_error(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            result = check_ioc("evil.example")

        self.assertFalse(result["found"])
        self.assertIn("THREATFOX_KEY", result["error"])


class TestNormalize(unittest.TestCase):
    def test_email_diablinda_fallback_metadata(self):
        data = {
            "holehe": {"email": "target@example.com", "found": [], "rate_limited": []},
            "diablinda": {
                "email": "target@example.com",
                "found": [{
                    "service": "GitHub",
                    "username": "octocat",
                    "avatar": "https://avatar.example/1",
                    "profile_url": "https://github.com/octocat",
                    "name": "Octo",
                    "bio": "Mascot",
                    "category": "tech",
                }],
                "dossier": {
                    "usernames": ["octocat"],
                    "names": ["Octo"],
                    "avatars": ["https://avatar.example/1"],
                },
            },
        }

        normalized = main.normalize(data, "email", "target@example.com")

        self.assertTrue(main.has_usable_data(normalized))
        self.assertIn("octocat", normalized["nicks"])
        self.assertIn("https://github.com/octocat", normalized["urls"])
        self.assertTrue(any("Diablinda" in obs for obs in normalized["observations"]))
        self.assertTrue(any(
            "avatar" in str(site.get("data", {}))
            for site in normalized["sites"]
        ))

    def test_domain_threatfox_observation(self):
        data = {
            "theharvester": {
                "domain": "example.com",
                "emails": ["john@example.com"],
                "subdomains": ["www.example.com"],
                "ips": ["1.2.3.4"],
                "hosts": [{"host": "www.example.com", "ip": "1.2.3.4"}],
            },
            "threatfox": [{
                "ioc": "www.example.com",
                "found": True,
                "malware": "Emotet",
                "confidence": 100,
                "threat_type": "botnet_cc",
            }],
        }

        normalized = main.normalize(data, "domain", "example.com")

        self.assertIn("john@example.com", normalized["emails"])
        self.assertTrue(any(
            "www.example.com" in site["site"]
            for site in normalized["sites"]
        ))
        self.assertTrue(any(
            "⚠️ Домен связан с малварью: Emotet" in obs
            for obs in normalized["observations"]
        ))

    def test_email_without_results_is_not_usable(self):
        data = {
            "holehe": {
                "email": "target@example.com",
                "found": [],
                "rate_limited": ["github.com"],
            }
        }
        normalized = main.normalize(data, "email", "target@example.com")

        # The target email is not treated as a discovered entity.
        self.assertFalse(main.has_usable_data(normalized))

    def test_domain_with_only_threatfox_hit_is_usable(self):
        data = {
            "theharvester": {
                "domain": "example.com",
                "emails": [],
                "subdomains": [],
                "ips": [],
                "hosts": [],
            },
            "threatfox": [{
                "ioc": "example.com",
                "found": True,
                "malware": "Emotet",
                "confidence": 100,
            }],
        }
        normalized = main.normalize(data, "domain", "example.com")

        self.assertTrue(main.has_usable_data(normalized))
        self.assertTrue(any("⚠️ Домен связан с малварью" in obs
                            for obs in normalized["observations"]))

    def test_maigret_metadata_merges_with_sherlock_site(self):
        data = {
            "sherlock": {
                "username": "alice",
                "found": [{"site": "GitHub", "url": "https://github.com/alice"}],
            },
            "maigret": {
                "username": "alice",
                "found": [{
                    "site": "GitHub",
                    "url": "https://github.com/alice",
                    "data": {"fullname": "Alice", "bio": "hello"},
                }],
            },
        }
        normalized = main.normalize(data, "username", "alice")

        github = [
            site for site in normalized["sites"]
            if site["url"] == "https://github.com/alice"
        ]
        self.assertEqual(len(github), 1)
        self.assertEqual(github[0]["data"]["fullname"], "Alice")


class TestRunCycle(unittest.TestCase):
    @mock.patch("main.filter_sites")
    @mock.patch("main.collect_by_email")
    def test_no_data_skips_filter(self, collect, filter_mock):
        collect.return_value = {
            "holehe": {
                "email": "target@example.com",
                "found": [],
                "rate_limited": ["github.com"],
            }
        }

        with mock.patch("builtins.print"):
            result = main.run_cycle("email", "target@example.com")

        self.assertIsNone(result)
        filter_mock.assert_not_called()

    def test_save_report_depth_and_parent(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(main, "OUTPUT_DIR", tmp):
                path = main.save_report(
                    "target@example.com",
                    {"holehe": {}},
                    {"kept": []},
                    {"input_type": "email", "summary": "test"},
                    parent_report="/tmp/parent.json",
                    depth=2,
                )

                with open(path, "r", encoding="utf-8") as handle:
                    report = json.load(handle)

        self.assertEqual(report["depth"], 2)
        self.assertEqual(report["parent_report"], "/tmp/parent.json")
        self.assertEqual(report["analysis"]["input_type"], "email")


class TestPivot(unittest.TestCase):
    def test_extracts_email_and_telegram(self):
        analysis = {
            "summary": "Contact target@person.com or https://t.me/SomeChannel",
            "entities": [
                {"type": "email", "value": "other@company.org"},
                {"type": "url", "value": "https://t.me/anotherchan"},
            ],
            "connections": [
                {
                    "entity_a": "target@person.com",
                    "entity_b": "@SomeChannel",
                    "reasoning": "same handle",
                }
            ],
        }

        candidates = main.extract_pivot_candidates(analysis)
        values = {item["value"] for item in candidates}

        self.assertIn("target@person.com", values)
        self.assertIn("other@company.org", values)
        self.assertIn("SomeChannel", values)
        self.assertIn("anotherchan", values)

    def test_placeholder_emails_are_ignored(self):
        analysis = {"summary": "user@example.com and real@person.org"}
        candidates = main.extract_pivot_candidates(analysis)
        values = {item["value"] for item in candidates}

        self.assertNotIn("user@example.com", values)
        self.assertIn("real@person.org", values)

    def test_reserved_telegram_paths_are_ignored(self):
        analysis = {"summary": "https://t.me/joinchat/abc https://t.me/realchannel"}
        candidates = main.extract_pivot_candidates(analysis)
        values = {item["value"] for item in candidates}

        self.assertNotIn("joinchat", values)
        self.assertIn("realchannel", values)

    def test_recursive_pivot_passes_parent_and_depth(self):
        analysis = {"summary": "contact target@person.com"}
        visited = set()

        with mock.patch("main.run_cycle", return_value={
            "analysis": {}, "path": "/tmp/child.json", "data": {}, "filtered": {},
        }) as run_cycle, \
             mock.patch("main._ask_yes_no", return_value=True), \
             mock.patch("builtins.print"):
            main.run_recursive_pivot(
                analysis,
                depth=0,
                parent_report="/tmp/root.json",
                visited=visited,
            )

        run_cycle.assert_called_once_with(
            "email",
            "target@person.com",
            parent_report="/tmp/root.json",
            depth=1,
        )

    def test_recursive_pivot_stops_at_max_depth(self):
        analysis = {"summary": "contact target@person.com"}

        with mock.patch("main.run_cycle") as run_cycle, \
             mock.patch("builtins.print"):
            main.run_recursive_pivot(
                analysis,
                depth=main.MAX_PIVOT_DEPTH,
                parent_report="/tmp/root.json",
                visited=set(),
            )

        run_cycle.assert_not_called()

    def test_visited_entities_are_not_repeated(self):
        analysis = {"summary": "contact target@person.com"}
        visited = {"email:target@person.com"}

        with mock.patch("main.run_cycle") as run_cycle, \
             mock.patch("main._ask_yes_no", return_value=True), \
             mock.patch("builtins.print"):
            main.run_recursive_pivot(
                analysis,
                depth=0,
                parent_report="/tmp/root.json",
                visited=visited,
            )

        run_cycle.assert_not_called()


class TestAnalyzeFiltered(unittest.TestCase):
    def test_observations_are_sent_to_llm(self):
        normalized = {
            "input_type": "domain",
            "input_value": "example.com",
            "nicks": [],
            "emails": ["john@example.com"],
            "observations": ["⚠️ Домен связан с малварью: Emotet"],
            "sites": [],
        }
        filtered = {"kept": []}

        captured = {}

        def fake_call(prompt, user_content, timeout=600, **kwargs):
            captured["content"] = user_content
            return {"summary": "ok"}

        with mock.patch("main._call_llm", side_effect=fake_call):
            analysis = main.analyze_filtered(normalized, filtered)

        self.assertEqual(analysis["summary"], "ok")
        self.assertIn("Emotet", captured["content"])
        self.assertIn("john@example.com", captured["content"])


if __name__ == "__main__":
    unittest.main()
