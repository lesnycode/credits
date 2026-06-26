#!/usr/bin/env python3
"""Generate static «кто свел» SEO pages from index.html track data."""

import html
import json
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INDEX = ROOT / "index.html"
TRACK_DIR = ROOT / "track"
SITE = "https://credits.podlesnytwins.com"
TODAY = date.today().isoformat()

TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def esc(s: str) -> str:
    return html.escape(s, quote=True)


def slugify(*parts: str) -> str:
    raw = "-".join(parts).lower().replace("’", "'")
    out = []
    for ch in raw:
        if ch in TRANSLIT:
            out.append(TRANSLIT[ch])
        elif "a" <= ch <= "z" or "0" <= ch <= "9":
            out.append(ch)
        elif ch in " -_'/;,&.+":
            out.append("-")
    slug = re.sub(r"-+", "-", "".join(out)).strip("-")
    return slug[:80] or "track"


def extract_tracks(doc: str) -> list[dict]:
    tracks: list[dict] = []
    seen: set[str] = set()

    tile_re = re.compile(
        r'<button class="tile(?![^"]*album)[^"]*"[^>]*data-id="([A-Za-z0-9]{22})"[^>]*>'
        r'.*?<img src="([^"]+)"[^>]*>.*?<span class="art">(.*?)</span>'
        r'<span class="trk">(.*?)</span><span class="yr">(.*?)</span>',
        re.S,
    )
    for tid, img, artist, title, year in tile_re.findall(doc):
        artist = html.unescape(re.sub(r"<[^>]+>", "", artist))
        if tid in seen:
            continue
        seen.add(tid)
        tracks.append({
            "id": tid,
            "img": img,
            "artist": html.unescape(artist),
            "title": html.unescape(title),
            "year": html.unescape(year),
        })

    albums = json.loads(re.search(r"var ALBUMS=(\[.*?\]);", doc, re.S).group(1))
    for album in albums:
        for tr in album["tracks"]:
            tid = tr["id"]
            if tid in seen:
                continue
            seen.add(tid)
            tracks.append({
                "id": tid,
                "img": album["cover"],
                "artist": album["artist"],
                "title": tr["title"],
                "year": tr.get("year", ""),
            })

    return tracks


def assign_slugs(tracks: list[dict]) -> None:
    used: dict[str, int] = {}
    for tr in tracks:
        base = slugify(tr["artist"], tr["title"])
        n = used.get(base, 0)
        used[base] = n + 1
        tr["slug"] = base if n == 0 else f"{base}-{n + 1}"


