#!/usr/bin/env python3
"""Manage tracks/albums on credits.podlesnytwins.com (~/works-site).

Subcommands (first arg; defaults to `add` if omitted):

  add <link[@GENRE]>...   Add one or more single tracks. Auto-derives artist,
                          title, year, cover from Spotify; auto-picks genre from
                          the artist's existing tiles (or `@GENRE` / --genre).
                          Builds SEO pages + sitemap ONCE after all tiles.

  album <album-link>      Add a whole album: pulls the tracklist from Spotify,
                          appends an object to the JS ALBUMS array + an album
                          tile, writes roles for every track, rebuilds.

  remove <link-or-id>...  Remove single-track tile(s) + roles.json entries, then
                          rebuild (which also prunes orphaned track/ pages).

  build                   Just run build_who_mixed.py (regenerate + prune orphans).

Common flags:
  --genre HIPHOP|POP|INDIE|ROCK   Force bucket. New artist w/o genre -> the tool
                                  prints GENRE_UNKNOWN and writes NOTHING (exit 3).
  --role  mix|mm|master           Default mix. Applies to every track in the call.
  --award GRAM|TOP1               Award filter (data-aw).
  --ia / --no-ia                  Force иностранный агент marker. Default: auto.
  --year / --artist / --title     Override (single-link add only).
  --dry-run                       Resolve + print RESULT lines, write nothing.
  --no-build                      Edit files but skip build_who_mixed.py.
  --repo PATH                     Default ~/works-site.
  --json                          Emit machine-readable RESULT {...} lines.

Per-link genre in a batch: suffix the link with @GENRE, e.g.
  add "https://open.spotify.com/track/ID1@POP" "https://...ID2@HIPHOP"
"""

import argparse
import html
import json
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

GENRES = {"HIPHOP", "POP", "INDIE", "ROCK"}
AWARDS = {"GRAM", "TOP1"}
ROLES = {"mix", "mm", "master"}
IA = {"morgenshtern"}  # keep in sync with build_who_mixed.py IA set
UA = {"User-Agent": "Mozilla/5.0"}


def die(msg, code=1):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def esc(s):
    return html.escape(s, quote=True)


def primary(artist):
    return artist.split(",")[0].strip().lower()


def plt(n):
    n = abs(n) % 100
    d = n % 10
    if 10 < n < 20:
        return "треков"
    if d == 1:
        return "трек"
    if 2 <= d <= 4:
        return "трека"
    return "треков"


def parse_id(raw):
    m = re.search(r"([A-Za-z0-9]{22})", raw)
    if not m:
        die(f"cannot parse Spotify id from {raw!r}")
    return m.group(1)


def _get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20) as r:
        return r.read().decode("utf-8")


def _next_data(page):
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', page, re.S)
    return json.loads(m.group(1)) if m else {}


def _find(o, key, depth=0):
    if depth > 9:
        return None
    if isinstance(o, dict):
        if key in o:
            return o[key]
        for v in o.values():
            r = _find(v, key, depth + 1)
            if r is not None:
                return r
    elif isinstance(o, list):
        for v in o:
            r = _find(v, key, depth + 1)
            if r is not None:
                return r
    return None


def _cover_hash(thumb):
    m = re.search(r"ab67616d[0-9a-f]{8}([0-9a-f]+)", thumb or "")
    return m.group(1) if m else ""


def oembed(kind, sid):
    return json.loads(_get(
        "https://open.spotify.com/oembed?url="
        + urllib.parse.quote(f"https://open.spotify.com/{kind}/{sid}")
    ))


def fetch_track(track_id):
    oe = oembed("track", track_id)
    chash = _cover_hash(oe.get("thumbnail_url"))
    if not chash:
        die("cannot resolve cover hash from oEmbed")
    artist = year = ""
    try:
        page = _get(f"https://open.spotify.com/embed/track/{track_id}")
        am = re.search(r'"artists":(\[.*?\])', page)
        if am:
            artist = ", ".join(a.get("name", "") for a in json.loads(am.group(1)) if a.get("name"))
        ym = re.search(r'"releaseDate":\{"isoString":"(\d{4})', page)
        if ym:
            year = ym.group(1)
    except Exception as e:
        print(f"note: track embed metadata unavailable ({e})", file=sys.stderr)
    return {"title": oe.get("title", ""), "artist": artist, "year": year, "cover_hash": chash}


