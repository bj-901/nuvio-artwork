#!/usr/bin/env python3
"""
Regenerate Nuvio Discover hero backdrops from the live Stremio catalogs.
The generator reads catalog entries, resolves their metadata backgrounds, and
composes a dark Violet Platinum collage. It never overwrites a backdrop unless
it successfully builds a replacement with enough usable images.
"""
from __future__ import annotations

import concurrent.futures
import io
import json
import os
import random
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance, ImageOps

REPO_ROOT = Path(__file__).resolve().parents[1]
DISCOVER_DIR = REPO_ROOT / "Discover"
WIDTH, HEIGHT = 1920, 1080
MAX_ITEMS_PER_CATALOG = 24
MAX_BACKDROPS_PER_CATEGORY = 12
REQUEST_TIMEOUT = 25
USER_AGENT = "Nuvio-Discover-Artwork-Generator/1.0"

# Current catalog IDs from the user's existing Nuvio Discover profile.
CATEGORY_CATALOGS = {
    "Trending": [("movie", "mdblist.206584"), ("series", "mdblist.207259")],
    "Popular": [("movie", "mdblist.221823"), ("series", "mdblist.221824")],
    "Latest Releases": [("movie", "mdblist.207268"), ("series", "mdblist.208593")],
    "Top Rated": [("movie", "mdblist.207276"), ("series", "mdblist.207277")],
    "For You": [
        ("movie", "aicat_list_203374"),
        ("series", "aicat_list_203375"),
        ("movie", "aicat_list_203376"),
        ("series", "aicat_list_203377"),
    ],
}

# Each category receives a slightly different tint while retaining one visual identity.
ACCENTS = {
    "Trending": (139, 73, 255),
    "Popular": (166, 52, 225),
    "Latest Releases": (117, 74, 255),
    "Top Rated": (185, 151, 255),
    "For You": (132, 91, 220),
}

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": USER_AGENT})


def log(message: str) -> None:
    print(message, flush=True)


def env_manifests() -> list[str]:
    keys = [
        "AIO_METADATA_MANIFEST_URL_1",
        "AIO_METADATA_MANIFEST_URL_2",
        "BINGECAT_MANIFEST_URL",
    ]
    urls = [os.environ.get(k, "").strip() for k in keys]
    urls = [u for u in urls if u]
    if not urls:
        raise RuntimeError(
            "No add-on manifest URLs found. Configure AIO_METADATA_MANIFEST_URL_1, "
            "AIO_METADATA_MANIFEST_URL_2, and BINGECAT_MANIFEST_URL as GitHub Actions secrets."
        )
    return urls


def get_json(url: str) -> dict:
    response = SESSION.get(url, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.json()


def addon_base_url(manifest_url: str) -> str:
    """Convert an add-on manifest URL into the base URL used by catalog/meta routes."""
    clean = manifest_url.split("?", 1)[0].rstrip("/")
    if clean.endswith("/manifest.json"):
        return clean[:-len("/manifest.json")]
    return clean


def discover_catalog_hosts(manifest_urls: list[str]) -> dict[str, str]:
    """Return catalog_id -> add-on base URL, validating IDs against manifests."""
    found: dict[str, str] = {}
    for manifest_url in manifest_urls:
        base = addon_base_url(manifest_url)
        try:
            manifest = get_json(manifest_url)
            addon_name = manifest.get("name") or base
            catalogs = manifest.get("catalogs") or []
            log(f"Manifest OK: {addon_name} ({len(catalogs)} catalogs)")
            for catalog in catalogs:
                catalog_id = catalog.get("id")
                if catalog_id:
                    found.setdefault(str(catalog_id), base)
        except Exception as exc:
            log(f"WARNING: Could not read manifest {base}: {exc}")
    return found


def catalog_url(base: str, media_type: str, catalog_id: str) -> str:
    return f"{base}/catalog/{media_type}/{catalog_id}.json"


def meta_url(base: str, media_type: str, item_id: str) -> str:
    return f"{base}/meta/{media_type}/{item_id}.json"


def get_catalog_items(base: str, media_type: str, catalog_id: str) -> list[dict]:
    data = get_json(catalog_url(base, media_type, catalog_id))
    metas = data.get("metas") or []
    return metas[:MAX_ITEMS_PER_CATALOG]


def resolve_background(base: str, media_type: str, item: dict) -> str | None:
    # Catalog responses sometimes already contain the background URL.
    bg = item.get("background")
    if bg and str(bg).startswith("http"):
        return str(bg)

    item_id = item.get("id")
    if not item_id:
        return None
    try:
        data = get_json(meta_url(base, media_type, str(item_id)))
        meta = data.get("meta") or {}
        bg = meta.get("background") or meta.get("landscape") or meta.get("backdrop")
        if bg and str(bg).startswith("http"):
            return str(bg)
    except Exception as exc:
        log(f"  metadata skipped for {item.get('name', item_id)}: {exc}")
    return None


def download_image(url: str) -> Image.Image | None:
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return None
        response = SESSION.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        image = Image.open(io.BytesIO(response.content)).convert("RGB")
        if image.width < 400 or image.height < 200:
            return None
        return image
    except Exception as exc:
        log(f"  image download skipped: {exc}")
        return None


def collect_images(category: str, catalog_hosts: dict[str, str]) -> list[Image.Image]:
    collected: list[Image.Image] = []
    seen: set[str] = set()
    for media_type, catalog_id in CATEGORY_CATALOGS[category]:
        base = catalog_hosts.get(catalog_id)
        if not base:
            log(f"  catalog not found in supplied manifests: {catalog_id}")
            continue
        try:
            items = get_catalog_items(base, media_type, catalog_id)
            log(f"  {catalog_id}: {len(items)} catalog items")
        except Exception as exc:
            log(f"  catalog failed {catalog_id}: {exc}")
            continue

        for item in items:
            bg_url = resolve_background(base, media_type, item)
            if not bg_url or bg_url in seen:
                continue
            seen.add(bg_url)
            image = download_image(bg_url)
            if image:
                collected.append(image)
            if len(collected) >= MAX_BACKDROPS_PER_CATEGORY:
                return collected
    return collected


def cover_crop(image: Image.Image, target_size: tuple[int, int]) -> Image.Image:
    return ImageOps.fit(image, target_size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.42))


