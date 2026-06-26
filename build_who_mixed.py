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

    artists = sorted(by_artist, key=str.lower)
    blocks = []
    prev_letter = ""
    for artist in artists:
        items = sorted(by_artist[artist], key=lambda x: x["title"].lower())
        letter = (artist[0].upper() if artist else "#")
        letter_band = ""
        if letter != prev_letter:
            prev_letter = letter
            letter_band = f'<div class="letter" data-letter="{esc(letter)}">{esc(letter)}</div>'
        rows = []
        for tr in items:
            yr = tr.get("year", "")
            yr_html = (
                f'<span class="tyr">{esc(yr)}</span>'
                if yr and yr != "альбом"
                else ""
            )
            rows.append(
                f'<a class="trow" href="/track/{esc(tr["slug"])}/" '
                f'data-q="{esc((tr["title"] + " " + artist).lower())}">'
                f'<img src="{esc(tr["img"])}" alt="" loading="lazy" width="44" height="44">'
                f'<span class="tname">{esc(tr["title"])}</span>'
                f'{yr_html}<span class="tgo" aria-hidden="true">→</span></a>'
            )
        rows = "".join(rows)
        aid = slugify(artist) or "artist"
        blocks.append(
            f'{letter_band}<section class="ablock" id="{esc(aid)}" data-artist="{esc(artist.lower())}">'
            f'<header class="ahead"><h2>{esc(artist)}</h2>'
            f'<span class="acnt">{len(items)}</span></header>'
            f'<div class="tlist">{rows}</div></section>'
        )

    seen_l: set[str] = set()
    jump_links = []
    for a in artists:
        L = a[0].upper() if a else "#"
        if L in seen_l:
            continue
        seen_l.add(L)
        jump_links.append(
            f'<a class="lj" href="#{esc(slugify(a) or "artist")}">{esc(L)}</a>'
        )

    catalog = "".join(blocks)
    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Кто свел — все треки Podlesny Twins</title>
