"""Gallery — list the images dropped into frontend/gallery/ so the UI can show them.

Zero-DB: the folder IS the gallery. Files are served as static assets by the frontend
mount at /gallery/<file>; this endpoint just enumerates them (+ optional captions).
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter

router = APIRouter(prefix="/api/gallery", tags=["gallery"])

GALLERY_DIR = Path(__file__).resolve().parents[2] / "frontend" / "gallery"
_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".avif"}


def _captions() -> dict:
    f = GALLERY_DIR / "captions.json"
    if f.exists():
        try:
            return json.loads(f.read_text())
        except Exception:  # noqa: BLE001
            return {}
    return {}


def _pretty(stem: str) -> str:
    return stem.replace("_", " ").replace("-", " ").strip().title()


@router.get("")
def list_gallery() -> list[dict]:
    if not GALLERY_DIR.exists():
        return []
    caps = _captions()
    items = []
    for f in sorted(GALLERY_DIR.iterdir(), key=lambda p: p.name.lower()):
        if f.is_file() and f.suffix.lower() in _EXTS:
            items.append({
                "file": f.name,
                "url": f"/gallery/{f.name}",
                "caption": caps.get(f.name) or _pretty(f.stem),
            })
    return items
