# tests/test_ai_modes.py — Raw Mode, cloud LLMs, JSON repair, and logging.

import json
import os
import tempfile
import unittest
from unittest import mock

import asyncio
import re
from pathlib import Path

import config
import logger
import main
import app as app_module
import web_i18n
from api_models import InvestigateRequest


def sample_username_data():
    return {
        "sherlock": {
            "username": "alice",
            "found": [
                {"site": "GitHub", "url": "https://github.com/alice"},
                {"site": "TikTok", "url": "https://www.tiktok.com/@alice"},
                {"site": "Pastebin", "url": "https://pastebin.com/u/alice"},
            ],
        },
        "maigret": {
            "username": "alice",
            "found": [
                {
                    "site": "GitHub",
                    "url": "https://github.com/alice",
                    "data": {"fullname": "Alice", "bio": "dev"},
                },
            ],
        },
    }


def sample_normalized():
    return main.normalize(sample_username_data(), "username", "alice")


class TestRawMode(unittest.TestCase):
    def test_raw_filtered_keeps_all_sites(self):
        normalized = sample_normalized()
        filtered = main.raw_filtered(normalized)

        self.assertEqual(len(filtered["kept"]), len(normalized["sites"]))
        self.assertEqual(filtered["dropped"], [])
        self.assertEqual(filtered["mode"], "raw")
        self.assertIn("Raw Mode", filtered["thinking"])

    def test_raw_analysis_has_required_structure(self):
        normalized = sample_normalized()
        filtered = main.raw_filtered(normalized)
        analysis = main.raw_analysis(normalized, filtered)

        self.assertEqual(analysis["summary"], "Режим без AI (Raw Mode)")
        self.assertEqual(analysis["input_value"], "alice")
        self.assertTrue(analysis["entities"])
        self.assertTrue(analysis["connections"])
        self.assertEqual(analysis["mode"], "raw")
        self.assertIsInstance(analysis["tree"], dict)

    def test_run_cycle_raw_mode_skips_llm(self):
        old_use_ai = config.USE_AI
        config.USE_AI = False
        self.addCleanup(setattr, config, "USE_AI", old_use_ai)

        with mock.patch.object(main, "collect_by_username", return_value=sample_username_data()), \
             mock.patch.object(main, "filter_sites") as filter_mock, \
             mock.patch.object(main, "analyze_filtered") as analyze_mock, \
             mock.patch.object(main, "save_report", return_value="/tmp/report.json"), \
             mock.patch("builtins.print"):
            result = main.run_cycle("username", "alice")

        filter_mock.assert_not_called()
        analyze_mock.assert_not_called()
        self.assertFalse(result["ai_used"])
        self.assertEqual(result["analysis"]["mode"], "raw")
        self.assertEqual(result["analysis"]["summary"], "Режим без AI (Raw Mode)")

    def test_run_cycle_falls_back_when_filter_fails(self):
        with mock.patch.object(main, "collect_by_username", return_value=sample_username_data()), \
             mock.patch.object(main, "filter_sites", return_value={"error": "timeout"}), \
             mock.patch.object(main, "analyze_filtered") as analyze_mock, \
             mock.patch.object(main, "save_report", return_value="/tmp/report.json"), \
             mock.patch("builtins.print"):
            result = main.run_cycle("username", "alice")

        analyze_mock.assert_not_called()
        self.assertFalse(result["ai_used"])
        self.assertEqual(result["analysis"]["mode"], "raw_fallback")
        self.assertTrue(result["filtered"]["kept"])
        self.assertIn("timeout", result["analysis"]["notice"])


    def test_run_cycle_falls_back_when_analysis_fails(self):
        with mock.patch.object(main, "collect_by_username", return_value=sample_username_data()), \
             mock.patch.object(main, "filter_sites", return_value={"kept": [
                 {"site": "GitHub", "url": "https://github.com/alice", "weight": "strong"}
             ]}), \
             mock.patch.object(main, "analyze_filtered", return_value={"error": "timeout"}), \
             mock.patch.object(main, "save_report", return_value="/tmp/report.json"), \
             mock.patch("builtins.print"):
            result = main.run_cycle("username", "alice")

        self.assertFalse(result["ai_used"])
        self.assertEqual(result["analysis"]["mode"], "raw_fallback")
        self.assertTrue(result["analysis"]["entities"])
        self.assertIn("timeout", result["analysis"]["notice"])


