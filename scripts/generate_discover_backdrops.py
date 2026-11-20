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
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps

REPO_ROOT = Path(__file__).resolve().parents[1]
DISCOVER_DIR = REPO_ROOT / "Discover"

COVER_SIZE = (1536, 864)
MAX_BACKDROP_SIZE = (3840, 2160)  # Never enlarge a backdrop beyond its source resolution
MIN_BACKDROP_SIZE = (1920, 1080)  # Reject smaller hero sources to avoid visibly soft TV artwork
MAX_ITEMS_PER_CATALOG = 30
MAX_POSTERS = 15
MAX_BACKDROPS = 12
MIN_BACKDROP_ASPECT = 1.50  # Reject portrait/square promotional artwork as hero images
TIMEOUT = 25
USER_AGENT = "Nuvio-Discover-Artwork-Generator/2.3-Audited"
AUDIT_PATH = DISCOVER_DIR / "artwork-audit.json"

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


def download_backdrop(url: str) -> tuple[Image.Image | None, tuple[int, int] | None, str]:
    """Download a backdrop and report its original dimensions and validation result."""
    try:
        response = SESSION.get(url, timeout=TIMEOUT)
        response.raise_for_status()
        with Image.open(io.BytesIO(response.content)) as original:
            width, height = original.size
            if width < MIN_BACKDROP_SIZE[0] or height < MIN_BACKDROP_SIZE[1]:
                return None, (width, height), f"too small; requires at least {MIN_BACKDROP_SIZE[0]}x{MIN_BACKDROP_SIZE[1]}"
            aspect = width / height
            if aspect < MIN_BACKDROP_ASPECT:
                return None, (width, height), f"not a landscape hero image; aspect ratio {aspect:.2f} is below {MIN_BACKDROP_ASPECT:.2f}"
            image = original.convert("RGB")
        return image, (width, height), "accepted"
    except Exception as exc:
        return None, None, f"download/decode failed: {exc}"


def collect_category_art(category: str, hosts: dict[str, str]) -> tuple[list[Image.Image], list[dict], list[dict]]:
    posters: list[Image.Image] = []
    backdrops: list[dict] = []
    audit: list[dict] = []
    seen_posters: set[str] = set()
    seen_backdrops: set[str] = set()

    for media_type, catalog_id in CATEGORY_CATALOGS[category]:
        base = hosts.get(catalog_id)
        if not base:
            log(f"  catalog not listed by installed manifests: {catalog_id}")
            audit.append({"category": category, "catalog_id": catalog_id, "expected_type": media_type,
                          "status": "catalog_missing", "reason": "catalog ID not found in configured manifests"})
            continue
        try:
            items = fetch_catalog(base, media_type, catalog_id)
            log(f"  {catalog_id}: {len(items)} current catalog items")
        except Exception as exc:
            log(f"  catalog failed {catalog_id}: {exc}")
            audit.append({"category": category, "catalog_id": catalog_id, "expected_type": media_type,
                          "status": "catalog_failed", "reason": str(exc)})
            continue

        for item in items:
            meta = {}
            item_id = str(item.get("id") or "")
            title = str(item.get("name") or item.get("title") or "Unknown title").strip()
            actual_type = str(item.get("type") or media_type).lower()
            entry = {"category": category, "catalog_id": catalog_id, "title": title,
                     "item_id": item_id, "expected_type": media_type, "catalog_type": actual_type,
                     "poster_status": "not_checked", "backdrop_status": "not_checked"}

            # A catalog route is not enough if the item itself explicitly identifies another media type.
            if actual_type not in ("movie", "series") or actual_type != media_type:
                entry.update({"status": "rejected", "reason": f"media type mismatch or unsupported type: {actual_type}"})
                audit.append(entry)
                log(f"  rejected {title}: {entry['reason']}")
                continue

            poster_url = valid_http_url(item.get("poster"))
            backdrop_url = valid_http_url(item.get("background") or item.get("landscape"))

            # Resolve missing poster/background URLs and authoritative type/title from metadata.
            if (not poster_url or not backdrop_url or not item.get("type")) and item_id:
                try:
                    meta = fetch_meta(base, media_type, item_id)
                except Exception as exc:
                    entry["metadata_warning"] = str(exc)
                    log(f"  metadata skipped for {title}: {exc}")

            meta_type = str(meta.get("type") or actual_type).lower()
            if meta_type not in ("movie", "series") or meta_type != media_type:
                entry.update({"catalog_type": meta_type, "status": "rejected",
                              "reason": f"metadata media type mismatch or unsupported type: {meta_type}"})
                audit.append(entry)
                log(f"  rejected {title}: {entry['reason']}")
                continue
            if meta.get("name") or meta.get("title"):
                title = str(meta.get("name") or meta.get("title")).strip()
                entry["title"] = title

            if not poster_url:
                poster_url = valid_http_url(meta.get("poster"))
            if not backdrop_url:
                backdrop_url = valid_http_url(meta.get("background") or meta.get("landscape"))

            if poster_url and poster_url not in seen_posters and len(posters) < MAX_POSTERS:
                seen_posters.add(poster_url)
                image = download_image(poster_url, min_size=(180, 260))
                if image:
                    posters.append(image)
                    entry["poster_status"] = "accepted"
                else:
                    entry["poster_status"] = "rejected: unavailable or too small"

            if backdrop_url and backdrop_url not in seen_backdrops and len(backdrops) < MAX_BACKDROPS:
                seen_backdrops.add(backdrop_url)
                image, dimensions, reason = download_backdrop(backdrop_url)
                parsed = urlparse(backdrop_url)
                entry["backdrop_source_host"] = parsed.netloc
                entry["backdrop_source_dimensions"] = list(dimensions) if dimensions else None
                entry["backdrop_status"] = reason
                if image:
                    backdrops.append({"image": image, "title": title, "type": media_type,
                                      "item_id": item_id, "catalog_id": catalog_id,
                                      "source_dimensions": dimensions, "source_host": parsed.netloc})
                    log(f"    accepted backdrop: {title} ({media_type}) {dimensions[0]}x{dimensions[1]}")
                else:
                    log(f"    rejected backdrop: {title} ({media_type}) — {reason}")
            elif not backdrop_url:
                entry["backdrop_status"] = "no background/landscape URL supplied"
            else:
                entry["backdrop_status"] = "duplicate URL or backdrop limit reached"

            entry["status"] = "processed"
            audit.append(entry)

            if len(posters) >= MAX_POSTERS and len(backdrops) >= MAX_BACKDROPS:
                break

    return posters, backdrops, audit


