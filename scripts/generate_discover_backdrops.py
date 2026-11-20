#!/usr/bin/env python3
"""
Refresh Nuvio Discover cover cards and hero backdrops from the live Stremio catalogs.

- Cover: portrait-poster collage, no embedded wording.
- Backdrop: one dominant current title backdrop, subtly blended with supporting
  title backdrops and Violet Platinum color grading.
- Logo: static transparent Violet Platinum typography installed separately.
Existing files are replaced only after a category has enough valid source images.
"""
from __future__ import annotations

import io
import os
import random
from pathlib import Path
from urllib.parse import urlparse

import requests
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps

REPO_ROOT = Path(__file__).resolve().parents[1]
DISCOVER_DIR = REPO_ROOT / "Discover"

COVER_SIZE = (1536, 864)
BACKDROP_SIZE = (3840, 2160)  # Native 4K UHD output for large TVs
MAX_ITEMS_PER_CATALOG = 30
MAX_POSTERS = 30
MAX_BACKDROPS = 18
TIMEOUT = 25
USER_AGENT = "Nuvio-Discover-Artwork-Generator/2.2-4K-Randomized"

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

ACCENTS = {
    "Trending": (137, 74, 255),
    "Popular": (160, 75, 225),
    "Latest Releases": (123, 83, 255),
    "Top Rated": (183, 157, 255),
    "For You": (143, 105, 220),
}

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": USER_AGENT})


def log(message: str) -> None:
    print(message, flush=True)


def manifest_urls() -> list[str]:
    names = (
        "AIO_METADATA_MANIFEST_URL_1",
        "AIO_METADATA_MANIFEST_URL_2",
        "BINGECAT_MANIFEST_URL",
    )
    urls = [os.environ.get(name, "").strip() for name in names]
    urls = [url for url in urls if url]
    if not urls:
        raise RuntimeError("No add-on manifest URLs are configured in GitHub Actions secrets.")
    return urls


def addon_base(manifest_url: str) -> str:
    clean = manifest_url.split("?", 1)[0].rstrip("/")
    return clean[:-len("/manifest.json")] if clean.endswith("/manifest.json") else clean


def get_json(url: str) -> dict:
    response = SESSION.get(url, timeout=TIMEOUT)
    response.raise_for_status()
    return response.json()


def find_catalog_hosts(urls: list[str]) -> dict[str, str]:
    hosts: dict[str, str] = {}
    for manifest_url in urls:
        base = addon_base(manifest_url)
        try:
            manifest = get_json(manifest_url)
            catalogs = manifest.get("catalogs") or []
            log(f"Manifest OK: {manifest.get('name', base)} ({len(catalogs)} catalogs)")
            for catalog in catalogs:
                cid = catalog.get("id")
                if cid:
                    hosts.setdefault(str(cid), base)
        except Exception as exc:
            log(f"WARNING: manifest unavailable: {base}: {exc}")
    return hosts


def fetch_catalog(base: str, media_type: str, catalog_id: str) -> list[dict]:
    url = f"{base}/catalog/{media_type}/{catalog_id}.json"
    payload = get_json(url)
    return (payload.get("metas") or [])[:MAX_ITEMS_PER_CATALOG]


def fetch_meta(base: str, media_type: str, item_id: str) -> dict:
    payload = get_json(f"{base}/meta/{media_type}/{item_id}.json")
    return payload.get("meta") or {}