class TestCompactFiltering(unittest.TestCase):
    def test_keep_indices_are_expanded_with_data(self):
        normalized = sample_normalized()

        with mock.patch.object(
            main, "_call_llm",
            return_value={"keep": [1, 2], "thinking": "оставляем главное"},
        ):
            filtered = main.filter_sites(normalized)

        self.assertEqual(filtered["thinking"], "оставляем главное")
        self.assertGreaterEqual(len(filtered["kept"]), 2)
        github = next(item for item in filtered["kept"] if item["site"] == "GitHub")
        self.assertEqual(github["data"]["fullname"], "Alice")
        self.assertTrue(filtered["dropped"])

    def test_legacy_full_kept_format_is_supported(self):
        normalized = sample_normalized()
        with mock.patch.object(
            main, "_call_llm",
            return_value={
                "thinking": "ok",
                "kept": [{"site": "GitHub", "url": "https://github.com/alice",
                          "weight": "strong", "reason": "metadata"}],
            },
        ):
            filtered = main.filter_sites(normalized)

        self.assertGreaterEqual(len(filtered["kept"]), 1)
        self.assertIn("GitHub", [item["site"] for item in filtered["kept"]])

    def test_empty_keep_uses_local_candidates(self):
        normalized = sample_normalized()
        with mock.patch.object(main, "_call_llm", return_value={"keep": [], "thinking": "x"}):
            filtered = main.filter_sites(normalized)

        self.assertTrue(filtered["kept"])
        self.assertIn("локально", filtered["thinking"].lower())
        kept_names = {item["site"].lower() for item in filtered["kept"]}
        dropped_names = {item["site"].lower() for item in filtered["dropped"]}
        self.assertFalse(kept_names & dropped_names)

    def test_analysis_merges_local_entities(self):
        normalized = sample_normalized()
        filtered = main.raw_filtered(normalized)
        llm_result = {
            "summary": "Alice found on GitHub",
            "thinking": "ok",
            "connections": [
                {"entity_a": "alice", "entity_b": "GitHub",
                 "confidence": "high", "evidence": "url", "reasoning": "same"},
            ],
        }
        with mock.patch.object(main, "_call_llm", return_value=llm_result):
            analysis = main.analyze_filtered(normalized, filtered)

        self.assertEqual(analysis["summary"], "Alice found on GitHub")
        self.assertEqual(analysis["mode"], "ai")
        values = {entity["value"] for entity in analysis["entities"]}
        self.assertIn("alice", values)
        self.assertIn("GitHub", values)
        self.assertTrue(analysis["connections"])


class TestJsonExtraction(unittest.TestCase):
    def test_markdown_fenced_json(self):
        parsed = main._extract_json('```json\n{"a": 1, "b": [2, 3]}\n```')
        self.assertEqual(parsed, {"a": 1, "b": [2, 3]})

    def test_json_with_text_around_it(self):
        parsed = main._extract_json('Here is the result:\n{"summary": "ok"}\nDone.')
        self.assertEqual(parsed["summary"], "ok")

    def test_truncated_json_is_repaired(self):
        parsed = main._extract_json('{"a": 1, "b": [2, 3')
        self.assertEqual(parsed["a"], 1)
        self.assertEqual(parsed["b"], [2, 3])

    def test_invalid_json_returns_error(self):
        parsed = main._extract_json("not json at all")
        self.assertIn("error", parsed)


