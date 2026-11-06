"""Сборка статического сайта панели агентов.

    python -m panel.build --digest-dir /mnt/project-files/ecom-digest \
                          --config-dir /mnt/project-files/agents-panel/config \
                          --out dist

Без внешних зависимостей. Результат — папка с HTML, которую можно выложить на
любой статический хостинг (рекомендуем Cloudflare Pages + Cloudflare Access).
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import shutil
from pathlib import Path

from . import sources

HERE = Path(__file__).parent
ALMATY = dt.timezone(dt.timedelta(hours=5))
NAV = [
    ("index.html", "Обзор"),
    ("agents.html", "Агенты"),
    ("digests.html", "Дайджесты"),
    ("tasks.html", "Задачи"),
    ("runs.html", "Запуски"),
    ("queries.html", "Запросы"),
]
STATUS = {
    "active": ("Работает", "ok"),
    "building": ("В работе", "warn"),
    "planned": ("В плане", "muted"),
    "paused": ("На паузе", "muted"),
    "ok": ("Успешно", "ok"),
    "partial": ("Частично", "warn"),
    "error": ("Ошибка", "bad"),
    "saved": ("Сохранён", "ok"),
    "open": ("Открыта", "warn"),
    "doing": ("В работе", "warn"),
    "done": ("Готово", "ok"),
}

e = html.escape


def fmt_ts(ts: dt.datetime) -> str:
    return ts.astimezone(ALMATY).strftime("%d.%m.%Y %H:%M")


def badge(status: str) -> str:
    label, tone = STATUS.get(status, (status, "muted"))
    return f'<span class="badge {tone}">{e(label)}</span>'


def page(title: str, active: str, content: str, depth: int = 0, built: str = "") -> str:
    up = "../" * depth
    nav = "".join(
        f'<a href="{up}{href}"{" class=on" if href == active else ""}>{e(label)}</a>' for href, label in NAV
    )
    return f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>{e(title)} · Агенты Viled</title>
<link rel="stylesheet" href="{up}style.css">
</head><body>
<header><div class="wrap"><a class="brand" href="{up}index.html">Агенты e-com Viled</a><nav>{nav}</nav></div></header>
<main class="wrap">{content}</main>
<footer class="wrap">Собрано {e(built)} (Алматы). Данные: Metabase через агента дайджестов.</footer>
<script src="{up}app.js"></script>
</body></html>"""


def digest_link(d: sources.Digest, depth: int = 0) -> str:
    return f'<a href="{"../" * depth}digests/{e(d.slug)}.html">{e(d.title)}</a>'


def task_item(t: sources.Task, digests_by_slug: dict, depth: int = 0) -> str:
    who = ", ".join(t.people) or "без ответственного"
    src = digests_by_slug.get(t.source)
    src_html = digest_link(src, depth) if src else "вручную"
    checked = " checked" if t.status == "done" else ""
    return (f'<li class="task" data-id="{e(t.id)}" data-people="{e("|".join(t.people))}">'
            f'<label><input type="checkbox"{checked}> <span class="tg">{t.text}</span></label>'
            f'<div class="meta">{e(who)} · {e(t.created)} · {src_html}</div></li>')