def fetch_album(album_id):
    oe = oembed("album", album_id)
    chash = _cover_hash(oe.get("thumbnail_url"))
    if not chash:
        die("cannot resolve album cover hash from oEmbed")
    page = _get(f"https://open.spotify.com/embed/album/{album_id}")
    d = _next_data(page)
    tl = _find(d, "trackList") or []
    if not tl:
        die("could not read album tracklist from Spotify embed")
    ym = re.search(r'"releaseDate":\{"isoString":"(\d{4})', page)
    year = ym.group(1) if ym else ""
    ids = [t["uri"].split(":")[-1] for t in tl if t.get("uri")]
    if not year and ids:  # album embed often omits the date; borrow track 1's
        year = fetch_track(ids[0]).get("year", "")
    tracks = [{"id": t["uri"].split(":")[-1], "title": t.get("title", ""), "year": year}
              for t in tl if t.get("uri")]
    # album artist: primary from first track subtitle
    subs = [t.get("subtitle", "") for t in tl if t.get("subtitle")]
    artist = subs[0].split(",")[0].strip() if subs else ""
    return {"name": oe.get("title", ""), "artist": artist, "year": year,
            "cover_hash": chash, "tracks": tracks}


def fetch_playlist(playlist_id):
    """Return {name, tracks:[{id,title,artist}]} from the playlist embed.

    NOTE: the no-auth embed exposes only the first ~50-100 tracks. For a big
    works-playlist keep newest near the top (or use a small staging playlist);
    tracks already on the site are skipped anyway, so only new ones matter.
    """
    d = _next_data(_get(f"https://open.spotify.com/embed/playlist/{playlist_id}"))
    tl = _find(d, "trackList") or []
    if not tl:
        die("could not read playlist tracklist from Spotify embed")
    tracks = [{"id": t["uri"].split(":")[-1], "title": t.get("title", ""),
               "artist": t.get("subtitle", "")} for t in tl if t.get("uri")]
    nm = oembed("playlist", playlist_id).get("title", "")
    return {"name": nm, "tracks": tracks}


def album_track_ids(doc):
    """Ids that already live inside the ALBUMS array (not standalone tiles)."""
    try:
        albums, _, _ = read_albums(doc)
    except SystemExit:
        return set()
    return {t["id"] for al in albums for t in al.get("tracks", [])}


# ── HTML builders ────────────────────────────────────────────────────

def cover_urls(chash):
    return (f"https://i.scdn.co/image/ab67616d0000b273{chash}",
            f"https://i.scdn.co/image/ab67616d00001e02{chash}")


def build_single_tile(*, genre, track_id, chash, artist, title, year, award, ia):
    u640, u300 = cover_urls(chash)
    alt = f"{artist} — {title} · сведение и мастеринг Podlesny Twins"
    aw = f' data-aw="{award}"' if award else ""
    art = esc(artist) + ('<sup class="ia">*</sup>' if ia else "")
    return (f'      <button class="tile" data-g="{genre}"{aw} data-id="{track_id}" '
            f'onclick="play(this)"><img src="{u640}" alt="{esc(alt)}" loading="lazy" '
            f'srcset="{u300} 300w, {u640} 640w" sizes="(max-width:560px) 46vw, 200px" '
            f'decoding="async"><span class="ov"><i class="pl">&#9654;</i></span>'
            f'<span class="meta"><span class="art">{art}</span>'
            f'<span class="trk">{esc(title)}</span>'
            f'<span class="yr">{esc(str(year))}</span></span></button>')


def build_album_tile(*, genre, index, chash, artist, name, ntracks, award, ia):
    u640, u300 = cover_urls(chash)
    alt = f"{artist} — {name} (альбом) · сведение и мастеринг Podlesny Twins"
    aw = f' data-aw="{award}"' if award else ""
    art = esc(artist) + ('<sup class="ia">*</sup>' if ia else "")
    return (f'      <button class="tile album" data-g="{genre}"{aw} '
            f'onclick="openAlbum({index})"><img src="{u640}" alt="{esc(alt)}" '
            f'loading="lazy" srcset="{u300} 300w, {u640} 640w" '
            f'sizes="(max-width:560px) 46vw, 200px" decoding="async">'
            f'<span class="abadge">{ntracks} {plt(ntracks)}</span>'
            f'<span class="ov"><i class="pl">&#9776;</i></span>'
            f'<span class="meta"><span class="art">{art}</span>'
            f'<span class="trk">{esc(name)}</span>'
            f'<span class="yr">альбом</span></span></button>')


