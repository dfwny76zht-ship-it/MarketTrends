"""Edit version of the investor page for Markus: same files, served behind the Market Trends login, with
text overrides saved to texts/texts.json (nginx serves that file to Markus' page on :8446)."""

from __future__ import annotations

import html
import json
import os
import re
from html.parser import HTMLParser
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel

from .auth import current_user

router = APIRouter()
SITE = Path(os.environ.get("MARKUS_DIR", "/markus"))
TEXTS = SITE / "texts" / "texts.json"
FILES = {"index.html", "app.js", "style.css", "echarts.min.js", "data.json", "texts/texts.json"}
ALLOWED = {"b", "strong", "em", "i", "br", "a", "span", "sup", "sub"}


class _Clean(HTMLParser):
    """Keeps text and a few inline tags (links only with http(s) targets); drops everything else."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        elif tag in ALLOWED and not self.skip:
            if tag == "a":
                href = dict(attrs).get("href") or ""
                if re.match(r"^https?://", href):
                    self.out.append(f'<a href="{html.escape(href)}" rel="noopener noreferrer">')
                else:
                    self.out.append("<a>")
            elif tag == "span":
                cls = dict(attrs).get("class") or ""
                self.out.append('<span class="big">' if cls == "big" else "<span>")
            else:
                self.out.append(f"<{tag}>")
        elif tag in ("div", "p") and not self.skip and self.out:
            self.out.append("<br>")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)
        elif tag in ALLOWED and tag != "br" and not self.skip:
            self.out.append(f"</{tag}>")

    def handle_data(self, data):
        if not self.skip:
            self.out.append(html.escape(data, quote=False))


def clean(fragment: str) -> str:
    p = _Clean()
    p.feed(fragment)
    p.close()
    return "".join(p.out).strip()


def _read() -> dict:
    try:
        return json.loads(TEXTS.read_text())
    except (OSError, ValueError):
        return {}


@router.get("/markus-edit")
def edit_root():
    return RedirectResponse("/markus-edit/")


@router.get("/markus-edit/{path:path}")
def edit_file(path: str, request: Request):
    try:
        current_user(request)
    except HTTPException:
        return RedirectResponse("/")
    path = path or "index.html"
    if path not in FILES:
        raise HTTPException(404)
    full = SITE / path
    if path == "texts/texts.json" and not full.exists():
        return {}
    if not full.is_file():
        raise HTTPException(404)
    return FileResponse(full, headers={"Cache-Control": "no-store"})


class TextsIn(BaseModel):
    texts: dict[str, str | None]  # None = back to the automatic text


@router.post("/api/markus/texts", dependencies=[Depends(current_user)])
def save_texts(body: TextsIn):
    texts = _read()
    for key, value in body.texts.items():
        if not re.fullmatch(r"[a-z0-9_-]{1,40}", key):
            raise HTTPException(422, f"Unknown text block {key}.")
        if value is None:
            texts.pop(key, None)
        else:
            texts[key] = clean(value)[:20000]
    TEXTS.parent.mkdir(parents=True, exist_ok=True)
    tmp = TEXTS.with_suffix(".tmp")
    tmp.write_text(json.dumps(texts, ensure_ascii=False, indent=1))
    os.replace(tmp, TEXTS)
    return texts
