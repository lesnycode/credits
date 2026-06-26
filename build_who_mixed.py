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


def render_hub(tracks: list[dict]) -> str:
    by_artist: dict[str, list[dict]] = {}
    for tr in tracks:
        by_artist.setdefault(tr["artist"], []).append(tr)
    sections = []
    for artist in sorted(by_artist, key=str.lower):
        items = sorted(by_artist[artist], key=lambda x: x["title"].lower())
        lis = "".join(
            f'<li><a href="/track/{esc(tr["slug"])}/">'
            f'{esc(tr["title"])}</a></li>'
            for tr in items
        )
        sections.append(f"<h2>{esc(artist)}</h2><ul>{lis}</ul>")

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Кто свел — все треки Podlesny Twins</title>
<meta name="description" content="Полный список треков, которые свели и смастерили Podlesny Twins. Ответы на запросы «кто свел» по каждому треку.">
<link rel="canonical" href="{SITE}/track/">
<link rel="icon" type="image/png" href="{SITE}/favicon.png">
<style>
@import url('https://fonts.googleapis.com/css2?family=Work+Sans:wght@400;600;700&display=swap');
body{{margin:0;background:#1a1a19;color:#fff;font-family:'Work Sans',-apple-system,sans-serif}}
.wrap{{max-width:900px;margin:0 auto;padding:40px 20px 80px}}
a{{color:#cf2c04;text-decoration:none}}
a:hover{{text-decoration:underline}}
.nav{{display:flex;justify-content:space-between;margin-bottom:28px;font-size:14px;font-weight:600}}
h1{{font-size:34px;margin:0 0 10px}}
.sub{{color:#9a9292;margin:0 0 32px;line-height:1.5}}
h2{{color:#cf2c04;font-size:15px;margin:28px 0 10px;text-transform:uppercase;letter-spacing:.4px}}
ul{{margin:0;padding:0;list-style:none;display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:6px 20px}}
li{{font-size:14px;line-height:1.4}}
</style>
</head>
<body>
<div class="wrap">
  <div class="nav">
    <a href="{SITE}/">← Портфолио</a>
    <a href="https://podlesnytwins.com">Курс →</a>
  </div>
  <h1>Кто свел — все треки</h1>
  <p class="sub">{len(tracks)} треков в портфолио Podlesny Twins. Павел и Антон Подлесные — сведение и мастеринг.</p>
  {''.join(sections)}
</div>
</body>
</html>
"""


def patch_index(doc: str, tracks: list[dict]) -> str:
    doc = re.sub(
        r'<div class="tile-wrap">(<button class="tile"[^>]*>.*?</button>)'
        r'<a class="tseo" href="/track/[^"]+/">кто свел\?</a></div>',
        r"\1",
        doc,
        flags=re.S,
    )
    id_to_slug = {tr["id"]: tr["slug"] for tr in tracks}
    css = """
.pf .tile-wrap{position:relative;display:block}
.pf .tseo{position:absolute;top:8px;left:8px;z-index:5;font-size:9px;font-weight:700;letter-spacing:.03em;text-transform:uppercase;color:#fff;background:rgba(0,0,0,.58);padding:3px 7px;border-radius:20px;text-decoration:none;opacity:0;transition:.2s}
.pf .tile-wrap:hover .tseo,.pf .tile-wrap:focus-within .tseo{opacity:1}
.pf .seo-foot{text-align:center;margin-top:28px;font-size:14px;font-weight:600}
.pf .seo-foot a{color:#cfc9c9}
.pf .seo-foot a:hover{color:#fff}
"""
    if ".pf .tile-wrap" not in doc:
        doc = doc.replace("</style>", css + "</style>", 1)

    if 'href="/track/"' not in doc:
        doc = doc.replace(
            '<a class="pflink" href="https://podlesnytwins.com">',
            '<a class="pflink" href="/track/">Кто свел</a>\n'
            '    <a class="pflink" href="https://podlesnytwins.com">',
            1,
        )

    if 'class="seo-foot"' not in doc:
        doc = doc.replace(
            '<p class="iadisc">',
            '<p class="seo-foot"><a href="/track/">Кто свел эти треки? Полный список →</a></p>\n'
            '    <p class="iadisc">',
            1,
        )

    def wrap_tile(match: re.Match[str]) -> str:
        block = match.group(0)
        if "openAlbum" in block:
            return block
        tid_m = re.search(r'data-id="([A-Za-z0-9]{22})"', block)
        if not tid_m:
            return block
        slug = id_to_slug.get(tid_m.group(1))
        if not slug:
            return block
        return (
            f'<div class="tile-wrap">{block}'
            f'<a class="tseo" href="/track/{slug}/">кто свел?</a></div>'
        )

    return re.sub(
        r'<button class="tile"[^>]*>.*?</button>',
        wrap_tile,
        doc,
        flags=re.S,
    )


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
        "  <url>",
        f"    <loc>{SITE}/track/</loc>",
        f"    <lastmod>{TODAY}</lastmod>",
        "    <changefreq>weekly</changefreq>",
        "    <priority>0.9</priority>",
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

    hub_file = TRACK_DIR / "index.html"
    if hub_file.exists():
        hub_file.unlink()

    for tr in tracks:
        out = TRACK_DIR / tr["slug"]
        out.mkdir(parents=True, exist_ok=True)
        (out / "index.html").write_text(render_page(tr), encoding="utf-8")

    hub_file.write_text(render_hub(tracks), encoding="utf-8")
    INDEX.write_text(patch_index(doc, tracks), encoding="utf-8")

    write_sitemap(tracks)
    print(f"Сгенерировано страниц: {len(tracks)}")
    print(f"Индекс: {SITE}/track/")
    print(f"Пример: {SITE}/track/{tracks[0]['slug']}/")
    print(f"Sitemap обновлён: {len(tracks) + 2} URL")
    print("index.html — добавлены ссылки на треки")


if __name__ == "__main__":
    main()