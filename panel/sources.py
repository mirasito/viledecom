"""Чтение данных для панели: дайджесты, запуски, запросы, агенты, команда, задачи.

Все функции работают только со стандартной библиотекой и не ходят в сеть.
Данные лежат вне репозитория (репозиторий публичный): каталог дайджеста
(`--digest-dir`, по умолчанию /mnt/project-files/ecom-digest) и каталог
настроек панели (`--config-dir`).
"""
from __future__ import annotations

import ast
import dataclasses
import datetime as dt
import hashlib
import html
import json
import re
from pathlib import Path

MONTHS = {
    "01": "январь", "02": "февраль", "03": "март", "04": "апрель", "05": "май", "06": "июнь",
    "07": "июль", "08": "август", "09": "сентябрь", "10": "октябрь", "11": "ноябрь", "12": "декабрь",
}

KIND_LABELS = {
    "day": "Дневной",
    "week": "Недельный",
    "month": "Месячный",
    "quarter": "Квартальный",
    "half": "Полугодовой",
    "year": "Годовой",
    "range": "За период",
    "ytd": "С начала года",
    "other": "Другое",
}


# --------------------------------------------------------------------------- дайджесты

@dataclasses.dataclass
class Digest:
    slug: str            # имя файла без расширения
    path: Path
    kind: str            # day / week / month / ...
    period: str          # ключ периода для сортировки, напр. 2026-11-05
    version: int         # _v2 → 2
    title: str           # первая строка без тегов
    body: str            # Telegram HTML как есть
    saved_at: dt.datetime

    @property
    def kind_label(self) -> str:
        return KIND_LABELS.get(self.kind, self.kind)


_PATTERNS = [
    (re.compile(r"^(\d{4})-ytd-(\d{2})-(\d{2})$"), "ytd", lambda m: f"{m[1]}-{m[2]}-{m[3]}"),
    (re.compile(r"^(\d{4})-(\d{2})-(\d{2})_(\d{2})$"), "range", lambda m: f"{m[1]}-{m[2]}-{m[4]}"),
    (re.compile(r"^(\d{4})-(\d{2})-(\d{2})$"), "day", lambda m: m[0]),
    (re.compile(r"^(\d{4})-(\d{2})-w(\d)$"), "week", lambda m: f"{m[1]}-{m[2]}-w{m[3]}"),
    (re.compile(r"^(\d{4})-W(\d{2})$"), "week", lambda m: m[0]),
    (re.compile(r"^(\d{4})-(\d{2})$"), "month", lambda m: m[0]),
    (re.compile(r"^(\d{4})-Q(\d)$"), "quarter", lambda m: m[0]),
    (re.compile(r"^(\d{4})-H(\d)$"), "half", lambda m: m[0]),
    (re.compile(r"^(\d{4})$"), "year", lambda m: m[0]),
]


def classify(stem: str) -> tuple[str, str, int]:
    """digest_2026-11-05_v2 → ('day', '2026-11-05', 2)."""
    name = stem.removeprefix("digest_")
    version = 1
    m = re.search(r"_v(\d+)$", name)
    if m:
        version = int(m[1])
        name = name[: m.start()]
    for rx, kind, key in _PATTERNS:
        m = rx.match(name)
        if m:
            return kind, key(m), version
    return "other", name, version