class TestCloudLLM(unittest.TestCase):
    def setUp(self):
        self.patches = [
            mock.patch.object(config, "LLM_PROVIDER", "openai"),
            mock.patch.object(config, "OPENAI_API_KEY", "sk-test"),
            mock.patch.object(config, "OPENAI_BASE_URL", "https://api.example/v1"),
            mock.patch.object(config, "OPENAI_MODEL", "gpt-test"),
        ]
        for patch in self.patches:
            patch.start()
            self.addCleanup(patch.stop)

    @mock.patch("main.requests.post")
    def test_openai_request_and_response(self, post):
        response = mock.Mock()
        response.status_code = 200
        response.json.return_value = {
            "choices": [{"message": {"content": '```json\n{"summary": "ok"}\n```'}}],
        }
        post.return_value = response

        result = main._call_llm("system", "user", timeout=5, purpose="analyze")

        self.assertEqual(result["summary"], "ok")
        args, kwargs = post.call_args
        self.assertEqual(args[0], "https://api.example/v1/chat/completions")
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer sk-test")
        messages = kwargs["json"]["messages"]
        self.assertEqual(messages[0], {"role": "system", "content": "system"})
        self.assertEqual(messages[1], {"role": "user", "content": "user"})
        self.assertEqual(kwargs["json"]["model"], "gpt-test")

    @mock.patch("main.requests.post")
    def test_openai_http_error_is_returned(self, post):
        response = mock.Mock()
        response.status_code = 401
        response.text = '{"error": {"message": "bad key"}}'
        response.json.return_value = {"error": {"message": "bad key"}}
        post.return_value = response

        result = main._call_llm("system", "user", timeout=5)
        self.assertIn("error", result)
        self.assertIn("bad key", result["error"])

    def test_missing_key(self):
        with mock.patch.object(config, "OPENAI_API_KEY", ""):
            result = main._call_llm("system", "user", timeout=5)
        self.assertIn("OPENAI_API_KEY", result["error"])


class TestOllamaCall(unittest.TestCase):
    def setUp(self):
        self.patch = mock.patch.object(config, "LLM_PROVIDER", "ollama")
        self.patch.start()
        self.addCleanup(self.patch.stop)

    @mock.patch("main.requests.post")
    def test_ollama_body_and_parse(self, post):
        response = mock.Mock()
        response.status_code = 200
        response.json.return_value = {
            "response": '{"keep": [1]}',
            "eval_count": 10,
            "prompt_eval_count": 50,
            "load_duration": 2,
        }
        post.return_value = response

        result = main._call_llm("system", "user", timeout=5, purpose="filter")

        self.assertEqual(result["keep"], [1])
        _, kwargs = post.call_args
        self.assertEqual(kwargs["json"]["model"], config.OLLAMA_MODEL)
        self.assertEqual(kwargs["json"]["options"]["num_predict"], 200)
        self.assertEqual(kwargs["json"]["options"]["num_ctx"], config.OLLAMA_NUM_CTX)


class TestCloudHealth(unittest.TestCase):
    @mock.patch.object(app_module.requests, "get")
    def test_cloud_health_available(self, get_mock):
        get_mock.return_value = mock.Mock(status_code=200)
        with mock.patch.object(config, "LLM_PROVIDER", "openai"), \
             mock.patch.object(config, "OPENAI_API_KEY", "sk-test"), \
             mock.patch.object(config, "OPENAI_BASE_URL", "https://api.example/v1"), \
             mock.patch.object(config, "OPENAI_MODEL", "gpt-test"):
            health = asyncio.run(app_module.health())

        self.assertEqual(health.llm_provider, "openai")
        self.assertEqual(health.llm_model, "gpt-test")
        self.assertTrue(health.llm_available)
        get_mock.assert_called_once()
        self.assertIn("Authorization", get_mock.call_args.kwargs["headers"])

    def test_cloud_health_without_key(self):
        with mock.patch.object(config, "LLM_PROVIDER", "openai"), \
             mock.patch.object(config, "OPENAI_API_KEY", ""):
            health = asyncio.run(app_module.health())
        self.assertFalse(health.llm_available)


class TestApiRawMode(unittest.TestCase):
    def test_api_use_ai_false_skips_llm(self):
        with mock.patch.object(
            app_module, "collect_by_username", return_value=sample_username_data(),
        ), mock.patch.object(app_module, "filter_sites") as filter_mock, \
             mock.patch.object(app_module, "analyze_filtered") as analyze_mock, \
             mock.patch.object(app_module, "save_report", return_value="/tmp/report.json"):
            payload = asyncio.run(app_module.investigate(InvestigateRequest(
                input_type="username",
                value="alice",
                language="ru",
                use_ai=False,
            )))

        self.assertFalse(payload.ai_used)
        self.assertEqual(payload.mode, "raw")
        self.assertEqual(payload.analysis["summary"], "Режим без AI (Raw Mode)")
        filter_mock.assert_not_called()
        analyze_mock.assert_not_called()


