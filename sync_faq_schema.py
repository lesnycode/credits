#!/usr/bin/env python3
"""Rebuild the FAQPage JSON-LD in faq/index.html from the page's visible text.

Google drops FAQ markup whose answers don't match what the visitor sees, so the
schema must never be hand-edited: edit the <details> blocks, then run this.

    python3 sync_faq_schema.py
"""
from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PAGE = ROOT / "faq" / "index.html"


def strip_tags(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", s))).strip()


def main() -> int:
    src = PAGE.read_text(encoding="utf-8")

    pairs = re.findall(
        r"<summary>(.*?)</summary>\s*<p class=\"ans\">(.*?)</p>", src, re.S
    )
    if not pairs:
        print("no <details> blocks found — aborting", file=sys.stderr)
        return 1

    block = re.search(r'<script type="application/ld\+json">(.*?)</script>', src, re.S)
    if not block:
        print("no JSON-LD block found — aborting", file=sys.stderr)
        return 1

    data = json.loads(block.group(1))
    faq = next((n for n in data["@graph"] if n.get("@type") == "FAQPage"), None)
    if faq is None:
        print("no FAQPage node in @graph — aborting", file=sys.stderr)
        return 1

    faq["mainEntity"] = [
        {
            "@type": "Question",
            "name": strip_tags(q),
            "acceptedAnswer": {"@type": "Answer", "text": strip_tags(a)},
        }
        for q, a in pairs
    ]

    rebuilt = json.dumps(data, ensure_ascii=False)
    src = src[: block.start(1)] + rebuilt + src[block.end(1) :]
    PAGE.write_text(src, encoding="utf-8")
    print(f"faq/index.html: JSON-LD пересобран из HTML, вопросов — {len(pairs)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