def strip_tags(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", s)).strip()


def load_digests(digest_dir: Path) -> list[Digest]:
    out_dir = digest_dir / "out"
    items = []
    for p in sorted(out_dir.glob("digest_*.html")):
        body = p.read_text(encoding="utf-8")
        first = next((ln for ln in body.splitlines() if ln.strip()), p.stem)
        kind, period, version = classify(p.stem)
        items.append(Digest(
            slug=p.stem,
            path=p,
            kind=kind,
            period=period,
            version=version,
            title=strip_tags(first),
            body=body,
            saved_at=dt.datetime.fromtimestamp(p.stat().st_mtime, dt.timezone.utc),
        ))
    items.sort(key=lambda d: (d.saved_at, d.version), reverse=True)
    return items


# --------------------------------------------------------------------------- задачи из дайджестов

@dataclasses.dataclass
class Task:
    id: str
    text: str            # HTML (безопасный Telegram-набор тегов)
    people: list[str]
    source: str          # slug дайджеста или 'manual'
    created: str         # YYYY-MM-DD
    status: str = "open" # open / doing / done


_TASK_HEADER = re.compile(r"решить|с кем поговорить", re.I)


def extract_tasks(d: Digest, team: list[dict]) -> list[Task]:
    """Пункты «• …» из блока «Решить / с кем поговорить», с привязкой к людям."""
    tasks, inside = [], False
    for line in d.body.splitlines():
        plain = strip_tags(line)
        if _TASK_HEADER.search(plain) and not plain.startswith("•"):
            inside = True
            continue
        if not inside:
            continue
        if plain.startswith("•"):
            people = [m["name"] for m in team if any(stem.lower() in plain.lower() for stem in m.get("match", [m["name"]]))]
            text = line.strip().lstrip("•").strip()
            tid = hashlib.sha1(f"{d.slug}|{plain}".encode()).hexdigest()[:10]
            tasks.append(Task(id=tid, text=text, people=people, source=d.slug,
                              created=d.saved_at.date().isoformat()))
        elif plain == "" and tasks:
            break
        elif plain and not plain.startswith("•") and tasks:
            break
    return tasks


def load_manual_tasks(config_dir: Path) -> tuple[list[Task], dict[str, str]]:
    """tasks.json: {"tasks": [...ручные задачи...], "status": {"<id>": "done", ...}}."""
    p = config_dir / "tasks.json"
    if not p.exists():
        return [], {}
    data = json.loads(p.read_text(encoding="utf-8"))
    manual = [
        Task(id=t.get("id") or hashlib.sha1(t["text"].encode()).hexdigest()[:10],
             text=html.escape(t["text"]), people=t.get("people", []), source="manual",
             created=t.get("created", ""), status=t.get("status", "open"))
        for t in data.get("tasks", [])
    ]
    return manual, data.get("status", {})


# --------------------------------------------------------------------------- запуски

@dataclasses.dataclass
class Run:
    ts: dt.datetime
    agent: str
    status: str          # ok / partial / error / saved
    summary: str
    digests: list[str]


def load_runs(digest_dir: Path, digests: list[Digest]) -> list[Run]:
    """runs.jsonl, если агент его пишет; иначе — восстанавливаем по сохранённым дайджестам."""
    p = digest_dir / "runs.jsonl"
    runs: list[Run] = []
    if p.exists():
        for ln in p.read_text(encoding="utf-8").splitlines():
            if not ln.strip():
                continue
            r = json.loads(ln)
            runs.append(Run(
                ts=dt.datetime.fromisoformat(r["ts"]),
                agent=r.get("agent", "digest"),
                status=r.get("status", "ok"),
                summary=r.get("summary", ""),
                digests=r.get("digests", []),
            ))
    if not runs:
        by_hour: dict[str, list[Digest]] = {}
        for d in digests:
            by_hour.setdefault(d.saved_at.strftime("%Y-%m-%d %H"), []).append(d)
        for group in by_hour.values():
            runs.append(Run(
                ts=max(d.saved_at for d in group),
                agent="digest",
                status="saved",
                summary=", ".join(f"{d.kind_label.lower()} {d.period}" for d in group),
                digests=[d.slug for d in group],
            ))
    runs.sort(key=lambda r: r.ts, reverse=True)
    return runs


# --------------------------------------------------------------------------- запросы

@dataclasses.dataclass
class Query:
    name: str
    database: str
    description: str
    sql: str
    section: str


def load_sections(digest_dir: Path) -> dict[str, tuple[str, ...]]:
    """Словарь SECTIONS из digest.py, без импорта модуля (там зависимости и сеть)."""
    p = digest_dir / "digest.py"
    if not p.exists():
        return {}
    tree = ast.parse(p.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "SECTIONS" for t in node.targets):
            return ast.literal_eval(node.value)
    return {}


def load_queries(digest_dir: Path) -> list[Query]:
    sections = load_sections(digest_dir)
    section_of = {q: s for s, qs in sections.items() for q in qs}
    out = []
    for p in sorted((digest_dir / "queries").glob("*.sql")):
        sql = p.read_text(encoding="utf-8")
        lines = sql.splitlines()
        db, desc = "все базы", []
        for ln in lines:
            if not ln.startswith("--"):
                break
            text = ln[2:].strip()
            if text.lower().startswith("database:"):
                db = text.split(":", 1)[1].strip()
            elif text:
                desc.append(text)
        out.append(Query(name=p.stem, database=db, description=" ".join(desc[:2]),
                         sql=sql, section=section_of.get(p.stem, "Не в дайджесте")))
    return out


# --------------------------------------------------------------------------- настройки

def load_json(config_dir: Path, name: str, default):
    p = config_dir / name
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return default