def build(digest_dir: Path, config_dir: Path, out: Path) -> None:
    built = fmt_ts(dt.datetime.now(dt.timezone.utc))
    agents = sources.load_json(config_dir, "agents.json", [])
    team = sources.load_json(config_dir, "team.json", [])
    digests = sources.load_digests(digest_dir)
    by_slug = {d.slug: d for d in digests}
    runs = sources.load_runs(digest_dir, digests)
    queries = sources.load_queries(digest_dir)

    tasks = [t for d in digests for t in sources.extract_tasks(d, team)]
    manual, status_over = sources.load_manual_tasks(config_dir)
    tasks = manual + tasks
    for t in tasks:
        t.status = status_over.get(t.id, t.status)

    if out.exists():
        shutil.rmtree(out)
    (out / "digests").mkdir(parents=True)
    for asset in ("style.css", "app.js"):
        shutil.copy(HERE / "static" / asset, out / asset)

    def write(name: str, title: str, content: str, depth: int = 0) -> None:
        (out / name).write_text(page(title, name if depth == 0 else "digests.html", content, depth, built),
                                encoding="utf-8")

    # ---------------------------------------------------------------- агенты
    def agent_last_run(a: dict):
        return next((r for r in runs if r.agent == a.get("id")), None)

    def agent_card(a: dict) -> str:
        r = agent_last_run(a)
        last = f'{fmt_ts(r.ts)} {badge(r.status)}' if r else "запусков ещё не было"
        owners = ", ".join(a.get("owners", [])) or "—"
        sources_html = "".join(f"<li>{e(s)}</li>" for s in a.get("sources", []))
        return f"""<article class="card">
<div class="row"><h3>{e(a["name"])}</h3>{badge(a.get("status", "planned"))}</div>
<p>{e(a.get("description", ""))}</p>
<dl><dt>Расписание</dt><dd>{e(a.get("schedule", "—"))}</dd>
<dt>Канал</dt><dd>{e(a.get("channel", "—"))}</dd>
<dt>Для кого</dt><dd>{e(owners)}</dd>
<dt>Последний запуск</dt><dd>{last}</dd></dl>
{f'<details><summary>Источники</summary><ul>{sources_html}</ul></details>' if sources_html else ''}
</article>"""

    agents_html = "".join(agent_card(a) for a in agents) or '<p class="muted">Нет agents.json в каталоге настроек.</p>'
    write("agents.html", "Агенты", f"<h1>Агенты</h1><div class=grid>{agents_html}</div>")

    # ---------------------------------------------------------------- дайджесты
    for d in digests:
        content = f"""<p><a href="../digests.html">← Все дайджесты</a></p>
<div class="row"><span class="badge muted">{e(d.kind_label)}</span><span class="muted">сохранён {fmt_ts(d.saved_at)}{f' · версия {d.version}' if d.version > 1 else ''}</span></div>
<article class="tg-message tg">{d.body}</article>"""
        write(f"digests/{d.slug}.html", d.title, content, depth=1)

    kinds = sorted({d.kind for d in digests}, key=list(sources.KIND_LABELS).index)
    filters = '<button class="chip on" data-kind="">Все</button>' + "".join(
        f'<button class="chip" data-kind="{k}">{e(sources.KIND_LABELS[k])}</button>' for k in kinds)
    rows = "".join(
        f'<tr data-kind="{d.kind}"><td>{digest_link(d)}</td><td>{e(d.kind_label)}</td>'
        f'<td>{e(d.period)}</td><td>{fmt_ts(d.saved_at)}</td></tr>' for d in digests)
    write("digests.html", "Дайджесты", f"""<h1>Дайджесты</h1>
<div class="chips" id="kind-filter">{filters}</div>
<table class="list" id="digests"><thead><tr><th>Дайджест</th><th>Тип</th><th>Период</th><th>Сохранён</th></tr></thead>
<tbody>{rows}</tbody></table>""")

    # ---------------------------------------------------------------- задачи
    people = [m["name"] for m in team]
    chips = '<button class="chip on" data-person="">Все</button>' + "".join(
        f'<button class="chip" data-person="{e(p)}">{e(p)}</button>' for p in people)
    team_cards = "".join(
        f'<div class="person"><b>{e(m["name"])}</b><span class="muted">{e(m.get("role", ""))}</span>'
        f'<span class="count" data-count-for="{e(m["name"])}"></span></div>' for m in team)
    write("tasks.html", "Задачи", f"""<h1>Задачи команды</h1>
<p class="muted">Собраны из блока «Решить / с кем поговорить» каждого дайджеста, плюс ручные из tasks.json.
Галочка сохраняется в этом браузере; общий статус задаётся в tasks.json.</p>
<div class="team">{team_cards}</div>
<div class="chips" id="person-filter">{chips}<label class="toggle"><input type="checkbox" id="hide-done" checked> скрыть готовые</label></div>
<ul class="tasks" id="tasks">{''.join(task_item(t, by_slug) for t in tasks)}</ul>""")

    # ---------------------------------------------------------------- запуски
    run_rows = "".join(
        f'<tr><td>{fmt_ts(r.ts)}</td><td>{e(next((a["name"] for a in agents if a.get("id") == r.agent), r.agent))}</td>'
        f'<td>{badge(r.status)}</td><td>{e(r.summary)}</td>'
        f'<td>{" ".join(digest_link(by_slug[s]) for s in r.digests if s in by_slug)}</td></tr>' for r in runs)
    note = ("" if (digest_dir / "runs.jsonl").exists() else
            '<p class="muted">Журнала runs.jsonl пока нет, поэтому запуски восстановлены по времени сохранения дайджестов.</p>')
    write("runs.html", "Запуски", f"""<h1>Запуски агентов</h1>{note}
<table class="list"><thead><tr><th>Когда</th><th>Агент</th><th>Статус</th><th>Что сделано</th><th>Результат</th></tr></thead>
<tbody>{run_rows}</tbody></table>""")

    # ---------------------------------------------------------------- запросы
    by_section: dict[str, list[sources.Query]] = {}
    for q in queries:
        by_section.setdefault(q.section, []).append(q)
    order = list(sources.load_sections(digest_dir)) + ["Не в дайджесте"]
    blocks = []
    for s in sorted(by_section, key=lambda s: order.index(s) if s in order else len(order)):
        items = "".join(
            f'<details class="query"><summary><code>{e(q.name)}</code> <span class="muted">{e(q.database)}</span>'
            f'<br><span class="desc">{e(q.description)}</span></summary><pre>{e(q.sql)}</pre></details>'
            for q in by_section[s])
        blocks.append(f"<section><h2>{e(s)}</h2>{items}</section>")
    write("queries.html", "Запросы", f"""<h1>Разделы и запросы дайджеста</h1>
<p class="muted">{len(queries)} SQL-запросов в Metabase. Раздел берётся из SECTIONS в digest.py.</p>{''.join(blocks)}""")

    # ---------------------------------------------------------------- обзор
    latest = digests[0] if digests else None
    last_run = runs[0] if runs else None
    open_tasks = [t for t in tasks if t.status != "done"]
    latest_tasks = [t for t in tasks if latest and t.source == latest.slug]
    active = sum(1 for a in agents if a.get("status") == "active")
    stats = f"""<div class="stats">
<div><b>{active} из {len(agents)}</b><span>агентов работают</span></div>
<div><b>{len(digests)}</b><span>дайджестов в архиве</span></div>
<div><b>{fmt_ts(last_run.ts) if last_run else "—"}</b><span>последний запуск</span></div>
<div><b>{len(open_tasks)}</b><span>открытых задач</span></div></div>"""
    latest_html = (f'<h2>Последний дайджест</h2><p>{digest_link(latest)} <span class="muted">· {fmt_ts(latest.saved_at)}</span></p>'
                   f'<article class="tg-message tg preview">{latest.body}</article>') if latest else ""
    todo_html = (f'<h2>Решить сегодня</h2><ul class="tasks">{"".join(task_item(t, by_slug) for t in latest_tasks)}</ul>'
                 if latest_tasks else "")
    write("index.html", "Обзор", f"""<h1>Обзор</h1>{stats}
<div class="cols"><div>{todo_html}<h2>Агенты</h2><div class="grid one">{agents_html}</div></div>
<div>{latest_html}</div></div>""")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--digest-dir", type=Path, default=Path("/mnt/project-files/ecom-digest"))
    ap.add_argument("--config-dir", type=Path, default=HERE.parent / "config.example")
    ap.add_argument("--out", type=Path, default=Path("dist"))
    args = ap.parse_args()
    build(args.digest_dir, args.config_dir, args.out)
    print(f"Готово: {args.out.resolve()}")


if __name__ == "__main__":
    main()