class TestLLMSettings(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "llm_settings.json")
        self.originals = {
            key: getattr(config, key)
            for key in (
                "LLM_PROVIDER", "OPENAI_API_KEY", "OPENAI_BASE_URL",
                "OPENAI_MODEL", "OLLAMA_MODEL", "SETTINGS_FILE",
            )
        }
        config.SETTINGS_FILE = self.path
        self.addCleanup(self._restore)

    def _restore(self):
        for key, value in self.originals.items():
            setattr(config, key, value)

    def test_save_cloud_settings_and_mask_key(self):
        settings = config.update_llm_settings({
            "provider": "openai",
            "api_key": "sk-test-123456",
            "base_url": "https://api.example/v1",
            "model": "gpt-test",
        })

        self.assertEqual(config.LLM_PROVIDER, "openai")
        self.assertEqual(config.OPENAI_MODEL, "gpt-test")
        self.assertEqual(config.OPENAI_BASE_URL, "https://api.example/v1")
        self.assertTrue(settings["has_api_key"])
        self.assertNotIn("sk-test-123456", json.dumps(settings))
        self.assertTrue(os.path.isfile(self.path))
        self.assertEqual(os.stat(self.path).st_mode & 0o777, 0o600)

    def test_cloud_requires_key(self):
        config.OPENAI_API_KEY = ""
        with self.assertRaises(ValueError):
            config.update_llm_settings({"provider": "openai", "model": "gpt-test"})

    def test_empty_key_keeps_existing(self):
        config.OPENAI_API_KEY = "sk-existing"
        config.update_llm_settings({
            "provider": "openai",
            "api_key": "",
            "base_url": "https://api.example/v1",
            "model": "gpt-test",
        })
        self.assertEqual(config.OPENAI_API_KEY, "sk-existing")

    def test_clear_api_key(self):
        config.OPENAI_API_KEY = "sk-existing"
        settings = config.update_llm_settings({
            "provider": "ollama",
            "clear_api_key": True,
        })
        self.assertFalse(settings["has_api_key"])
        self.assertEqual(config.OPENAI_API_KEY, "")

    def test_ollama_model_update(self):
        settings = config.update_llm_settings({
            "provider": "ollama",
            "model": "qwen2.5:3b",
        })
        self.assertEqual(settings["provider"], "ollama")
        self.assertEqual(config.OLLAMA_MODEL, "qwen2.5:3b")


class TestWebI18n(unittest.TestCase):
    def test_known_strings_are_translated(self):
        self.assertEqual(
            web_i18n.translate("Куда добавить результат", "en"),
            "Where to add the result",
        )
        self.assertEqual(
            web_i18n.translate("Куда добавить результат", "ru"),
            "Куда добавить результат",
        )
        self.assertEqual(web_i18n.translate("unknown", "en"), "unknown")

    def test_every_template_and_js_key_exists(self):
        root = Path(__file__).resolve().parents[1]
        html = (root / "templates" / "index.html").read_text(encoding="utf-8")
        js = (root / "static" / "app.js").read_text(encoding="utf-8")
        keys = set(re.findall(r"wt\('([^']*)'\)", html))
        keys |= set(re.findall(r"\btr\('([^']*)'\)", js))
        keys |= set(re.findall(r"\btf\('([^']*)'", js))
        missing = sorted(key for key in keys if key not in web_i18n.WEB_EN)
        self.assertEqual(missing, [])


class TestLogger(unittest.TestCase):
    def test_get_logger_writes_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"OSINT_LOG_DIR": tmp}):
                logger.reset_for_tests()
                log = logger.get_logger("test.module")
                log.info("hello from test")
                path = logger.log_file()
                self.assertIsNotNone(path)
                self.assertTrue(path.exists())
                text = path.read_text(encoding="utf-8")
                self.assertIn("[INFO] test.module: hello from test", text)
                logger.reset_for_tests()


if __name__ == "__main__":
    unittest.main()