def valid_http_url(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https"):
        return None
    # TMDB image paths often arrive as w500/w780/w1280. Request the original
    # image instead of accepting a thumbnail and enlarging it to 4K.
    if parsed.netloc.lower() in ("image.tmdb.org", "www.image.tmdb.org"):
        value = value.replace("/t/p/w500/", "/t/p/original/")
        value = value.replace("/t/p/w780/", "/t/p/original/")
        value = value.replace("/t/p/w1280/", "/t/p/original/")
        value = value.replace("/t/p/w1920/", "/t/p/original/")
    return value


def download_image(url: str, min_size=(250, 250)) -> Image.Image | None:
    try:
        response = SESSION.get(url, timeout=TIMEOUT)
        response.raise_for_status()
        img = Image.open(io.BytesIO(response.content)).convert("RGB")
        if img.width < min_size[0] or img.height < min_size[1]:
            return None
        return img
    except Exception as exc:
        log(f"  image skipped: {exc}")
        return None


def collect_category_art(category: str, hosts: dict[str, str]) -> tuple[list[Image.Image], list[Image.Image]]:
    posters: list[Image.Image] = []
    backdrops: list[Image.Image] = []
    seen_posters: set[str] = set()
    seen_backdrops: set[str] = set()

    catalog_sources = CATEGORY_CATALOGS[category][:]
    random.shuffle(catalog_sources)
    for media_type, catalog_id in catalog_sources:
        base = hosts.get(catalog_id)
        if not base:
            log(f"  catalog not listed by installed manifests: {catalog_id}")
            continue
        try:
            items = fetch_catalog(base, media_type, catalog_id)
            random.shuffle(items)
            log(f"  {catalog_id}: {len(items)} current catalog items (selection shuffled)")
        except Exception as exc:
            log(f"  catalog failed {catalog_id}: {exc}")
            continue

        for item in items:
            meta = {}
            poster_url = valid_http_url(item.get("poster"))
            backdrop_url = valid_http_url(item.get("background") or item.get("landscape"))

            # Resolve missing poster/background URLs from the add-on metadata endpoint.
            if (not poster_url or not backdrop_url) and item.get("id"):
                try:
                    meta = fetch_meta(base, media_type, str(item["id"]))
                except Exception as exc:
                    log(f"  metadata skipped for {item.get('name', item.get('id'))}: {exc}")

            if not poster_url:
                poster_url = valid_http_url(meta.get("poster"))
            if not backdrop_url:
                backdrop_url = valid_http_url(meta.get("background") or meta.get("landscape"))

            if poster_url and poster_url not in seen_posters and len(posters) < MAX_POSTERS:
                seen_posters.add(poster_url)
                image = download_image(poster_url, min_size=(180, 260))
                if image:
                    posters.append(image)

            if backdrop_url and backdrop_url not in seen_backdrops and len(backdrops) < MAX_BACKDROPS:
                seen_backdrops.add(backdrop_url)
                image = download_image(backdrop_url, min_size=(1280, 720))
                if image:
                    backdrops.append(image)

            if len(posters) >= MAX_POSTERS and len(backdrops) >= MAX_BACKDROPS:
                break

    return posters, backdrops


def crop_cover(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    return ImageOps.fit(img, size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.38))


def rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius, fill=255)
    return mask


