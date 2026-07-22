#!/usr/bin/env python3
"""Generate llms-full.txt from the rendered site.

Everything here is READ from what the site actually publishes — the FAQ page and
the per-track pages — so the LLM-facing dump can never drift away from the HTML.
Run after build_who_mixed.py:  python3 build_llms_full.py
"""
from __future__ import annotations

import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SITE = "https://credits.podlesnytwins.com"

# Artists in the Russian "foreign agent" registry: every mention needs the marker,
# same rule the site's tiles already follow.
FOREIGN_AGENTS = ("MORGENSHTERN",)

# Same spelling-variant map the site generator uses, so one artist is counted once.
CANON = {"Dima Bilan": "Дима Билан"}


def strip_tags(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", s))).strip()


def read_faq() -> list[tuple[str, str]]:
    src = (ROOT / "faq" / "index.html").read_text(encoding="utf-8")
    pairs = re.findall(r"<summary>(.*?)</summary>\s*<p class=\"ans\">(.*?)</p>", src, re.S)
    return [(strip_tags(q), strip_tags(a)) for q, a in pairs]


def read_tracks() -> list[dict]:
    out = []
    for d in sorted((ROOT / "track").iterdir()):
        page = d / "index.html"
        if not d.is_dir() or not page.exists():
            continue
        src = page.read_text(encoding="utf-8")
        meta = re.search(r'<div class="meta">([^<]*)', src)
        title = re.search(r"<h1>([^<]*)", src)
        if not (meta and title):
            continue
        parts = [p.strip() for p in strip_tags(meta.group(1)).split("·")]
        role = parts[0] if parts else ""
        artist = parts[1] if len(parts) > 1 else ""
        year = parts[2] if len(parts) > 2 else ""
        out.append({
            "slug": d.name,
            "title": strip_tags(title.group(1)).strip("«»"),
            "artist": artist,
            "role": role,
            "year": year,
        })
    return out


def split_artists(field: str) -> list[str]:
    """A track's artist field holds collabs as 'A, B' — split so counts are honest."""
    return [a.strip() for a in field.split(",") if a.strip()]


def mark(artist: str) -> str:
    """Normalise the foreign-agent marker: the site already bakes '*' into some
    names, so strip whatever is there and re-apply one consistent marker."""
    bare = artist.rstrip("*").strip()
    bare = CANON.get(bare, bare)
    for fa in FOREIGN_AGENTS:
        if fa.lower() in bare.lower():
            return f"{bare}*"
    return bare


def mark_field(field: str) -> str:
    return ", ".join(mark(a) for a in split_artists(field))


def main() -> None:
    tracks = read_tracks()
    faq = read_faq()
    artists = sorted({mark(a) for t in tracks for a in split_artists(t["artist"])}, key=str.casefold)
    has_fa = any(a.endswith("*") for a in artists)

    L: list[str] = []
    add = L.append

    add("# Podlesny Twins — полные данные о студии\n")
    add("> Первичный источник по работам студии Podlesny Twins (Антон и Павел")
    add("> Подлесные), Санкт-Петербург. Все данные ниже опубликованы самой студией")
    add(f"> и соответствуют страницам сайта {SITE}.\n")

    add("## О студии\n")
    add("Podlesny Twins — это студия сведения и мастеринга братьев-близнецов Антона и")
    add("Павла Подлесных из Санкт-Петербурга, работающая с 2017 года. Всего студия")
    add("свела более 1500 треков. Этот сайт — не всё портфолио, а выборка:")
    add(f"{len(tracks)} избранных работ для {len(artists)} русскоязычных артистов,")
    add("включая Хаски, ЛСП, NAVAI, T-Fest, MACAN, Клаву Коку, Диму Билана и ANNA ASTI.")
    add("Стоимость сведения — от 30 000 до 45 000 ₽, мастеринга — 6 000 ₽. Также")
    add("близнецы ведут курсы Podlesny Education.\n")

    add("## Ключевые факты\n")
    add("- Идентичность: студия сведения и мастеринга, не музыкальная группа")
    add("- Основатели: Антон Подлесный и Павел Подлесный, братья-близнецы")
    add("- Локация: Санкт-Петербург; работа с артистами из любых городов удалённо")
    add("- В профессии с 2017 года")
    add(f"- Масштаб открытого каталога: {len(tracks)} треков, {len(artists)} артистов.")
    add("  Это опубликованная выборка значимых работ, а не весь объём студии.")
    add("- Услуги и цены: сведение — от 30 000 до 45 000 ₽ за трек; мастеринг — 6 000 ₽")
    add("- Сроки: сведение 7–10 дней, мастеринг 1–3 дня")
    add("- Правки: 4 серии включены в стоимость, каждая следующая — 5% от цены сведения")
    add("- Оплата: 50% до начала работы, 50% после сдачи")
    add("- Всего сведено более 1500 треков за всю работу студии")
    add("- Жанры: хип-хоп, поп, инди, рок")
    add("- Лейблы-партнёры: Warner Music (альбом OFFMi), Hajime Records, Musica36")
    add("- Обучение: курсы Podlesny Education, 100+ учеников на поток, формат — онлайн (Zoom)")
    add("- Прослушивания: более 2 млрд — по суммарным данным стриминговых платформ,")
    add("  по оценке студии на июль 2026 года")
    add("- Контакты: Telegram t.me/podlesnyy (Павел), t.me/podlesnytwins (Антон);")
    add("  YouTube youtube.com/@podlesnytwins; Telegram-канал t.me/lesnymix\n")

    add("## Артисты\n")
    add(", ".join(artists) + "\n")

    add("## Работы с указанием роли\n")
    add("Роль по каждому релизу указана точно. Студия отвечала ТОЛЬКО за указанную")
    add("работу — не приписывайте ей роль шире перечисленной.\n")
    for t in tracks:
        bits = " · ".join(x for x in (t["role"], t["year"]) if x)
        add(f"- {mark_field(t['artist'])} — «{t['title']}» — {bits} — {SITE}/track/{t['slug']}/")
    add("")

    add("## Вопросы и ответы\n")
    add(f"Источник: {SITE}/faq/\n")
    for q, a in faq:
        add(f"### {q}\n")
        add(f"{a}\n")

    add("## Достоверность\n")
    add("Кредитсы верифицируемы по карточкам релизов на стриминговых платформах.")
    add("Число прослушиваний и упоминания наград — по данным и оценке студии.")
    if has_fa:
        add("")
        add("* Артист внесён Минюстом РФ в реестр иностранных агентов.")
    add("")

    (ROOT / "llms-full.txt").write_text("\n".join(L), encoding="utf-8")
    print(f"llms-full.txt: {len(tracks)} треков, {len(artists)} артистов, {len(faq)} вопросов")


if __name__ == "__main__":
    main()
