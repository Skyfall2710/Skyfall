# tests/test_investigations.py — tests for "live" investigations.
#
# They check the graph store (nodes, edges, notes), the import of search
# results, and saving an HTML page. They do not access the network.

import os
import tempfile
import unittest
from unittest import mock

import investigations


class InvestigationsTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.inv_dir = os.path.join(self.tmp.name, "investigations")
        self.pages_dir = os.path.join(self.tmp.name, "saved_pages")
        os.makedirs(self.inv_dir)
        os.makedirs(self.pages_dir)

        self.patches = [
            mock.patch.object(investigations, "INVESTIGATIONS_DIR", self.inv_dir),
            mock.patch.object(investigations, "SAVED_PAGES_DIR", self.pages_dir),
        ]
        for patch in self.patches:
            patch.start()
            self.addCleanup(patch.stop)


class TestStorage(InvestigationsTestBase):
    def test_create_list_rename_delete(self):
        inv = investigations.create_investigation("Первый")
        self.assertTrue(inv["id"].startswith("inv_"))
        self.assertEqual(inv["nodes"], [])

        items = investigations.list_investigations()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "Первый")
        self.assertEqual(items[0]["node_count"], 0)

        renamed = investigations.update_investigation(inv["id"], "Второй")
        self.assertEqual(renamed["title"], "Второй")

        self.assertTrue(investigations.delete_investigation(inv["id"]))
        self.assertEqual(investigations.list_investigations(), [])

    def test_invalid_id_does_not_escape_directory(self):
        with self.assertRaises(ValueError):
            investigations.load_investigation("../secret")


class TestNodes(InvestigationsTestBase):
    def setUp(self):
        super().setUp()
        self.inv = investigations.create_investigation("Тест")

    def test_add_node_numbers_and_dedupes(self):
        node, created = investigations.add_node(
            self.inv, label="target@example.com", type="email", url="https://a.example/u",
        )
        self.assertTrue(created)
        self.assertEqual(node["num"], 1)
        self.assertEqual(node["type"], "email")

        same, created_again = investigations.add_node(
            self.inv, label="target@example.com", type="email", notes="заметка",
        )
        self.assertFalse(created_again)
        self.assertEqual(same["id"], node["id"])
        self.assertEqual(same["notes"], "заметка")

        other, _ = investigations.add_node(self.inv, label="site", type="url")
        self.assertEqual(other["num"], 2)

    def test_update_node_and_delete_cascades_edges(self):
        a, _ = investigations.add_node(self.inv, label="A", type="nick")
        b, _ = investigations.add_node(self.inv, label="B", type="url")
        edge, created = investigations.add_edge(self.inv, source=a["id"], target=b["id"])
        self.assertTrue(created)

        investigations.update_node(self.inv, a["id"], {"notes": "важное", "url": "https://x"})
        node = next(node for node in self.inv["nodes"] if node["id"] == a["id"])
        self.assertEqual(node["notes"], "важное")
        self.assertEqual(node["url"], "https://x")

        self.assertTrue(investigations.delete_node(self.inv, a["id"]))
        self.assertEqual([node["label"] for node in self.inv["nodes"]], ["B"])
        self.assertEqual(self.inv["edges"], [])
        self.assertEqual(edge["target"], b["id"])

    def test_urls_are_sanitized(self):
        bad, _ = investigations.add_node(
            self.inv, label="bad", type="custom", url="javascript:alert(1)",
        )
        self.assertEqual(bad["url"], "")

        good, _ = investigations.add_node(
            self.inv, label="good", type="custom", url="example.com/profile",
        )
        self.assertEqual(good["url"], "https://example.com/profile")

    def test_self_loop_and_missing_node_are_rejected(self):
        a, _ = investigations.add_node(self.inv, label="A", type="nick")
        with self.assertRaises(ValueError):
            investigations.add_edge(self.inv, source=a["id"], target=a["id"])
        with self.assertRaises(ValueError):
            investigations.add_edge(self.inv, source=a["id"], target="n_missing")

    def test_duplicate_edge_is_reused(self):
        a, _ = investigations.add_node(self.inv, label="A", type="nick")
        b, _ = investigations.add_node(self.inv, label="B", type="url")
        first, created = investigations.add_edge(
            self.inv, source=a["id"], target=b["id"], confidence="low",
        )
        self.assertTrue(created)
        second, created_again = investigations.add_edge(
            self.inv, source=b["id"], target=a["id"], confidence="high", notes="связь",
        )
        self.assertFalse(created_again)
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(second["confidence"], "high")
        self.assertEqual(second["notes"], "связь")


