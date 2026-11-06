import tempfile
import unittest
from pathlib import Path

from panel import sources


class ClassifyTest(unittest.TestCase):
    def test_kinds(self):
        cases = {
            "digest_2026-11-05": ("day", "2026-11-05", 1),
            "digest_2026-11-05_v2": ("day", "2026-11-05", 2),
            "digest_2026-11-w1": ("week", "2026-11-w1", 1),
            "digest_2026-10": ("month", "2026-10", 1),
            "digest_2026-Q3": ("quarter", "2026-Q3", 1),
            "digest_2026-H1": ("half", "2026-H1", 1),
            "digest_2026-ytd-11-05": ("ytd", "2026-11-05", 1),
            "digest_2026-11-01_05": ("range", "2026-11-05", 1),
        }
        for stem, want in cases.items():
            self.assertEqual(sources.classify(stem), want, stem)


class TasksTest(unittest.TestCase):
    def test_extract(self):
        body = (
            "<b>Дайджест · 5 ноября</b>\n\n• не задача\n\n"
            "<b>Решить / с кем поговорить</b>\n"
            "• <b>Иван</b>: проверить отгрузки.\n"
            "• <b>Мария + Иван:</b> карточки без фото.\n\n"
            "<i>Источник: …</i>\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            out.mkdir()
            (out / "digest_2026-11-05.html").write_text(body, encoding="utf-8")
            [d] = sources.load_digests(Path(tmp))
        team = [{"name": "Иван", "match": ["Иван"]}, {"name": "Мария", "match": ["Мари"]}]
        tasks = sources.extract_tasks(d, team)
        self.assertEqual(len(tasks), 2)
        self.assertEqual(tasks[0].people, ["Иван"])
        self.assertEqual(tasks[1].people, ["Иван", "Мария"])
        self.assertEqual(d.title, "Дайджест · 5 ноября")


if __name__ == "__main__":
    unittest.main()