def genre_for_artist(doc, artist):
    key = primary(artist)
    for line in doc.split("\n"):
        if 'class="tile"' not in line and 'class="tile album"' not in line:
            continue
        gm = re.search(r'data-g="([^"]+)"', line)
        am = re.search(r'<span class="art">(.*?)(?:<sup|</span>)', line)
        if gm and am and primary(re.sub(r"<[^>]+>", "", am.group(1))) == key:
            return gm.group(1)
    return ""


def insert_tile(doc, tile, artist):
    """Insert a tile line after the last tile of the same artist (any kind).
    A brand-new artist goes into the MIDDLE of the grid, never the top: the
    top ~20-30 tiles are hand-picked strongest mixes and must stay put."""
    lines = doc.split("\n")
    key = primary(artist)
    anchor = grid_open = -1
    tile_lines = []
    for i, ln in enumerate(lines):
        if 'id="grid"' in ln:
            grid_open = i
        if '<button class="tile' in ln:
            tile_lines.append(i)
            m = re.search(r'<span class="art">(.*?)(?:<sup|</span>)', ln)
            if m and primary(re.sub(r"<[^>]+>", "", m.group(1))) == key:
                anchor = i
    if anchor >= 0:                              # same artist: keep grouped
        lines.insert(anchor + 1, tile)
    elif tile_lines:                             # new artist: middle, not top
        lines.insert(tile_lines[len(tile_lines) // 2] + 1, tile)
    elif grid_open >= 0:                         # empty grid: first tile
        lines.insert(grid_open + 1, tile)
    else:
        die('cannot find <div class="grid" id="grid"> in index.html')
    return "\n".join(lines)


def remove_tile(doc, track_id):
    lines = doc.split("\n")
    kept = [ln for ln in lines if f'data-id="{track_id}"' not in ln]
    return "\n".join(kept), len(lines) - len(kept)


def read_albums(doc):
    """Return (albums_list, start_idx, end_idx) for `var ALBUMS=[...];`."""
    m = re.search(r"var ALBUMS=(\[.*?\]);", doc, re.S)
    if not m:
        die("cannot find `var ALBUMS=[...]` in index.html")
    return json.loads(m.group(1)), m.start(1), m.end(1)


def write_albums(doc, albums, s, e):
    return doc[:s] + json.dumps(albums, ensure_ascii=False) + doc[e:]


def load_roles(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def save_roles(path, data):
    body = ",\n".join(f"{json.dumps(k)}: {json.dumps(v, ensure_ascii=False)}"
                      for k, v in data.items())
    path.write_text("{\n" + body + "\n}\n", encoding="utf-8")


def run_build(repo):
    r = subprocess.run([sys.executable, "build_who_mixed.py"], cwd=repo)
    if r.returncode != 0:
        die("build_who_mixed.py failed")


def out(rec, as_json):
    if as_json:
        print("RESULT " + json.dumps(rec, ensure_ascii=False))


# ── commands ─────────────────────────────────────────────────────────

def add_tokens(tokens, a, doc, roles, skip_ids=frozenset()):
    """Core add loop: resolve each token, insert tile, record role.
    Returns (doc, planned, unknown). Mutates `roles`. Writes nothing."""
    ia_flag = a.ia
    award = a.award.upper() if a.award else ""
    planned, unknown = [], []
    for token in tokens:
        forced_genre = ""
        if "@" in token:  # optional trailing @GENRE (only if it names a bucket)
            base, _, suf = token.rpartition("@")
            if suf.upper() in GENRES:
                token, forced_genre = base, suf.upper()
        tid = parse_id(token)
        if tid in skip_ids or f'data-id="{tid}"' in doc:
            print(f"skip: {tid} already on site")
            continue
        meta = fetch_track(tid)
        artist = a.artist or meta["artist"]
        title = a.title or meta["title"]
        year = a.year or meta["year"]
        if not (artist and title and year):
            die(f"{tid}: missing artist/title/year from Spotify; pass overrides")
        genre = (forced_genre or a.genre or genre_for_artist(doc, artist)).upper()
        if not genre:
            unknown.append({"id": tid, "artist": artist, "title": title, "year": year})
            continue
        if genre not in GENRES:
            die(f"genre must be one of {sorted(GENRES)}")
        ia = ia_flag if ia_flag is not None else (primary(artist) in IA)
        tile = build_single_tile(genre=genre, track_id=tid, chash=meta["cover_hash"],
                                 artist=artist, title=title, year=year, award=award, ia=ia)
        doc = insert_tile(doc, tile, artist)  # so same-artist siblings resolve genre
        roles[tid] = a.role
        rec = {"id": tid, "artist": artist, "title": title, "year": year,
               "genre": genre, "role": a.role, "award": award, "ia": ia}
        planned.append(rec)
        out(rec, a.json)
        print(f"+ {artist} — «{title}» [{genre}] {year} role={a.role}"
              + (f" aw={award}" if award else "") + (" IA*" if ia else ""))
    return doc, planned, unknown


def finalize_adds(a, repo, index, roles_path, doc, roles, planned, unknown):
    if unknown:
        for u in unknown:
            print(f"GENRE_UNKNOWN id={u['id']} artist={u['artist']!r} "
                  f"title={u['title']!r} year={u['year']} — rerun with @GENRE "
                  f"or --genre {sorted(GENRES)}", file=sys.stderr)
        die(f"{len(unknown)} track(s) need a genre; nothing written", code=3)
    if not planned:
        print("nothing to add.")
        return
    if a.dry_run:
        print(f"dry-run: {len(planned)} track(s) resolved, nothing written.")
        return
    index.write_text(doc, encoding="utf-8")
    save_roles(roles_path, roles)
    if not a.no_build:
        run_build(repo)
    else:
        print("skipped build (--no-build).")


def cmd_add(a, repo, index, roles_path):
    if len(a.links) != 1 and (a.artist or a.title or a.year):
        die("--artist/--title/--year only allowed with a single link")
    doc = index.read_text(encoding="utf-8")
    roles = load_roles(roles_path)
    doc, planned, unknown = add_tokens(a.links, a, doc, roles)
    finalize_adds(a, repo, index, roles_path, doc, roles, planned, unknown)


def cmd_sync(a, repo, index, roles_path):
    """Add every playlist track not already on the site (as tile or album track)."""
    if a.artist or a.title or a.year:
        die("--artist/--title/--year not allowed for sync (many tracks)")
    doc = index.read_text(encoding="utf-8")
    roles = load_roles(roles_path)
    pl = fetch_playlist(parse_id(a.links[0]))
    skip = album_track_ids(doc)
    on_site = sum(1 for t in pl["tracks"] if t["id"] in skip or f'data-id="{t["id"]}"' in doc)
    new_ids = [t["id"] for t in pl["tracks"]
               if t["id"] not in skip and f'data-id="{t["id"]}"' not in doc]
    print(f"playlist «{pl['name']}»: {len(pl['tracks'])} tracks "
          f"({on_site} already on site, {len(new_ids)} new)")
    if not new_ids:
        print("nothing new to add.")
        return
    doc, planned, unknown = add_tokens(new_ids, a, doc, roles)

    # sync is NOT atomic: add every resolvable track, list the rest as a to-do
    # (a works-playlist has many artists — one new artist must not block all).
    if unknown:
        print(f"\n{len(unknown)} track(s) need a genre — add them with:",
              file=sys.stderr)
        for u in unknown:
            print(f'  add "https://open.spotify.com/track/{u["id"]}@<GENRE>"  '
                  f'# {u["artist"]} — {u["title"]}', file=sys.stderr)
    if not planned:
        print("no auto-resolvable tracks (all need a genre); nothing written.")
        sys.exit(3 if unknown else 0)
    if a.dry_run:
        print(f"dry-run: {len(planned)} resolved, {len(unknown)} need genre; "
              f"nothing written.")
        sys.exit(3 if unknown else 0)
    index.write_text(doc, encoding="utf-8")
    save_roles(roles_path, roles)
    if not a.no_build:
        run_build(repo)
    else:
        print("skipped build (--no-build).")
    print(f"synced {len(planned)} track(s)."
          + (f" {len(unknown)} still need a genre (see above)." if unknown else ""))
    if unknown:
        sys.exit(3)


def cmd_album(a, repo, index, roles_path):
    doc = index.read_text(encoding="utf-8")
    album_id = parse_id(a.links[0])
    m = fetch_album(album_id)
    artist = a.artist or m["artist"]
    if not artist:
        die("could not derive album artist; pass --artist")
    name = a.title or m["name"]
    if a.year:  # override year for every track
        m["year"] = a.year
        for t in m["tracks"]:
            t["year"] = a.year
    genre = (a.genre or genre_for_artist(doc, artist)).upper()
    if not genre:
        print(f"GENRE_UNKNOWN album={name!r} artist={artist!r} — rerun with "
              f"--genre {sorted(GENRES)}", file=sys.stderr)
        sys.exit(3)
    if genre not in GENRES:
        die(f"genre must be one of {sorted(GENRES)}")
    albums, s, e = read_albums(doc)
    if any(al.get("name") == name and al.get("artist") == artist for al in albums):
        die(f"album «{name}» by {artist} already in ALBUMS")
    u640, _ = cover_urls(m["cover_hash"])
    obj = {"artist": artist, "name": name, "cover": u640, "tracks": m["tracks"]}
    idx = len(albums)
    ia = a.ia if a.ia is not None else (primary(artist) in IA)
    award = a.award.upper() if a.award else ""
    rec = {"album": name, "artist": artist, "genre": genre, "role": a.role,
           "ntracks": len(m["tracks"]), "year": m["year"], "ia": ia,
           "index": idx, "tracks": [t["id"] for t in m["tracks"]]}
    out(rec, a.json)
    print(f"album: {artist} — «{name}» [{genre}] {m['year']} "
          f"{len(m['tracks'])} {plt(len(m['tracks']))} role={a.role}"
          + (" IA*" if ia else ""))
    for t in m["tracks"]:
        print(f"    · {t['title']}")
    if a.dry_run:
        print("dry-run: nothing written.")
        return
    doc = write_albums(doc, albums + [obj], s, e)
    tile = build_album_tile(genre=genre, index=idx, chash=m["cover_hash"],
                            artist=artist, name=name, ntracks=len(m["tracks"]),
                            award=award, ia=ia)
    doc = insert_tile(doc, tile, artist)
    index.write_text(doc, encoding="utf-8")
    roles = load_roles(roles_path)
    for t in m["tracks"]:
        roles[t["id"]] = a.role
    save_roles(roles_path, roles)
    if not a.no_build:
        run_build(repo)
    else:
        print("skipped build (--no-build).")


def cmd_remove(a, repo, index, roles_path):
    doc = index.read_text(encoding="utf-8")
    roles = load_roles(roles_path)
    removed = []
    for token in a.links:
        tid = parse_id(token)
        doc2, n = remove_tile(doc, tid)
        if n == 0:
            print(f"not found as a single-track tile: {tid} "
                  f"(album tracks have no standalone tile)")
            continue
        doc = doc2
        roles.pop(tid, None)
        removed.append(tid)
        print(f"- removed {tid} ({n} line(s))")
    if not removed:
        print("nothing removed.")
        return
    if a.dry_run:
        print(f"dry-run: would remove {len(removed)}, nothing written.")
        return
    index.write_text(doc, encoding="utf-8")
    save_roles(roles_path, roles)
    if not a.no_build:
        run_build(repo)  # regenerates + prunes orphaned track/ pages


def main():
    argv = sys.argv[1:]
    if argv and argv[0] not in {"add", "album", "sync", "remove", "build"}:
        argv = ["add"] + argv
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["add", "album", "sync", "remove", "build"])
    ap.add_argument("links", nargs="*")
    ap.add_argument("--genre", default="")
    ap.add_argument("--year", default="")
    ap.add_argument("--artist", default="")
    ap.add_argument("--title", default="")
    ap.add_argument("--role", default="mix")
    ap.add_argument("--award", default="")
    ap.add_argument("--ia", dest="ia", action="store_true", default=None)
    ap.add_argument("--no-ia", dest="ia", action="store_false")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-build", action="store_true")
    ap.add_argument("--repo", default=str(Path.home() / "works-site"))
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    if a.role not in ROLES:
        die(f"--role must be one of {sorted(ROLES)}")
    if a.award and a.award.upper() not in AWARDS:
        die(f"--award must be one of {sorted(AWARDS)}")
    repo = Path(a.repo).expanduser()
    index, roles_path = repo / "index.html", repo / "roles.json"
    if not index.is_file():
        die(f"no index.html at {index}")

    if a.cmd == "build":
        run_build(repo)
        return
    if not a.links:
        die(f"{a.cmd}: need at least one link/id")
    {"add": cmd_add, "album": cmd_album, "sync": cmd_sync,
     "remove": cmd_remove}[a.cmd](a, repo, index, roles_path)


if __name__ == "__main__":
    main()
