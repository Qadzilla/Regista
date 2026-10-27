"""The share preview: every page names the same 1200x630 image, and the app serves it (docs/brand/make_images.py)."""

import re
from pathlib import Path

from fastapi.testclient import TestClient

from regista.api import app

STATIC = Path(__file__).resolve().parents[1] / "src" / "regista" / "static"
IMAGE = "/static/shared/regista-share.png"


def test_every_page_has_the_share_preview():
    pages = sorted(STATIC.glob("*/index.html"))
    assert len(pages) >= 6
    for p in pages:
        s = p.read_text()
        img = re.search(r'<meta property="og:image" content="([^"]+)">', s)
        assert img and img.group(1).startswith("https://") and img.group(1).endswith(IMAGE), p
        assert '<meta name="twitter:card" content="summary_large_image">' in s, p
        assert re.search(r'<meta property="og:title" content="[^"]+">', s), p


def test_the_image_is_served_at_its_size():
    from PIL import Image

    r = TestClient(app).get(IMAGE)
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    with Image.open(STATIC / "shared" / "regista-share.png") as im:
        assert im.size == (1200, 630)