def make_violet_platinum_collage(images: list[Image.Image], category: str) -> Image.Image:
    """Compose title backdrops into a cinematic, dark purple/silver layered mosaic."""
    if len(images) < 3:
        raise RuntimeError(
            f"Only {len(images)} usable title backdrops were found for {category}; "
            "at least 3 are required. Existing backdrop was left untouched."
        )

    random.seed(category)
    accent = ACCENTS[category]
    canvas = Image.new("RGB", (WIDTH, HEIGHT), (7, 6, 12))

    # Use a large feature image with two smaller supporting panels.
    random.shuffle(images)
    hero = cover_crop(images[0], (WIDTH, HEIGHT))
    hero = ImageEnhance.Color(hero).enhance(0.68)
    hero = ImageEnhance.Contrast(hero).enhance(1.12)
    hero = ImageEnhance.Brightness(hero).enhance(0.58)
    canvas.paste(hero, (0, 0))

    # Darken the center and edges so the category logo remains legible.
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (4, 3, 10, 112))
    canvas = Image.alpha_composite(canvas.convert("RGBA"), overlay)

    # Violet tint, blended gently rather than flattening the source imagery.
    tint = Image.new("RGBA", (WIDTH, HEIGHT), (*accent, 46))
    canvas = Image.alpha_composite(canvas, tint)

    # Three staggered translucent image bands create an editorial streaming collage.
    panel_specs = [
        ((0, 0, 640, 360), images[1]),
        ((1280, 0, 1920, 360), images[2]),
        ((0, 720, 640, 1080), images[3] if len(images) > 3 else images[1]),
        ((1280, 720, 1920, 1080), images[4] if len(images) > 4 else images[2]),
    ]
    for (x1, y1, x2, y2), source in panel_specs:
        panel = cover_crop(source, (x2 - x1, y2 - y1))
        panel = ImageEnhance.Color(panel).enhance(0.58)
        panel = ImageEnhance.Brightness(panel).enhance(0.62)
        panel = Image.blend(panel, Image.new("RGB", panel.size, accent), 0.18)
        panel_rgba = panel.convert("RGBA")
        panel_rgba.putalpha(118)
        canvas.alpha_composite(panel_rgba, (x1, y1))

    # Soft dark center band for title logo placement.
    center_shade = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(center_shade)
    draw.rectangle((360, 260, 1560, 820), fill=(4, 3, 9, 92))
    center_shade = center_shade.filter(ImageFilter.GaussianBlur(110))
    canvas = Image.alpha_composite(canvas, center_shade)

    # Metallic/violet contour accents at the outer edges.
    lines = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    ld = ImageDraw.Draw(lines)
    for offset in range(0, 5):
        y = 115 + offset * 13
        ld.arc((-250, y - 180, 820, y + 430), start=205, end=345,
               fill=(205, 190, 255, 34 - offset * 4), width=3)
        y2 = 865 + offset * 12
        ld.arc((1160, y2 - 390, 2220, y2 + 220), start=20, end=160,
               fill=(*accent, 34 - offset * 4), width=3)
    lines = lines.filter(ImageFilter.GaussianBlur(1.2))
    canvas = Image.alpha_composite(canvas, lines)

    # Edge vignette.
    vignette = Image.new("L", (WIDTH, HEIGHT), 0)
    vd = ImageDraw.Draw(vignette)
    vd.ellipse((-260, -200, WIDTH + 260, HEIGHT + 200), fill=190)
    vignette = vignette.filter(ImageFilter.GaussianBlur(190))
    dark = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 150))
    dark.putalpha(Image.eval(vignette, lambda p: 150 - int(p * 0.55)))
    canvas = Image.alpha_composite(canvas, dark)

    return canvas.convert("RGB")


def main() -> int:
    manifests = env_manifests()
    catalog_hosts = discover_catalog_hosts(manifests)
    if not catalog_hosts:
        raise RuntimeError("No catalog IDs were found in the supplied add-on manifests.")

    failures = []
    updated = []
    for category in CATEGORY_CATALOGS:
        log(f"\n=== {category} ===")
        try:
            images = collect_images(category, catalog_hosts)
            log(f"  usable backdrops: {len(images)}")
            output = make_violet_platinum_collage(images, category)
            destination_dir = DISCOVER_DIR / category / "Backdrop"
            destination_dir.mkdir(parents=True, exist_ok=True)
            destination = destination_dir / "backdrop.webp"
            temp = destination.with_suffix(".tmp.webp")
            output.save(temp, "WEBP", quality=91, method=6)
            temp.replace(destination)
            updated.append(category)
            log(f"  Wrote {destination.relative_to(REPO_ROOT)}")
        except Exception as exc:
            failures.append((category, str(exc)))
            log(f"  ERROR: {exc}")

    log("\n=== Summary ===")
    log(f"Updated: {', '.join(updated) if updated else 'none'}")
    if failures:
        for category, error in failures:
            log(f"Not updated — {category}: {error}")
        return 1
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        log(f"FATAL: {error}")
        raise SystemExit(1)
