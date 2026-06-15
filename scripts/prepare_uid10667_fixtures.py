#!/usr/bin/env python3
"""Copy UID10667 course PDFs into eval fixtures and build keywords.json."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "assets" / "eval_fixtures" / "uid10667"

SOURCE_MAP: dict[str, str] = {
    "chapter1-digital-literacy.pdf": "chapter 1 Digital Literacy.pdf",
    "chapter2-computer-use.pdf": (
        "Chapter 2 Digital Literacy Level 1 การใช้งานคอมพิวเตอร์.pdf"
    ),
    "chapter3-internet-security.pdf": (
        "chapter 3 การใช้งานอินเตอร์เน็ต และ การใช้งานเพื่อความมั่นคงปลอดภัย.pdf"
    ),
}

DEFAULT_SOURCE = (
    "/Users/tim/Library/CloudStorage/GoogleDrive-isaiah.pwnpk@gmail.com"
    "/My Drive/_Study/Year 2 Term 3/UID10667"
)

STOPWORDS = frozenset(
    """
    the a an and or but in on at to for of is are was were be been being
    this that these those with from by as it its they them their we you your
    have has had will can may not no yes all any each other such than then
    also into over after before about when where which who what how why
    การ ใน ของ และ เป็น ได้ มี ไป ที่ จาก ให้ ว่า แล้ว นี้ นั้น เมื่อ
    """.split()
)


def _extract_pdf_text(pdf_path: Path) -> str:
    sys.path.insert(0, str(REPO_ROOT))
    from src.pdf.intake import extract_pdf_text_from_path

    return extract_pdf_text_from_path(str(pdf_path))


def _keywords_from_text(text: str, *, limit: int = 12) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()

    def add(term: str) -> None:
        t = term.strip()
        if not t or len(t) < 3:
            return
        key = t.lower()
        if key in seen:
            return
        seen.add(key)
        found.append(t)

    for anchor in (
        "Digital Literacy",
        "UID10667",
        "Sripatum",
        "online learning",
        "computer",
        "internet",
        "security",
        "privacy",
    ):
        if anchor.lower() in text.lower():
            add(anchor)

    for line in text.splitlines():
        line = line.strip()
        if not line or len(line) > 80:
            continue
        if re.match(r"^[\d\s\.]+$", line):
            continue
        if re.match(r"^[A-Z][A-Za-z0-9\s\-]{2,60}$", line):
            add(line)
        if re.search(r"[\u0E00-\u0E7F]", line) and 4 <= len(line) <= 40:
            add(line)

    words = re.findall(r"[A-Za-z\u0E00-\u0E7F]{4,}", text)
    freq = Counter(w.lower() for w in words if w.lower() not in STOPWORDS)
    for word, _ in freq.most_common(30):
        if word.isascii():
            add(word.title() if word.islower() else word)
        else:
            add(word)
        if len(found) >= limit:
            break

    return found[:limit]


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare UID10667 eval fixtures")
    parser.add_argument(
        "--source",
        default=DEFAULT_SOURCE,
        help="Google Drive UID10667 folder path",
    )
    parser.add_argument(
        "--skip-copy",
        action="store_true",
        help="Only regenerate keywords.json from existing PDFs",
    )
    args = parser.parse_args()
    source_dir = Path(args.source).expanduser()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    keywords: dict[str, list[str]] = {}

    for dest_name, src_name in SOURCE_MAP.items():
        dest = OUT_DIR / dest_name
        if not args.skip_copy:
            src = source_dir / src_name
            if not src.exists():
                print(f"[WARN] Missing source PDF: {src}")
                continue
            shutil.copy2(src, dest)
            print(f"[OK] Copied {src_name} -> {dest_name}")

        if dest.exists():
            try:
                text = _extract_pdf_text(dest)
                keywords[dest_name] = _keywords_from_text(text)
                print(f"[OK] Keywords for {dest_name}: {keywords[dest_name][:5]}...")
            except Exception as exc:
                print(f"[WARN] Could not extract {dest_name}: {exc}")
                keywords[dest_name] = ["Digital Literacy", "UID10667"]

    meta = {
        "course": "UID10667 Digital Literacy",
        "chapters": keywords,
        "criticism_prompt_keyword": keywords.get(
            "chapter1-digital-literacy.pdf", ["Digital Literacy"]
        )[0],
    }
    (OUT_DIR / "keywords.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[DONE] Fixtures in {OUT_DIR}")


if __name__ == "__main__":
    main()