def render_page(tr: dict) -> str:
    url = f"{SITE}/track/{tr['slug']}/"
    q = f"Кто свел «{tr['title']}»?"
    title = f"Кто свел «{tr['title']}» — {tr['artist']} | Podlesny Twins"
    desc = (
        f"Трек «{tr['title']}» ({tr['artist']}) свели и смастерили Podlesny Twins — "
        f"Павел и Антон Подлесные. Студия сведения и мастеринга, 2+ млрд прослушиваний."
    )
    year_bit = f" ({tr['year']})" if tr.get("year") and tr["year"] != "альбом" else ""
    answer = (
        f"Трек «{tr['title']}»{year_bit} артиста {tr['artist']} свели и смастерили "
        f"<strong>Podlesny Twins</strong> — звукорежиссёры Павел и Антон Подлесные. "
        f"Это их официальное портфолио: сведение (mixing) и мастеринг (mastering)."
    )
    schema = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "MusicRecording",
                "name": tr["title"],
                "url": url,
                "image": tr["img"],
                "byArtist": {"@type": "MusicGroup", "name": tr["artist"]},
                "contributor": {
                    "@type": "Organization",
                    "name": "Podlesny Twins",
                    "url": f"{SITE}/",
                },
            },
            {
                "@type": "FAQPage",
                "mainEntity": [{
                    "@type": "Question",
                    "name": q,
                    "acceptedAnswer": {
                        "@type": "Answer",
                        "text": re.sub(r"<[^>]+>", "", answer),
                    },
                }],
            },
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "Портфолио", "item": f"{SITE}/"},
                    {"@type": "ListItem", "position": 2, "name": tr["title"], "item": url},
                ],
            },
        ],
    }

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<meta name="robots" content="index, follow">
<link rel="canonical" href="{esc(url)}">
<meta property="og:type" content="music.song">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{esc(url)}">
<meta property="og:image" content="{esc(tr['img'])}">
<meta property="og:locale" content="ru_RU">
<link rel="icon" type="image/png" href="{SITE}/favicon.png">
<script type="application/ld+json">{json.dumps(schema, ensure_ascii=False)}</script>
<style>
@import url('https://fonts.googleapis.com/css2?family=Work+Sans:wght@400;600;700;800&display=swap');
body{{margin:0;background:#1a1a19;color:#fff;font-family:'Work Sans',-apple-system,sans-serif}}
.wrap{{max-width:760px;margin:0 auto;padding:40px 20px 80px}}
a{{color:#cf2c04;text-decoration:none}}
a:hover{{text-decoration:underline}}
.nav{{display:flex;justify-content:space-between;align-items:center;margin-bottom:36px;font-size:14px;font-weight:600}}
.bc{{font-size:13px;color:#9a9292;margin-bottom:24px}}
.bc a{{color:#9a9292}}
.card{{display:flex;gap:20px;align-items:center;background:#262625;border-radius:14px;padding:20px;margin:24px 0}}
.card img{{width:120px;height:120px;border-radius:10px;object-fit:cover}}
.art{{color:#cf2c04;font-size:13px;font-weight:700;margin-bottom:4px}}
h1{{font-size:clamp(28px,5vw,40px);line-height:1.1;margin:0 0 16px;font-weight:800}}
.lead{{font-size:17px;line-height:1.65;color:#d8d0d0;margin:0 0 20px}}
.lead strong{{color:#fff}}
.embed{{border-radius:12px;overflow:hidden;margin:28px 0}}
.cta{{display:inline-block;background:#cf2c04;color:#fff;font-weight:700;padding:14px 28px;border-radius:40px;margin-top:8px}}
.cta:hover{{background:#e3401a;text-decoration:none}}
.kw{{font-size:13px;color:#918b8b;line-height:1.6;margin-top:32px}}
</style>
</head>
<body>
<div class="wrap">
  <div class="nav">
    <a href="{SITE}/">← Портфолио</a>
    <a href="https://podlesnytwins.com">Курс →</a>
  </div>
  <div class="bc"><a href="{SITE}/">Портфолио</a> / {esc(tr['artist'])} / {esc(tr['title'])}</div>
  <h1>{esc(q)}</h1>
  <div class="card">
    <img src="{esc(tr['img'])}" alt="{esc(tr['artist'] + ' — ' + tr['title'])}">
    <div>
      <div class="art">{esc(tr['artist'])}</div>
      <div style="font-size:22px;font-weight:700">{esc(tr['title'])}</div>
      {f'<div style="font-size:13px;color:#9a9292;margin-top:4px">{esc(tr["year"])}</div>' if tr.get('year') and tr['year'] != 'альбом' else ''}
    </div>
  </div>
  <p class="lead">{answer}</p>
  <div class="embed">
    <iframe src="https://open.spotify.com/embed/track/{esc(tr['id'])}?utm_source=generator" width="100%" height="152" frameborder="0" allow="autoplay; clipboard-write; encrypted-media; fullscreen; picture-in-picture" loading="lazy" title="Слушать {esc(tr['title'])}"></iframe>
  </div>
  <a class="cta" href="{SITE}/">Все работы Podlesny Twins →</a>
  <p class="kw">Запросы: кто свел {esc(tr['title'].lower())}, кто мастерил {esc(tr['title'].lower())}, {esc(tr['artist'])} сведение, Podlesny Twins {esc(tr['title'])}</p>
</div>
</body>
</html>
"""


def write_sitemap(tracks: list[dict]) -> None:
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        "  <url>",
        f"    <loc>{SITE}/</loc>",
        f"    <lastmod>{TODAY}</lastmod>",
        "    <changefreq>weekly</changefreq>",
        "    <priority>1.0</priority>",
        "  </url>",
    ]
    for tr in tracks:
        lines += [
            "  <url>",
            f"    <loc>{SITE}/track/{tr['slug']}/</loc>",
            f"    <lastmod>{TODAY}</lastmod>",
            "    <changefreq>monthly</changefreq>",
            "    <priority>0.7</priority>",
            "  </url>",
        ]
    lines.append("</urlset>")
    (ROOT / "sitemap.xml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    doc = INDEX.read_text(encoding="utf-8")
    tracks = extract_tracks(doc)
    assign_slugs(tracks)

    if TRACK_DIR.exists():
        for old in TRACK_DIR.iterdir():
            if old.is_dir():
                for f in old.iterdir():
                    f.unlink()
                old.rmdir()
    TRACK_DIR.mkdir(exist_ok=True)

    for tr in tracks:
        out = TRACK_DIR / tr["slug"]
        out.mkdir(parents=True, exist_ok=True)
        (out / "index.html").write_text(render_page(tr), encoding="utf-8")

    write_sitemap(tracks)
    print(f"Сгенерировано страниц: {len(tracks)}")
    print(f"Пример: {SITE}/track/{tracks[0]['slug']}/")
    print(f"Sitemap обновлён: {len(tracks) + 1} URL")


if __name__ == "__main__":
    main()