def crop_cover(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    return ImageOps.fit(img, size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.38))


def rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius, fill=255)
    return mask


def build_cover(posters: list[Image.Image], category: str) -> Image.Image:
    if len(posters) < 5:
        raise RuntimeError(f"Only {len(posters)} usable posters for {category}; 5 are required.")

    random.seed(category)
    # Rotate through the current catalog ordering so each scheduled run can produce a new mix.
    selected = posters[:]
    random.shuffle(selected)
    canvas = Image.new("RGBA", COVER_SIZE, (7, 6, 12, 255))
    accent = ACCENTS[category]

    # Poster windows: a larger center feature, flanked by four smaller cards.
    specs = [
        (52, 180, 250, 505),
        (278, 105, 285, 655),
        (535, 42, 466, 780),
        (948, 105, 285, 655),
        (1234, 180, 250, 505),
    ]
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


def build_backdrop(backdrops: list[dict], category: str) -> tuple[Image.Image, dict]:
    if len(backdrops) < 3:
        raise RuntimeError(
            f"Only {len(backdrops)} usable hero backdrops at or above "
            f"{MIN_BACKDROP_SIZE[0]}x{MIN_BACKDROP_SIZE[1]} for {category}; 3 are required."
        )

    # Prefer the highest-resolution original. Do not upscale a 1080p/1440p
    # source and label it as native 4K; the output must never exceed source size.
    chosen = sorted(backdrops, key=lambda item: item["image"].width * item["image"].height, reverse=True)
    selected = chosen[0]
    source = selected["image"]
    source_size = source.size
    max_w, max_h = MAX_BACKDROP_SIZE
    scale = min(1.0, max_w / source.width, max_h / source.height)
    output_size = (
        max(2, int(source.width * scale) // 2 * 2),
        max(2, int(source.height * scale) // 2 * 2),
    )

    # Fit/crop only when necessary. No enlargement and no artificial sharpening.
    hero = ImageOps.fit(
        source,
        output_size,
        method=Image.Resampling.LANCZOS,
        centering=(0.5, 0.45),
    )
    hero = ImageEnhance.Color(hero).enhance(0.96)
    hero = ImageEnhance.Contrast(hero).enhance(1.02)
    canvas = hero.convert("RGBA")

    # Restrained Violet Platinum grade; avoid heavy overlays that muddy dark scenes.
    accent = ACCENTS[category]
    tint = Image.new("RGBA", output_size, (*accent, 7))
    canvas = Image.alpha_composite(canvas, tint)

    # Very subtle vignette, scaled to the actual output dimensions.
    w, h = output_size
    vignette = Image.new("L", output_size, 0)
    vd = ImageDraw.Draw(vignette)
    vd.ellipse((-int(w * 0.05), -int(h * 0.05), int(w * 1.05), int(h * 1.05)), fill=210)
    vignette = vignette.filter(ImageFilter.GaussianBlur(max(24, int(w * 0.035))))
    alpha = Image.eval(vignette, lambda value: max(0, min(34, 34 - int(value * 0.16))))
    dark = Image.new("RGBA", output_size, (0, 0, 0, 0))
    dark.putalpha(alpha)
    canvas = Image.alpha_composite(canvas, dark)

    return canvas.convert("RGB"), selected


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
    audit_report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator_version": "2.3-Audited",
        "rules": {
            "allowed_media_types": ["movie", "series"],
            "minimum_backdrop_dimensions": list(MIN_BACKDROP_SIZE),
            "minimum_backdrop_aspect_ratio": MIN_BACKDROP_ASPECT,
            "maximum_output_dimensions": list(MAX_BACKDROP_SIZE),
            "upscaling": False,
        },
        "categories": {},
    }

    for category in CATEGORY_CATALOGS:
        log(f"\n=== {category} ===")
        category_audit = []
        try:
            posters, backdrops, category_audit = collect_category_art(category, hosts)
            log(f"  usable posters: {len(posters)}")
            log(f"  usable hero backdrops: {len(backdrops)}")
            cover = build_cover(posters, category)
            hero, selected = build_backdrop(backdrops, category)

            cover_path = DISCOVER_DIR / category / "Cover" / "cover.webp"
            backdrop_path = DISCOVER_DIR / category / "Backdrop" / "backdrop.webp"
            save_webp(cover, cover_path)
            save_webp(hero, backdrop_path)

            logo_path = DISCOVER_DIR / category / "Logo" / "logo.webp"
            if not logo_path.exists():
                raise RuntimeError(f"Separate logo is missing: {logo_path.relative_to(REPO_ROOT)}")

            selected_record = {
                "title": selected["title"],
                "type": selected["type"],
                "item_id": selected["item_id"],
                "catalog_id": selected["catalog_id"],
                "source_host": selected["source_host"],
                "source_dimensions": list(selected["source_dimensions"]),
                "output_dimensions": list(hero.size),
                "native_4k_source": selected["source_dimensions"][0] >= 3840 and selected["source_dimensions"][1] >= 2160,
            }
            for record in category_audit:
                if record.get("title") == selected["title"] and record.get("item_id") == selected["item_id"]:
                    record["selected_for_hero"] = True
                elif "backdrop_status" in record and record.get("backdrop_status") == "accepted":
                    record["selected_for_hero"] = False
            audit_report["categories"][category] = {
                "selected_hero": selected_record,
                "usable_backdrop_count": len(backdrops),
                "usable_poster_count": len(posters),
                "items": category_audit,
            }

            updated.append(category)
            log(f"  SELECTED HERO: {selected['title']} ({selected['type']})")
            log(f"  Source: {selected['source_dimensions'][0]}x{selected['source_dimensions'][1]} from {selected['source_host']}")
            quality_label = "native 4K source" if selected_record["native_4k_source"] else "not native 4K"
            log(f"  Output: {hero.size[0]}x{hero.size[1]} ({quality_label}; no upscaling)")
            log(f"  Wrote {cover_path.relative_to(REPO_ROOT)} and {backdrop_path.relative_to(REPO_ROOT)}")
            log(f"  Kept separate logo: {logo_path.relative_to(REPO_ROOT)}")
        except Exception as exc:
            failures.append((category, str(exc)))
            audit_report["categories"][category] = {"error": str(exc), "items": category_audit}
            log(f"  ERROR: {exc}")

    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    AUDIT_PATH.write_text(json.dumps(audit_report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    log(f"\nAudit report written: {AUDIT_PATH.relative_to(REPO_ROOT)}")
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
