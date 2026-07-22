#!/usr/bin/env python3
"""Generate the «кто свёл» reference: per-track SEO pages + grouped hub.

Each track carries a credited role from roles.json (mix / mm / master):
detail pages and schema state only what we actually did. The hub groups by
primary (first-credited) artist with a canonical name, so an artist never
appears as two sections (e.g. «Дима Билан» / «Dima Bilan»).
"""

import hashlib
import html
import json
import re
from collections import OrderedDict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INDEX = ROOT / "index.html"
TRACK_DIR = ROOT / "track"
ROLES_FILE = ROOT / "roles.json"
FEATS_FILE = ROOT / "feats.json"
NOTES_FILE = ROOT / "notes.json"
# persistent SEO ledger: last-known slug per track id, retired-slug redirects,
# and honest per-slug lastmod. Keeps URLs alive + sitemap dates truthful across
# full rebuilds. Committed to git so state survives between machines.
SEO_STATE_FILE = ROOT / "seo_state.json"
SITE = "https://credits.podlesnytwins.com"


def abs_img(u):
    """Site-relative cover paths -> absolute URLs for og:image / JSON-LD."""
    return f"{SITE}{u}" if u.startswith("/") else u
TODAY = date.today().isoformat()

# /faq/ is a hand-written page, not generated from track data. Bump this when the
# FAQ text itself changes — a rebuild must not fake freshness for untouched copy.
FAQ_LASTMOD = "2026-07-22"

# canonical display name for spelling variants of the same artist
CANON = {"Dima Bilan": "Дима Билан"}
# «иностранный агент» artists — need * marker + footnote
IA = {"morgenshtern"}

GA_TAG = (
    '<!-- Google tag (gtag.js) -->\n'
    '<script async src="https://www.googletagmanager.com/gtag/js?id=G-JWPH35TTVX"></script>\n'
    '<script>\n'
    '  window.dataLayer = window.dataLayer || [];\n'
    '  function gtag(){dataLayer.push(arguments);}\n'
    "  gtag('js', new Date());\n"
    "  gtag('config', 'G-JWPH35TTVX');\n"
    '</script>'
)

ROLE_WORD = {"mm": "Сведение и мастеринг", "mix": "Сведение", "master": "Мастеринг"}
ROLE_VERB = {"mm": "Кто свёл", "mix": "Кто свёл", "master": "Кто мастерил"}

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


def canon(name: str) -> str:
    """Canonical display name for a single artist token."""
    n = name.replace("*", "").strip()
    return CANON.get(n, n)


def is_ia(name: str) -> bool:
    return name.replace("*", "").strip().lower() in IA


def primary_of(artist: str) -> str:
    return canon(artist.split(", ")[0])


def others_of(artist: str) -> list[str]:
    return [canon(x) for x in artist.split(", ")[1:]]


def feat_of(tr: dict) -> list[str]:
    """Per-track featured artists. Album tracks: explicit `feat` field
    (string or list). Singles: fall back to non-primary artists in `artist`."""
    f = tr.get("feat")
    if f:
        names = [f] if isinstance(f, str) else list(f)
        return [canon(x) for x in names if x]
    return [] if tr.get("album") else others_of(tr["artist"])


def load_roles() -> dict:
    if ROLES_FILE.is_file():
        return json.loads(ROLES_FILE.read_text(encoding="utf-8"))
    return {}


def load_notes() -> dict:
    """Per-track story blocks (slug -> list of paragraphs), shown under lead."""
    if NOTES_FILE.is_file():
        return json.loads(NOTES_FILE.read_text(encoding="utf-8"))
    return {}


# track-story blocks keyed by slug; populated in main()
NOTES: dict = {}


def load_feats() -> dict:
    """Map track id -> featured artist(s) from feats.json. Value is a
    string ("SALUKI") or list (["SALUKI", "OG Buda"]); empty = no feat."""
    if not FEATS_FILE.is_file():
        return {}
    data = json.loads(FEATS_FILE.read_text(encoding="utf-8"))
    return {row["id"]: row["feat"] for row in data if row.get("feat")}


