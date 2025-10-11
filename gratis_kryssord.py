#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import io
from collections import Counter
from datetime import date
from pathlib import Path
from PIL import Image
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout


def click_cookie_consent(page):
    """Try to close the consent popup by clicking Samtykke or similar."""
    selectors = [
        'button:has-text("Samtykke")',
        'button:has-text("Godta")',
        'button:has-text("Accept")',
        'button:has-text("Jeg samtykker")',
    ]
    for sel in selectors:
        try:
            page.locator(sel).first.click(timeout=1500)
            print("[✓] Consent popup closed.")
            return True
        except Exception:
            pass
    print("[!] Consent popup not found or already closed.")
    return False


def most_common_corner_color(img: Image.Image):
    w, h = img.size
    pts = [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]
    colors = [img.getpixel(p) for p in pts]
    colors = [c[:3] if isinstance(c, tuple) and len(c) == 4 else c for c in colors]
    return Counter(colors).most_common(1)[0][0]


def trim_uniform_bg(img: Image.Image, tol=12, pad=8) -> Image.Image:
    import numpy as np
    if img.mode != "RGB":
        img = img.convert("RGB")
    bg = most_common_corner_color(img)
    arr = np.asarray(img, dtype=np.int16)
    bg_arr = np.array(bg, dtype=np.int16).reshape(1, 1, 3)
    diff = np.max(np.abs(arr - bg_arr), axis=2)
    mask = diff > tol
    if not mask.any():
        return img
    ys, xs = np.where(mask)
    l, r, t, b = xs.min(), xs.max(), ys.min(), ys.max()
    l = max(0, l - pad); t = max(0, t - pad)
    r = min(img.width - 1, r + pad); b = min(img.height - 1, b + pad)
    return img.crop((l, t, r + 1, b + 1))


def save_pdf(rgb_img: Image.Image, out_base: str):
    import img2pdf
    buf = io.BytesIO()
    rgb_img.save(buf, format="PNG")
    pdf_path = Path(out_base).with_suffix(".pdf")
    with open(pdf_path, "wb") as f:
        f.write(img2pdf.convert(buf.getvalue()))
    return pdf_path


def download_gratiskryssord():
    ap = argparse.ArgumentParser(description="Fetch dagens kryssord (no solution) from gratiskryssord.no")
    ap.add_argument("--url", default="https://www.gratiskryssord.no/kryssord/dagens/")
    ap.add_argument("--selector", default="#myCanvas")
    ap.add_argument("--trim-tol", type=int, default=12)
    ap.add_argument("--pad", type=int, default=8)
    ap.add_argument("--jpg", action="store_true")
    ap.add_argument("--crop-right-px", type=int, default=0)
    args = ap.parse_args()

    today = date.today().strftime("%Y-%m-%d")
    base_name = f"{today}-gratiskryssord"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1600, "height": 1200}, device_scale_factor=2)
        page = ctx.new_page()

        print(f"Opening {args.url} …")
        try:
            page.goto(args.url, timeout=40000)
        except PWTimeout:
            raise SystemExit("Page load timed out.")

        # Try to handle consent popup
        click_cookie_consent(page)

        # Wait for crossword canvas
        page.wait_for_selector(args.selector, timeout=20000)
        target = page.locator(args.selector).first
        page.wait_for_timeout(800)
        target.scroll_into_view_if_needed(timeout=1000)

        png = target.screenshot()
        img = Image.open(io.BytesIO(png)).convert("RGB")

        # Optionally shave pixels off the right edge
        if args.crop_right_px > 0:
            w, h = img.size
            img = img.crop((0, 0, w - args.crop_right_px, h))

        trimmed = trim_uniform_bg(img, tol=args.trim_tol, pad=args.pad)
        pdf_path = save_pdf(trimmed, base_name)

        jpg_path = None
        if args.jpg:
            jpg_path = Path(base_name).with_suffix(".jpg")
            trimmed.save(jpg_path, quality=95, optimize=True)

        browser.close()

    print(f"✅ Saved {pdf_path}" + (f" and {jpg_path}" if jpg_path else ""))
    return pdf_path