def build_cover(posters: list[Image.Image], category: str) -> Image.Image:
    if len(posters) < 5:
        raise RuntimeError(f"Only {len(posters)} usable posters for {category}; 5 are required.")

    # Use fresh, non-deterministic poster selection on every workflow run.
    selected = random.sample(posters, k=len(posters))
    canvas = Image.new("RGBA", COVER_SIZE, (7, 6, 12, 255))
    accent = ACCENTS[category]

    # Rotate between restrained editorial layouts while keeping the same Nuvio style.
    layouts = [
        [(52, 180, 250, 505), (278, 105, 285, 655), (535, 42, 466, 780), (948, 105, 285, 655), (1234, 180, 250, 505)],
        [(40, 130, 270, 600), (285, 205, 250, 500), (535, 35, 466, 790), (1000, 205, 250, 500), (1225, 130, 270, 600)],
        [(45, 230, 270, 450), (290, 95, 285, 675), (565, 65, 410, 735), (965, 95, 285, 675), (1220, 230, 270, 450)],
    ]
    specs = random.choice(layouts)
    for idx, (x, y, w, h) in enumerate(specs):
        poster = crop_cover(selected[idx], (w, h))
        poster = ImageEnhance.Color(poster).enhance(0.84)
        poster = ImageEnhance.Contrast(poster).enhance(1.08)
        # Subtle tint to unify source artwork without obscuring it.
        tint = Image.new("RGB", poster.size, accent)
        poster = Image.blend(poster, tint, 0.10)
        mask = rounded_mask((w, h), 18)

        shadow = Image.new("RGBA", (w + 34, h + 34), (0, 0, 0, 0))
        shadow_mask = Image.new("L", shadow.size, 0)
        ImageDraw.Draw(shadow_mask).rounded_rectangle((14, 14, w + 14, h + 14), 20, fill=160)
        shadow_mask = shadow_mask.filter(ImageFilter.GaussianBlur(14))
        shadow.putalpha(shadow_mask)
        canvas.alpha_composite(shadow, (x - 17, y - 8))

        poster_rgba = poster.convert("RGBA")
        poster_rgba.putalpha(mask)
        canvas.alpha_composite(poster_rgba, (x, y))

        # Fine platinum/violet edge.
        edge = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(edge).rounded_rectangle(
            (1, 1, w - 2, h - 2), 18,
            outline=(205, 190, 255, 95 if idx == 2 else 60), width=2
        )
        canvas.alpha_composite(edge, (x, y))

    # Darken top/bottom edges, leaving poster artwork clear and title-logo overlay readable.
    shade = Image.new("RGBA", COVER_SIZE, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shade)
    sd.rectangle((0, 0, COVER_SIZE[0], 100), fill=(3, 2, 8, 95))
    sd.rectangle((0, 750, COVER_SIZE[0], COVER_SIZE[1]), fill=(3, 2, 8, 115))
    shade = shade.filter(ImageFilter.GaussianBlur(55))
    canvas = Image.alpha_composite(canvas, shade)

    # Restrained category accent glow near the lower edge.
    glow = Image.new("RGBA", COVER_SIZE, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((380, 700, 1160, 950), fill=(*accent, 28))
    glow = glow.filter(ImageFilter.GaussianBlur(100))
    canvas = Image.alpha_composite(canvas, glow)

    return canvas.convert("RGB")


def build_backdrop(backdrops: list[Image.Image], category: str) -> Image.Image:
    if len(backdrops) < 3:
        raise RuntimeError(f"Only {len(backdrops)} usable hero backdrops for {category}; 3 are required.")

    # Keep source quality high, but rotate among the best available scenes so the
    # same catalog can still produce a fresh hero on the next scheduled run.
    ranked = sorted(backdrops, key=lambda image: image.width * image.height, reverse=True)
    hero_pool = ranked[:min(8, len(ranked))]
    hero_source = random.choice(hero_pool)
    support_pool = [image for image in ranked if image is not hero_source]
    supporting = random.sample(support_pool, k=2)
    accent = ACCENTS[category]

    hero = ImageOps.fit(hero_source, BACKDROP_SIZE, method=Image.Resampling.LANCZOS, centering=(0.5, 0.45))
    hero = ImageEnhance.Color(hero).enhance(0.90)
    hero = ImageEnhance.Contrast(hero).enhance(1.06)
    # Careful output sharpening compensates for resize softness without halos.
    hero = hero.filter(ImageFilter.UnsharpMask(radius=2.2, percent=115, threshold=3))
    canvas = hero.convert("RGBA")

    # Supporting artwork appears only as softly blended edge panels, not a tiled grid.
    for side, source in (("left", supporting[0]), ("right", supporting[1])):
        panel_w = 760
        panel = ImageOps.fit(source, (panel_w, BACKDROP_SIZE[1]), method=Image.Resampling.LANCZOS)
        panel = ImageEnhance.Color(panel).enhance(0.82)
        panel = Image.blend(panel, Image.new("RGB", panel.size, accent), 0.07).convert("RGBA")
        panel.putalpha(62)
        x = 0 if side == "left" else BACKDROP_SIZE[0] - panel_w
        canvas.alpha_composite(panel, (x, 0))

    # Violet Platinum color grade.
    tint = Image.new("RGBA", BACKDROP_SIZE, (*accent, 18))
    canvas = Image.alpha_composite(canvas, tint)

    # Soft center gradient preserves visual space for the separate title logo.
    gradient = Image.new("RGBA", BACKDROP_SIZE, (0, 0, 0, 0))
    gd = ImageDraw.Draw(gradient)
    gd.rectangle((420, 500, 3420, 1700), fill=(4, 3, 10, 36))
    gradient = gradient.filter(ImageFilter.GaussianBlur(210))
    canvas = Image.alpha_composite(canvas, gradient)

    # Gentle cinematic vignette.
    vignette = Image.new("L", BACKDROP_SIZE, 0)
    vd = ImageDraw.Draw(vignette)
    vd.ellipse((-180, -120, BACKDROP_SIZE[0] + 180, BACKDROP_SIZE[1] + 120), fill=190)
    vignette = vignette.filter(ImageFilter.GaussianBlur(175))
    alpha = Image.eval(vignette, lambda p: max(0, min(78, 78 - int(p * 0.32))))
    dark = Image.new("RGBA", BACKDROP_SIZE, (0, 0, 0, 0))
    dark.putalpha(alpha)
    canvas = Image.alpha_composite(canvas, dark)

    # Final subtle sharpening after compositing; preserve real source detail.
    final = canvas.convert("RGB")
    final = final.filter(ImageFilter.UnsharpMask(radius=1.6, percent=85, threshold=4))
    return final


def save_webp(image: Image.Image, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_name(destination.stem + ".tmp.webp")
    image.save(temp, "WEBP", quality=96, method=6, exact=True)
    temp.replace(destination)


def main() -> int:
    hosts = find_catalog_hosts(manifest_urls())
    if not hosts:
        raise RuntimeError("No catalog IDs were discovered from the configured add-on manifests.")

    updated = []
    failures = []
    for category in CATEGORY_CATALOGS:
        log(f"\n=== {category} ===")
        try:
            posters, backdrops = collect_category_art(category, hosts)
            log(f"  usable posters: {len(posters)}")
            log(f"  usable hero backdrops (minimum 1280x720 source): {len(backdrops)}")
            cover = build_cover(posters, category)
            hero = build_backdrop(backdrops, category)

            cover_path = DISCOVER_DIR / category / "Cover" / "cover.webp"
            backdrop_path = DISCOVER_DIR / category / "Backdrop" / "backdrop.webp"
            save_webp(cover, cover_path)
            save_webp(hero, backdrop_path)

            # Logos are stable typography and are installed separately, not regenerated from posters.
            logo_path = DISCOVER_DIR / category / "Logo" / "logo.webp"
            if not logo_path.exists():
                raise RuntimeError(f"Separate logo is missing: {logo_path.relative_to(REPO_ROOT)}")

            updated.append(category)
            log(f"  Wrote {cover_path.relative_to(REPO_ROOT)}")
            log(f"  Wrote {backdrop_path.relative_to(REPO_ROOT)} ({BACKDROP_SIZE[0]}x{BACKDROP_SIZE[1]} 4K UHD; randomized hero/layout)")
            log(f"  Kept separate logo: {logo_path.relative_to(REPO_ROOT)}")
        except Exception as exc:
            failures.append((category, str(exc)))
            log(f"  ERROR: {exc}")

    log("\n=== Summary ===")
    log(f"Updated covers and hero backdrops: {', '.join(updated) if updated else 'none'}")
    if failures:
        for category, error in failures:
            log(f"Not updated — {category}: {error}")
        return 1
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        log(f"FATAL: {exc}")
        raise SystemExit(1)