class TestImport(InvestigationsTestBase):
    def make_result(self, input_value="sudzuya", input_type="username"):
        return {
            "input": input_value,
            "input_type": input_type,
            "report_path": "/tmp/report.json",
            "filtered": {
                "kept": [
                    {"site": "7Cups", "url": "https://www.7cups.com/@sudzuya"},
                    {"site": "TikTok", "url": "https://www.tiktok.com/@sudzuya"},
                ],
            },
            "analysis": {
                "entities": [
                    {"type": "nick", "value": input_value, "found_in": ["7Cups"]},
                    {"type": "url", "value": "7Cups", "found_in": ["7Cups"]},
                ],
                "connections": [
                    {
                        "entity_a": input_value,
                        "entity_b": "7Cups",
                        "confidence": "medium",
                        "evidence": "https://www.7cups.com/@sudzuya",
                    },
                ],
            },
        }

    def test_first_search_becomes_center_with_sources(self):
        inv = investigations.create_investigation("Тест")
        out = investigations.import_search(inv, self.make_result())
        inv = out["investigation"]

        root = next(node for node in inv["nodes"] if node["role"] == "input")
        self.assertEqual(root["type"], "center")
        self.assertEqual(root["label"], "sudzuya")
        self.assertIn("7cups.com", root["url"])

        site = next(node for node in inv["nodes"] if node["label"] == "7Cups")
        self.assertEqual(site["type"], "url")
        self.assertEqual(site["url"], "https://www.7cups.com/@sudzuya")
        self.assertEqual(len(inv["edges"]), 1)
        self.assertEqual(len(inv["searches"]), 1)
        self.assertEqual(inv["searches"][0]["input"], "sudzuya")

    def test_second_search_is_linked_to_existing_node(self):
        inv = investigations.create_investigation("Цепочка")
        first = investigations.import_search(inv, self.make_result())["investigation"]
        root_id = first["nodes"][0]["id"]

        second = investigations.import_search(
            first,
            self.make_result("sudzuya@example.com", "email"),
            link_to=root_id,
        )["investigation"]

        inputs = [node for node in second["nodes"] if node["role"] == "input"]
        self.assertEqual(len(inputs), 2)
        new_root = next(node for node in inputs if node["label"] == "sudzuya@example.com")
        self.assertEqual(new_root["type"], "email")

        manual = [
            edge for edge in second["edges"]
            if edge["origin"] == "Связано вручную при импорте"
        ]
        self.assertEqual(len(manual), 1)
        self.assertEqual(manual[0]["confidence"], "high")
        self.assertEqual(second["searches"][-1]["input"], "sudzuya@example.com")

    def test_repeated_search_does_not_duplicate_root(self):
        inv = investigations.create_investigation("Повтор")
        inv = investigations.import_search(inv, self.make_result())["investigation"]
        nodes_before = len(inv["nodes"])
        edges_before = len(inv["edges"])

        inv = investigations.import_search(inv, self.make_result())["investigation"]
        self.assertEqual(len(inv["nodes"]), nodes_before)
        self.assertEqual(len(inv["edges"]), edges_before)

    def test_positions_are_saved(self):
        inv = investigations.create_investigation("Позиции")
        inv = investigations.import_search(inv, self.make_result())["investigation"]
        node_id = inv["nodes"][0]["id"]

        updated = investigations.set_positions(inv, {node_id: {"x": 123.5, "y": -40}})
        self.assertEqual(updated, 1)
        investigations.save_investigation(inv)
        saved = investigations.load_investigation(inv["id"])
        node = next(node for node in saved["nodes"] if node["id"] == node_id)
        self.assertEqual((node["x"], node["y"]), (123.5, -40))


class TestSavePage(InvestigationsTestBase):
    def test_html_page_is_written_inside_pages_dir(self):
        inv = investigations.create_investigation("Страница")
        saved = investigations.save_page(inv, "<html><body>ok</body></html>", title="Отчёт")
        self.assertTrue(saved["filename"].endswith(".html"))
        self.assertEqual(os.path.dirname(saved["path"]), self.pages_dir)
        with open(saved["path"], "r", encoding="utf-8") as handle:
            self.assertIn("ok", handle.read())

        self.assertEqual(investigations.list_saved_pages()[0]["filename"], saved["filename"])
        self.assertEqual(investigations.saved_page_path(saved["filename"]), saved["path"])

    def test_empty_page_and_traversal_are_rejected(self):
        inv = investigations.create_investigation("Страница")
        with self.assertRaises(ValueError):
            investigations.save_page(inv, "   ")
        with self.assertRaises(ValueError):
            investigations.saved_page_path("../secret.html")
        with self.assertRaises(LookupError):
            investigations.saved_page_path("missing.html")


if __name__ == "__main__":
    unittest.main()