def extract_tracks(doc: str, roles: dict) -> list[dict]:
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
            "id": tid, "img": img, "artist": artist,
            "title": html.unescape(title), "year": html.unescape(year),
            "album": "", "role": roles.get(tid, "mix"),
        })

    feats = load_feats()
    albums = json.loads(re.search(r"var ALBUMS=(\[.*?\]);", doc, re.S).group(1))
    for album in albums:
        for tr in album["tracks"]:
            tid = tr["id"]
            if tid in seen:
                continue
            seen.add(tid)
            tracks.append({
                "id": tid, "img": album["cover"], "artist": album["artist"],
                "title": tr["title"], "year": tr.get("year", ""),
                "album": album["name"], "role": roles.get(tid, "mix"),
                "feat": feats.get(tid, tr.get("feat", "")),
            })

    return tracks


def assign_slugs(tracks: list[dict]) -> None:
    used: dict[str, int] = {}
    for tr in tracks:
        base = slugify(tr["artist"], tr["title"])
        n = used.get(base, 0)
        used[base] = n + 1
        tr["slug"] = base if n == 0 else f"{base}-{n + 1}"


# ── track detail page ────────────────────────────────────────────────

def render_page(tr: dict) -> str:
    url = f"{SITE}/track/{tr['slug']}/"
    role = tr["role"]
    role_word = ROLE_WORD.get(role, "Сведение")
    verb = ROLE_VERB.get(role, "Кто свёл")
    has_year = bool(tr.get("year")) and tr["year"] != "альбом"
    year_bit = f" ({tr['year']})" if has_year else ""

    q = f"{verb} «{tr['title']}»?"
    title = f"{verb} «{tr['title']}» — {tr['artist']} | Podlesny Twins"
    desc = (
        f"«{tr['title']}» ({tr['artist']}) — {role_word.lower()}: "
        f"Podlesny Twins, Павел и Антон Подлесные."
    )

    album_html = f' Из альбома «{esc(tr["album"])}».' if tr.get("album") else ""
    album_plain = f" Из альбома «{tr['album']}»." if tr.get("album") else ""
    lead = (
        f"«{esc(tr['title'])}»{year_bit} — {esc(tr['artist'])}. "
        f"{role_word}: <strong>Podlesny Twins</strong> "
        f"(Павел и Антон Подлесные).{album_html}"
    )
    answer_plain = (
        f"«{tr['title']}»{year_bit} — {tr['artist']}. {role_word}: "
        f"Podlesny Twins (Павел и Антон Подлесные).{album_plain}"
    )

    schema = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "MusicRecording",
                "name": tr["title"],
                "url": url,
                "image": abs_img(tr["img"]),
                "byArtist": {"@type": "MusicGroup", "name": tr["artist"]},
                **({"inAlbum": {"@type": "MusicAlbum", "name": tr["album"]}}
                   if tr.get("album") else {}),
                "contributor": {
                    "@type": "Organization",
                    "name": "Podlesny Twins",
                    "url": f"{SITE}/",
                },
            },
            {
                "@type": "FAQPage",
                "mainEntity": [{
                    "@type": "Question", "name": q,
                    "acceptedAnswer": {"@type": "Answer", "text": answer_plain},
                }],
            },
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "Все треки",
                     "item": f"{SITE}/track/"},
                    {"@type": "ListItem", "position": 2, "name": tr["title"],
                     "item": url},
                ],
            },
        ],
    }

    meta_line = f"{role_word} · {esc(tr['artist'])}" + (
        f" · {esc(tr['year'])}" if has_year else ""
    )

    note_html = "".join(
        f'\n  <p class="note">{esc(p)}</p>' for p in NOTES.get(tr["slug"], [])
    )

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{GA_TAG}
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<meta name="robots" content="index, follow">
<link rel="canonical" href="{esc(url)}">
<meta property="og:type" content="music.song">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{esc(url)}">
<meta property="og:image" content="{esc(abs_img(tr['img']))}">
<meta property="og:locale" content="ru_RU">
<link rel="icon" type="image/png" href="{SITE}/favicon.png">
<script type="application/ld+json">{json.dumps(schema, ensure_ascii=False)}</script>
<style>
@import url('https://fonts.googleapis.com/css2?family=Work+Sans:wght@400;500;600;700&display=swap');
:root{{--bg:#1a1a19;--surface:#222221;--line:#34332f;--ink:#f2efef;--mut:#9a9292;--mut2:#7a7474;--red:#cf2c04}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);font-family:'Work Sans',-apple-system,sans-serif;-webkit-font-smoothing:antialiased;line-height:1.55}}
.wrap{{max-width:680px;margin:0 auto;padding:40px 20px 80px}}
a{{color:inherit;text-decoration:none}}
.nav{{display:flex;justify-content:space-between;align-items:center;margin-bottom:40px}}
.nav a{{color:var(--mut);font-size:13px;font-weight:600;letter-spacing:.04em;text-transform:uppercase;transition:color .15s}}
.nav a:hover{{color:var(--ink)}}
.bc{{font-size:13px;color:var(--mut2);margin-bottom:22px}}
.bc a{{color:var(--mut)}}
.bc a:hover{{color:var(--ink)}}
.entry{{display:flex;gap:18px;align-items:center;margin-bottom:26px}}
.entry img{{width:96px;height:96px;border-radius:10px;object-fit:cover;flex:none}}
.meta{{font-size:13px;color:var(--red);font-weight:600;letter-spacing:.02em;margin-bottom:6px}}
h1{{font-size:clamp(26px,5vw,38px);line-height:1.08;margin:0;font-weight:700;letter-spacing:-.01em;text-wrap:balance}}
.lead{{font-size:16px;color:#cfc9c9;margin:0 0 26px;max-width:62ch}}
.lead strong{{color:var(--ink);font-weight:600}}
.note{{font-size:15px;color:var(--mut);max-width:62ch;margin:0 0 16px;padding-left:14px;border-left:2px solid var(--line)}}
.note:last-of-type{{margin-bottom:26px}}
.embed{{border-radius:12px;overflow:hidden;margin:0 0 28px}}
.back{{font-size:14px;color:var(--mut)}}
.back a{{color:var(--red);font-weight:600}}
.back a:hover{{text-decoration:underline}}
.workinfo{{font-size:13px;color:var(--mut);margin:0 0 16px}}
.workinfo a{{color:var(--red);font-weight:600}}
.workinfo a:hover{{text-decoration:underline}}
.trackfoot{{font-size:12px;color:var(--mut2);margin-top:18px;padding-top:16px;border-top:1px solid var(--line)}}
.trackfoot a{{color:var(--mut);font-weight:600}}
.trackfoot a:hover{{color:var(--ink)}}
</style>
</head>
<body>
<div class="wrap">
  <div class="nav">
    <a href="{SITE}/">Портфолио</a>
    <a href="https://podlesnytwins.com">Курс</a>
  </div>
  <div class="bc"><a href="{SITE}/">Портфолио</a> / <a href="{SITE}/track/">Все треки</a> / {esc(tr['title'])}</div>
  <div class="entry">
    <img src="{esc(tr['img'])}" alt="{esc(tr['artist'] + ' — ' + tr['title'])}">
    <div>
      <div class="meta">{meta_line}</div>
      <h1>«{esc(tr['title'])}»</h1>
    </div>
  </div>
  <p class="lead">{lead}</p>{note_html}
  <div class="embed">
    <iframe src="https://open.spotify.com/embed/track/{esc(tr['id'])}?utm_source=generator" width="100%" height="152" frameborder="0" allow="autoplay; clipboard-write; encrypted-media; fullscreen; picture-in-picture" loading="lazy" title="Слушать «{esc(tr['title'])}»"></iframe>
  </div>
  <p class="workinfo">Условия работы: <a href="{SITE}/faq/#what-to-send">что прислать, чтобы заказать сведение</a> · <a href="{SITE}/faq/#order">цены, сроки и правки</a></p>
  <p class="back"><a href="{SITE}/track/">← Все треки</a></p>
  <p class="trackfoot"><a href="{SITE}/faq/">Вопросы и ответы</a> · <a href="https://t.me/lesnymix" rel="noopener">Канал о звуке</a> · <a href="https://t.me/+VXgXHnAXj9w2ZGYy" rel="noopener">Чат</a></p>
</div>
</body>
</html>
"""


# ── hub (grouped reference, deduped by primary artist) ───────────────

def _artist_sort_key(name: str):
    """Latin A–Z first, then Cyrillic А–Я, then digits/other."""
    cl = (name[:1] or "").lower()
    if "a" <= cl <= "z":
        bucket = 0
    elif "а" <= cl <= "я" or cl == "ё":
        bucket = 1
    else:
        bucket = 2
    return (bucket, name.lower())


def _dq(*parts: str) -> str:
    return esc(" ".join(p for p in parts if p).lower())


def _feat(tr: dict) -> str:
    o = feat_of(tr)
    return f'<span class="feat"> · с {esc(", ".join(o))}</span>' if o else ""


def render_hub(tracks: list[dict]) -> str:
    groups: "OrderedDict[str, dict]" = OrderedDict()
    for tr in tracks:
        key = primary_of(tr["artist"])
        g = groups.setdefault(key, {"albums": OrderedDict(), "singles": [],
                                     "ia": is_ia(tr["artist"].split(", ")[0])})
        if tr.get("album"):
            alb = g["albums"].setdefault(
                tr["album"],
                {"year": tr.get("year", ""), "cover": tr["img"],
                 "tracks": [], "artist": tr["artist"]},
            )
            alb["tracks"].append(tr)
        else:
            g["singles"].append(tr)

    artists = sorted(groups, key=_artist_sort_key)
    any_ia = any(g["ia"] for g in groups.values())

    blocks = []
    prev_letter = ""
    for artist in artists:
        g = groups[artist]
        count = len(g["singles"]) + sum(len(a["tracks"]) for a in g["albums"].values())
        ia_sup = '<sup class="ia">*</sup>' if g["ia"] else ""

        letter = artist[0].upper() if artist else "#"
        if letter != prev_letter:
            prev_letter = letter
            blocks.append(f'<div class="letter">{esc(letter)}</div>')

        rels = []
        for name, alb in g["albums"].items():
            items = "".join(
                f'<li><a href="/track/{esc(t["slug"])}/" '
                f'data-q="{_dq(t["title"], t["artist"], name)}">{esc(t["title"])}{_feat(t)}</a></li>'
                for t in alb["tracks"]
            )
            year = f'<span class="rel-year">{esc(alb["year"])}</span>' if alb["year"] else ""
            rels.append(
                '<div class="rel album">'
                f'<img class="rel-cover" src="{esc(alb["cover"])}" '
                f'alt="{esc(name + " — " + artist)}" loading="lazy" width="56" height="56">'
                '<div class="rel-body">'
                f'<div class="rel-head"><span class="rel-name">«{esc(name)}»</span>{year}'
                f'<span class="rel-kind">альбом</span></div>'
                f'<ol class="trk-list">{items}</ol>'
                "</div></div>"
            )

        if g["singles"]:
            label = '<div class="rel-label">Синглы</div>' if g["albums"] else ""
            rows = "".join(
                f'<a class="sg" href="/track/{esc(t["slug"])}/" '
                f'data-q="{_dq(t["title"], t["artist"])}">'
                f'<img src="{esc(t["img"])}" alt="" loading="lazy" width="40" height="40">'
                f'<span class="sg-name">{esc(t["title"])}{_feat(t)}</span>'
                + (f'<span class="sg-year">{esc(t["year"])}</span>'
                   if t.get("year") and t["year"] != "альбом" else "<span></span>")
                + "</a>"
                for t in sorted(g["singles"], key=lambda x: x["title"].lower())
            )
            rels.append(f'<div class="rel singles">{label}<div class="sg-list">{rows}</div></div>')

        aid = slugify(artist) or "artist"
        blocks.append(
            f'<section class="art-sec" id="{esc(aid)}" data-artist="{esc(artist.lower())}">'
            f'<header class="art-head"><h2>{esc(artist)}{ia_sup}</h2>'
            f'<span class="art-cnt">{count}</span></header>'
            f'{"".join(rels)}</section>'
        )

    seen_l: set[str] = set()
    jump_links = []
    for a in artists:
        L = a[0].upper() if a else "#"
        if L in seen_l:
            continue
        seen_l.add(L)
        jump_links.append(f'<a class="lj" href="#{esc(slugify(a) or "artist")}">{esc(L)}</a>')

    ia_foot = (
        '<p class="ia-foot">* признан(ы) в РФ иностранным агентом.</p>'
        if any_ia else ""
    )
    total = len(tracks)
    catalog = "".join(blocks)

    # ItemList of the whole catalogue — one structured list an answer engine
    # can read as "these are the works", plus breadcrumbs. Reuses the site's
    # existing #podlesnytwins entity id.
    item_ld = {
        "@context": "https://schema.org",
        "@graph": [
            {"@type": "CollectionPage", "@id": f"{SITE}/track/#webpage",
             "url": f"{SITE}/track/",
             "name": "Кто свёл — все треки Podlesny Twins",
             "isPartOf": {"@id": f"{SITE}/#podlesnytwins"}},
            {"@type": "ItemList", "numberOfItems": total, "itemListOrder": "https://schema.org/ItemListUnordered",
             "itemListElement": [
                 {"@type": "ListItem", "position": i,
                  "url": f"{SITE}/track/{t['slug']}/",
                  "name": f"{t['title']} — {t['artist']}"}
                 for i, t in enumerate(tracks, 1)]},
            {"@type": "BreadcrumbList", "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "Портфолио", "item": f"{SITE}/"},
                {"@type": "ListItem", "position": 2, "name": "Все треки", "item": f"{SITE}/track/"}]},
        ],
    }
    item_ld_json = json.dumps(item_ld, ensure_ascii=False)
    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{GA_TAG}
<title>Кто свёл — все треки Podlesny Twins</title>
<meta name="description" content="Справочник работ Podlesny Twins: альбомы и треки, над которыми работали Павел и Антон Подлесные (сведение и мастеринг). {total} треков с поиском по артисту и названию.">
<link rel="canonical" href="{SITE}/track/">
<link rel="icon" type="image/png" href="{SITE}/favicon.png">
<script type="application/ld+json">{item_ld_json}</script>
<style>
@import url('https://fonts.googleapis.com/css2?family=Work+Sans:wght@400;500;600;700&display=swap');
@font-face{{font-family:'SaarSP';src:url('https://static.tildacdn.com/tild6565-6366-4065-b536-663938373766/SaarSPDemo.WOFF') format('woff');font-weight:400;font-display:swap}}
:root{{--bg:#1a1a19;--surface:#222221;--surface2:#2a2a28;--line:#34332f;--line2:#2a2a28;--ink:#f2efef;--mut:#9a9292;--mut2:#7a7474;--red:#cf2c04}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);font-family:'Work Sans',-apple-system,sans-serif;-webkit-font-smoothing:antialiased;line-height:1.5}}
.pf{{max-width:940px;margin:0 auto;padding:48px 20px 96px}}
a{{color:inherit;text-decoration:none}}
.pfnav{{display:flex;justify-content:space-between;align-items:center;padding-bottom:18px;margin-bottom:40px;border-bottom:1px solid var(--line)}}
.pflink{{color:var(--mut);font-weight:600;font-size:13px;letter-spacing:.04em;text-transform:uppercase;transition:color .15s}}
.pflink:hover{{color:var(--ink)}}
h1{{font-family:'SaarSP',Arial,sans-serif;font-weight:400;font-size:clamp(36px,7vw,68px);line-height:.92;margin:0 0 14px;letter-spacing:-.01em}}
.lead{{font-size:16px;color:var(--mut);max-width:58ch;margin:0}}
.toolbar{{display:flex;flex-wrap:wrap;gap:14px;align-items:center;margin:30px 0 6px}}
.search{{flex:1;min-width:220px;background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:13px 16px;color:var(--ink);font:inherit;font-size:15px;outline:none;transition:border-color .15s}}
.search::placeholder{{color:var(--mut2)}}
.search:focus{{border-color:var(--red)}}
.stat{{font-size:13px;color:var(--mut);font-variant-numeric:tabular-nums;white-space:nowrap}}
.jump{{display:flex;flex-wrap:wrap;gap:4px;margin:14px 0 0}}
.lj{{display:inline-flex;align-items:center;justify-content:center;min-width:30px;height:30px;padding:0 8px;border-radius:8px;color:var(--mut);font-size:12px;font-weight:700;transition:.15s}}
.lj:hover{{color:var(--ink);background:var(--surface)}}
.catalog{{margin-top:30px}}
.letter{{font-family:'SaarSP',Arial,sans-serif;font-size:22px;color:var(--red);margin:40px 0 6px;padding-bottom:8px;border-bottom:1px solid var(--line)}}
.letter:first-child{{margin-top:0}}
.art-sec{{padding:20px 0;border-top:1px solid var(--line2)}}
.art-sec:first-of-type,.letter + .art-sec{{border-top:0}}
.art-head{{display:flex;align-items:baseline;gap:10px;margin-bottom:12px}}
.art-head h2{{margin:0;font-size:19px;font-weight:700;letter-spacing:-.01em}}
.art-head sup{{font-size:11px;color:var(--mut2)}}
.art-cnt{{font-size:12px;color:var(--mut2);font-variant-numeric:tabular-nums}}
.rel{{padding:8px 0}}
.rel.album{{display:flex;gap:14px}}
.rel-cover{{width:56px;height:56px;border-radius:8px;object-fit:cover;flex:none}}
.rel-body{{flex:1;min-width:0}}
.rel-head{{display:flex;align-items:baseline;gap:10px;margin-bottom:8px;flex-wrap:wrap}}
.rel-name{{font-size:15px;font-weight:600}}
.rel-year{{font-size:12px;color:var(--mut);font-variant-numeric:tabular-nums}}
.rel-kind{{font-size:11px;color:var(--mut2);letter-spacing:.06em;text-transform:uppercase}}
.rel-label{{font-size:13px;color:var(--mut);margin-bottom:4px}}
.feat{{color:var(--mut2);font-weight:400}}
.trk-list{{list-style:none;margin:0;padding:0;counter-reset:t;column-width:230px;column-gap:30px}}
.trk-list li{{counter-increment:t;break-inside:avoid}}
.trk-list a{{display:flex;gap:10px;padding:4px 0;font-size:14px;color:#d8d2d2;transition:color .12s}}
.trk-list a::before{{content:counter(t);color:var(--mut2);font-size:12px;font-variant-numeric:tabular-nums;min-width:1.7em;text-align:right;flex:none}}
.trk-list a:hover{{color:var(--red)}}
.sg-list{{display:flex;flex-direction:column}}
.sg{{display:grid;grid-template-columns:40px 1fr auto;align-items:center;gap:12px;padding:7px 0;border-top:1px solid var(--line2)}}
.sg:first-child{{border-top:0}}
.sg img{{width:40px;height:40px;border-radius:6px;object-fit:cover;display:block}}
.sg-name{{font-size:14px;font-weight:500;min-width:0;transition:color .12s}}
.sg-year{{font-size:12px;color:var(--mut);font-variant-numeric:tabular-nums}}
.sg:hover .sg-name{{color:var(--red)}}
.ia-foot{{margin-top:40px;font-size:12px;color:var(--mut2)}}
.hublead{{font-size:14px;color:var(--mut);max-width:58ch;margin:10px 0 0}}
.hublead a{{color:var(--red);font-weight:600}}
.hubfoot{{margin-top:40px;padding-top:18px;border-top:1px solid var(--line);font-size:13px;color:var(--mut2)}}
.hubfoot a{{color:var(--mut);font-weight:600}}
.hubfoot a:hover{{color:var(--ink)}}
.hide{{display:none!important}}
.empty{{display:none;text-align:center;padding:56px 20px;color:var(--mut);font-size:15px}}
.empty.on{{display:block}}
@media (max-width:560px){{
.pf{{padding:32px 14px 64px}}
.rel.album{{gap:11px}}
.rel-cover{{width:48px;height:48px}}
.trk-list{{column-width:auto}}
}}
@media (prefers-reduced-motion:reduce){{*{{transition:none!important}}}}
</style>
</head>
<body>
<div class="pf">
  <div class="pfnav">
    <a class="pflink" href="{SITE}/">← Портфолио</a>
    <a class="pflink" href="https://podlesnytwins.com">Курс →</a>
  </div>
  <h1>Кто свёл</h1>
  <p class="lead">Альбомы и треки из нашего портфолио — сведение и мастеринг. Ищите по артисту, альбому или названию.</p>
  <p class="hublead">Полный каталог работ студии. Условия заказа сведения и мастеринга — в разделе <a href="{SITE}/faq/">вопросов и ответов</a>.</p>
  <div class="toolbar">
    <input class="search" id="q" type="search" placeholder="Артист, альбом или трек…" autocomplete="off">
    <span class="stat">{total} треков · {len(artists)} артистов</span>
  </div>
  <nav class="jump" aria-label="По алфавиту">{"".join(jump_links)}</nav>
  <div class="catalog" id="catalog">{catalog}</div>
  <p class="empty" id="empty">Ничего не нашлось</p>
  {ia_foot}
  <p class="hubfoot"><a href="{SITE}/faq/">Вопросы и ответы</a> · <a href="https://t.me/lesnymix" rel="noopener">Канал о звуке</a> · <a href="https://t.me/+VXgXHnAXj9w2ZGYy" rel="noopener">Чат</a></p>
</div>
<script>
(function(){{
  var q=document.getElementById('q'),cat=document.getElementById('catalog'),em=document.getElementById('empty');
  function norm(s){{return (s||'').toLowerCase().replace(/ё/g,'е');}}
  function run(){{
    var v=norm(q.value.trim()),any=false;
    cat.querySelectorAll('.art-sec').forEach(function(sec){{
      var aMatch=norm(sec.getAttribute('data-artist')).indexOf(v)>=0,secShow=false;
      sec.querySelectorAll('.rel').forEach(function(rel){{
        var relShow=false;
        rel.querySelectorAll('[data-q]').forEach(function(it){{
          var ok=!v||aMatch||norm(it.getAttribute('data-q')).indexOf(v)>=0;
          it.classList.toggle('hide',!ok); if(ok) relShow=true;
        }});
        rel.classList.toggle('hide',!relShow);
        if(relShow) secShow=true;
      }});
      sec.classList.toggle('hide',!secShow);
      if(secShow) any=true;
    }});
    cat.querySelectorAll('.letter').forEach(function(l){{
      var n=l.nextElementSibling,show=false;
      while(n&&!n.classList.contains('letter')){{
        if(n.classList.contains('art-sec')&&!n.classList.contains('hide')){{show=true;break;}}
        n=n.nextElementSibling;
      }}
      l.classList.toggle('hide',!show);
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

    # The home-page footer links out to the catalogue, the FAQ, and the
    # studio's Telegram channel + chat. Replace the whole <p class="seo-foot">
    # in place (idempotent) so re-runs update it instead of duplicating.
    foot = ('<p class="seo-foot"><a href="/track/">Полный список треков</a>'
            ' · <a href="/faq/">Вопросы и ответы</a>'
            ' · <a href="https://t.me/lesnymix" rel="noopener">Канал о звуке</a>'
            ' · <a href="https://t.me/+VXgXHnAXj9w2ZGYy" rel="noopener">Чат</a></p>')
    if 'class="seo-foot"' in doc:
        doc = re.sub(r'<p class="seo-foot">.*?</p>', foot, doc, count=1, flags=re.S)
    else:
        doc = doc.replace('<p class="iadisc">', foot + "\n    " + '<p class="iadisc">', 1)
    return doc


# ── SEO ledger: stable URLs + honest lastmod across full rebuilds ────

def content_hash(tr: dict) -> str:
    """Fingerprint the meaningful, user-visible content of a track page.

    Ignores template/CSS churn on purpose — only real content changes
    (title/artist/year/role/feat/album/cover/notes) bump the fingerprint,
    so a cosmetic template edit doesn't reset every page's <lastmod>.
    """
    payload = json.dumps(
        {
            "artist": tr.get("artist", ""), "title": tr.get("title", ""),
            "year": tr.get("year", ""), "role": tr.get("role", ""),
            "feat": tr.get("feat", ""), "album": tr.get("album", ""),
            "img": tr.get("img", ""), "notes": NOTES.get(tr.get("slug", ""), []),
        },
        ensure_ascii=False, sort_keys=True,
    )
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def render_redirect(target_slug: str) -> str:
    """A retired slug's page: canonical + instant redirect to the live URL.

    Google treats a same-host meta-refresh(0)+canonical as a 301, so link
    equity from an old URL flows to the renamed track instead of 404-ing.
    """
    url = f"{SITE}/track/{target_slug}/"
    return (
        '<!DOCTYPE html>\n<html lang="ru">\n<head>\n<meta charset="utf-8">\n'
        f'<title>Переехало → {esc(target_slug)}</title>\n'
        f'<link rel="canonical" href="{esc(url)}">\n'
        f'<meta http-equiv="refresh" content="0; url={esc(url)}">\n'
        f'<script>location.replace({json.dumps(url)});</script>\n'
        f'</head>\n<body>\n<p>Страница переехала: <a href="{esc(url)}">{esc(url)}</a></p>\n'
        '</body>\n</html>\n'
    )


def sync_seo_state(tracks: list[dict]) -> tuple[dict, dict]:
    """Reconcile the persistent SEO ledger against the current track set.

    Returns (lastmod_by_slug, redirects). A renamed track (same data-id,
    new slug) retires its old slug into `redirects`; a removed track is
    left to 404. Chains collapse to the final live slug; redirects whose
    key is now a live slug or whose target is gone are dropped.
    """
    try:
        state = json.loads(SEO_STATE_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        state = {}
    prev_ids = state.get("ids", {})
    prev_dates = state.get("dates", {})
    redirects = dict(state.get("redirects", {}))

    live_slugs = {tr["slug"] for tr in tracks}
    cur_ids = {tr["id"]: tr["slug"] for tr in tracks}

    # retire slugs of tracks that changed slug but still exist
    for tid, old_slug in prev_ids.items():
        new_slug = cur_ids.get(tid)
        if new_slug and new_slug != old_slug:
            redirects[old_slug] = new_slug

    # collapse chains a→b→c into a→c
    def resolve(slug: str, _seen: set) -> str:
        while slug in redirects and slug not in _seen:
            _seen.add(slug)
            slug = redirects[slug]
        return slug

    redirects = {old: resolve(dst, {old}) for old, dst in redirects.items()}
    # drop redirects that collide with a live page or point nowhere live
    redirects = {
        old: dst for old, dst in redirects.items()
        if old not in live_slugs and dst in live_slugs
    }

    # honest lastmod: keep stored date unless content fingerprint changed
    dates: dict[str, str] = {}
    new_dates: dict[str, dict] = {}
    for tr in tracks:
        slug, h = tr["slug"], content_hash(tr)
        prev = prev_dates.get(slug)
        lastmod = prev["lastmod"] if prev and prev.get("hash") == h else TODAY
        dates[slug] = lastmod
        new_dates[slug] = {"hash": h, "lastmod": lastmod}

    SEO_STATE_FILE.write_text(
        json.dumps(
            {"ids": cur_ids, "redirects": redirects, "dates": new_dates},
            ensure_ascii=False, indent=1, sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )
    return dates, redirects


def write_sitemap(tracks: list[dict], dates: dict) -> None:
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        "  <url>", f"    <loc>{SITE}/</loc>", f"    <lastmod>{TODAY}</lastmod>",
        "    <changefreq>weekly</changefreq>", "    <priority>1.0</priority>", "  </url>",
        "  <url>", f"    <loc>{SITE}/track/</loc>", f"    <lastmod>{TODAY}</lastmod>",
        "    <changefreq>weekly</changefreq>", "    <priority>0.9</priority>", "  </url>",
        # /faq/ is hand-written (not generated from tracks) — its lastmod must reflect
        # when the FAQ text actually changed, not every rebuild. Bump FAQ_LASTMOD by hand.
        "  <url>", f"    <loc>{SITE}/faq/</loc>", f"    <lastmod>{FAQ_LASTMOD}</lastmod>",
        "    <changefreq>monthly</changefreq>", "    <priority>0.8</priority>", "  </url>",
    ]
    for tr in tracks:
        lines += [
            "  <url>", f"    <loc>{SITE}/track/{tr['slug']}/</loc>",
            f"    <lastmod>{dates.get(tr['slug'], TODAY)}</lastmod>",
            "    <changefreq>monthly</changefreq>",
            "    <priority>0.7</priority>", "  </url>",
        ]
    lines.append("</urlset>")
    (ROOT / "sitemap.xml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    global NOTES
    roles = load_roles()
    NOTES = load_notes()
    doc = INDEX.read_text(encoding="utf-8")
    tracks = extract_tracks(doc, roles)
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

    live_slugs = {tr["slug"] for tr in tracks}
    for tr in tracks:
        out = TRACK_DIR / tr["slug"]
        out.mkdir(parents=True, exist_ok=True)
        (out / "index.html").write_text(render_page(tr), encoding="utf-8")

    # reconcile SEO ledger, then re-emit redirect stubs for retired slugs
    # (the track/ wipe above deletes them each build, so rebuild from state)
    dates, redirects = sync_seo_state(tracks)
    for old_slug, new_slug in redirects.items():
        if old_slug in live_slugs:
            continue
        out = TRACK_DIR / old_slug
        out.mkdir(parents=True, exist_ok=True)
        (out / "index.html").write_text(render_redirect(new_slug), encoding="utf-8")

    hub_file.write_text(render_hub(tracks), encoding="utf-8")
    INDEX.write_text(patch_index_footer(doc), encoding="utf-8")

    write_sitemap(tracks, dates)
    from collections import Counter
    print(f"Сгенерировано страниц: {len(tracks)}  роли: {dict(Counter(t['role'] for t in tracks))}")
    print(f"Артистов в хабе: {len(set(primary_of(t['artist']) for t in tracks))}")
    if redirects:
        print(f"Редиректы (retired slugs): {len(redirects)}")


if __name__ == "__main__":
    main()