<meta name="description" content="Полный список треков, которые свели и смастерили Podlesny Twins — сведение и мастеринг.">
<link rel="canonical" href="{SITE}/track/">
<link rel="icon" type="image/png" href="{SITE}/favicon.png">
<style>
@import url('https://fonts.googleapis.com/css2?family=Work+Sans:wght@400;500;600;700;800&display=swap');
@font-face{{font-family:'SaarSP';src:url('https://static.tildacdn.com/tild6565-6366-4065-b536-663938373766/SaarSPDemo.WOFF') format('woff');font-weight:400;font-display:swap}}
*{{box-sizing:border-box}}
body{{margin:0;background:#1a1a19;color:#fff;font-family:'Work Sans',-apple-system,sans-serif;-webkit-font-smoothing:antialiased}}
.pf{{max-width:1180px;margin:0 auto;padding:48px 20px 80px}}
a{{color:inherit;text-decoration:none}}
.pfnav{{display:flex;justify-content:space-between;align-items:center;padding-bottom:18px;margin-bottom:32px;border-bottom:1px solid rgba(255,255,255,.09)}}
.pflink{{color:#cfc9c9;font-weight:600;font-size:14px;transition:.15s}}
.pflink:hover{{color:#fff}}
h1{{font-family:'SaarSP',Arial,sans-serif;font-size:clamp(32px,5vw,52px);font-weight:400;line-height:.95;margin:0 0 12px}}
.lead{{font-size:15px;color:#9a9292;margin:0 0 24px;line-height:1.5}}
.toolbar{{display:flex;flex-wrap:wrap;gap:12px;align-items:center;margin-bottom:28px}}
.search{{flex:1;min-width:200px;background:#262625;border:1px solid #34332f;border-radius:40px;padding:12px 18px;color:#fff;font:inherit;font-size:15px;outline:none}}
.search::placeholder{{color:#7a7474}}
.search:focus{{border-color:#cf2c04}}
.stat{{font-size:13px;font-weight:700;color:#cf2c04;letter-spacing:.04em;text-transform:uppercase;white-space:nowrap}}
.jump{{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:24px}}
.lj{{display:inline-flex;align-items:center;justify-content:center;min-width:32px;height:32px;padding:0 8px;border-radius:8px;background:#262625;border:1px solid #34332f;font-size:12px;font-weight:700;color:#b6afaf;transition:.15s}}
.lj:hover{{color:#fff;border-color:#cf2c04}}
.catalog{{display:flex;flex-direction:column;gap:14px}}
.letter{{font-size:11px;font-weight:800;letter-spacing:.12em;color:#cf2c04;text-transform:uppercase;margin:18px 0 4px;padding-left:2px}}
.letter:first-child{{margin-top:0}}
.ablock{{background:#262625;border:1px solid #34332f;border-radius:14px;overflow:hidden}}
.ahead{{display:flex;align-items:baseline;justify-content:space-between;gap:12px;padding:16px 18px 12px;border-bottom:1px solid #34332f}}
.ahead h2{{margin:0;font-size:15px;font-weight:700;color:#cf2c04;letter-spacing:.02em}}
.acnt{{font-size:11px;font-weight:700;color:#9a9292;background:#1f1f1e;padding:4px 9px;border-radius:20px;white-space:nowrap}}
.tlist{{display:flex;flex-direction:column}}
.trow{{display:grid;grid-template-columns:44px 1fr auto 20px;align-items:center;gap:12px;padding:11px 18px;border-top:1px solid #2a2a28;transition:background .12s}}
.trow:first-child{{border-top:0}}
.trow:hover{{background:#2e2e2d}}
.trow img{{width:44px;height:44px;border-radius:6px;object-fit:cover;display:block}}
.tname{{font-size:15px;font-weight:600;line-height:1.25}}
.tyr{{font-size:12px;color:#9a9292;font-weight:500}}
.tgo{{color:#cf2c04;font-size:14px;opacity:0;transform:translateX(-4px);transition:.15s}}
.trow:hover .tgo{{opacity:1;transform:none}}
.ablock.hide,.trow.hide,.letter.hide{{display:none}}
.empty{{display:none;text-align:center;padding:48px 20px;color:#9a9292;font-size:15px}}
.empty.on{{display:block}}
@media (max-width:600px){{
.pf{{padding:30px 14px 60px}}
.trow{{grid-template-columns:40px 1fr auto;padding:10px 14px;gap:10px}}
.trow img{{width:40px;height:40px}}
.tgo{{display:none}}
.jump{{gap:5px}}
.lj{{min-width:28px;height:28px;font-size:11px}}
}}
</style>
</head>
<body>
<div class="pf">
  <div class="pfnav">
    <a class="pflink" href="{SITE}/">← Портфолио</a>
    <a class="pflink" href="https://podlesnytwins.com">Курс →</a>
  </div>
  <h1>Кто свел</h1>
  <p class="lead">Все треки Podlesny Twins — Павел и Антон Подлесные, сведение и мастеринг.</p>
  <div class="toolbar">
    <input class="search" id="q" type="search" placeholder="Найти трек или артиста…" autocomplete="off">
    <span class="stat">{len(tracks)} треков · {len(artists)} артистов</span>
  </div>
  <nav class="jump" aria-label="По алфавиту">{"".join(jump_links)}</nav>
  <div class="catalog" id="catalog">{catalog}</div>
  <p class="empty" id="empty">Ничего не найдено</p>
</div>
<script>
(function(){{
  var q=document.getElementById('q'),cat=document.getElementById('catalog'),em=document.getElementById('empty');
  function norm(s){{return (s||'').toLowerCase().replace(/ё/g,'е');}}
  function run(){{
    var v=norm(q.value.trim()),any=false;
    cat.querySelectorAll('.ablock').forEach(function(b){{
      var show=false;
      b.querySelectorAll('.trow').forEach(function(r){{
        var ok=!v||norm(r.getAttribute('data-q')).indexOf(v)>=0||norm(b.getAttribute('data-artist')).indexOf(v)>=0;
        r.classList.toggle('hide',!ok); if(ok) show=true;
      }});
      b.classList.toggle('hide',!show);
      cat.querySelectorAll('.letter').forEach(function(l){{
        var n=l.nextElementSibling;
        if(n&&n.classList.contains('ablock')&&!n.classList.contains('hide')) l.classList.remove('hide');
        else if(n&&n.classList.contains('ablock')) l.classList.add('hide');
      }});
      if(show) any=true;
    }});
    cat.querySelectorAll('.letter').forEach(function(l){{
      var n=l.nextElementSibling;
      l.classList.toggle('hide',!n||!n.classList.contains('ablock')||n.classList.contains('hide'));
    }});
    em.classList.toggle('on',!any);
  }}
  q.addEventListener('input',run);
}})();
</script>
</body>
</html>
"""


def patch_index_footer(doc: str) -> str:
    css = """
.pf .seo-foot{margin:22px auto 0;font-size:12px;line-height:1.5}
.pf .seo-foot a{color:#918b8b;font-weight:600}
.pf .seo-foot a:hover{color:#cfc9c9}
"""
    if ".pf .seo-foot" not in doc:
        doc = doc.replace("</style>", css + "</style>", 1)

    foot = '<p class="seo-foot"><a href="/track/">Полный список треков</a></p>'
    if foot not in doc:
        doc = doc.replace('<p class="iadisc">', foot + "\n    " + '<p class="iadisc">', 1)
    return doc


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

    hub_file = TRACK_DIR / "index.html"
    if TRACK_DIR.exists():
        if hub_file.is_file():
            hub_file.unlink()
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

    hub_file.write_text(render_hub(tracks), encoding="utf-8")
    INDEX.write_text(patch_index_footer(doc), encoding="utf-8")

    write_sitemap(tracks)
    print(f"Сгенерировано страниц: {len(tracks)}")
    print(f"Индекс: {SITE}/track/")
    print(f"Пример: {SITE}/track/{tracks[0]['slug']}/")
    print(f"Sitemap обновлён: {len(tracks) + 2} URL")


if __name__ == "__main__":
    main()