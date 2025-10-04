import argparse
import io
from pathlib import Path
from collections import Counter

from PIL import Image, ImageStat
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout


def click_cookie_accept(page):
    try:
        page.locator("#cookie-consent-accept").click(timeout=1500)
    except Exception:
        pass


JS_ZBOOST = """
(sel) => {
  const el = document.querySelector(sel);
  if (!el) return false;
  el.style.position = 'relative';
  el.style.zIndex = '2147483647';
  let p = el.parentElement;
  while (p && p !== document.body) {
    const cs = getComputedStyle(p);
    if (cs.overflow !== 'visible') p.style.overflow = 'visible';
    if (cs.position === 'static') p.style.position = 'relative';
    p.style.zIndex = (parseInt(p.style.zIndex || '0', 10) + 1).toString();
    p = p.parentElement;
  }
  return true;
}
"""

JS_HIDE_KEYBOARD = """
() => {
  const letters = new Set("QWERTYUIOPÅASDFGHJKLØÆZXCVBNM");
  const buttons = Array.from(document.querySelectorAll('button'));
  const buckets = new Map();
  for (const b of buttons) {
    const t = (b.textContent || "").trim().toUpperCase();
    if (t.length === 1 && letters.has(t)) {
      const cont = b.closest('[class], [role], div, section, footer, header') || b.parentElement;
      if (cont) buckets.set(cont, (buckets.get(cont) || 0) + 1);
    }
  }
  let kb = null, max = 0;
  for (const [el, cnt] of buckets.entries()) if (cnt >= 10 && cnt > max) { kb = el; max = cnt; }
  if (kb) kb.style.display = 'none';

  const style = document.createElement('style');
  style.textContent = `
    .keyboard, [class*="keyboard" i], [aria-label*="keyboard" i],
    [aria-label*="tastatur" i], [data-testid*="keyboard" i],
    .virtual-keyboard, [class*="virtual-keyboard" i],
    .bottom-bar, [class*="bottom-bar" i] { display:none!important; visibility:hidden!important; opacity:0!important; height:0!important; }
  `;
  document.head.appendChild(style);
}
"""


def most_common_corner_color(img: Image.Image):
    """Return the most common color among the 4 corners (handles off-white backgrounds)."""
    w, h = img.size
    pts = [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]
    colors = [img.getpixel(p) for p in pts]
    # If image has alpha (shouldn't), drop it
    colors = [c[:3] if isinstance(c, tuple) and len(c) == 4 else c for c in colors]
    return Counter(colors).most_common(1)[0][0]


def trim_uniform_bg(img: Image.Image, bg=None, tol=10, pad=8) -> Image.Image:
    """
    Trim uniform background (near `bg`) with tolerance.
    - bg: (R,G,B) background color; if None, inferred from corners.
    - tol: 0..255, higher → more aggressive trimming.
    - pad: pixels of margin kept after trimming.
    """
    if img.mode != "RGB":
        img = img.convert("RGB")

    if bg is None:
        bg = most_common_corner_color(img)

    # Build a mask of "content" pixels: any pixel sufficiently different from bg
    # Difference metric: max per-channel absolute difference
    import numpy as np
    arr = np.asarray(img, dtype=np.int16)
    bg_arr = np.array(bg, dtype=np.int16).reshape(1, 1, 3)
    diff = np.max(np.abs(arr - bg_arr), axis=2)
    mask = diff > tol

    # If the mask is empty (extreme case), return original
    if not mask.any():
        return img

    ys, xs = np.where(mask)
    left, right = xs.min(), xs.max()
    top, bottom = ys.min(), ys.max()

    # Apply padding and clamp
    left = max(0, left - pad)
    top = max(0, top - pad)
    right = min(img.width - 1, right + pad)
    bottom = min(img.height - 1, bottom + pad)

    return img.crop((left, top, right + 1, bottom + 1))


def save_outputs(rgb_img: Image.Image, out_base: str, fmt: str):
    outputs = []
    if fmt in ("jpg", "both"):
        jp = Path(out_base).with_suffix(".jpg")
        rgb_img.save(jp, "JPEG", quality=92)
        outputs.append(jp)
    if fmt in ("pdf", "both"):
        import img2pdf, io
        buf = io.BytesIO()
        rgb_img.save(buf, format="PNG")
        pp = Path(out_base).with_suffix(".pdf")
        with open(pp, "wb") as f:
            f.write(img2pdf.convert(buf.getvalue()))
        outputs.append(pp)
    return outputs


def main():
    parser = argparse.ArgumentParser(description="Screenshot ONLY the crossword grid and trim surrounding whitespace.")
    parser.add_argument("--url", default="https://kryssord.no/oppgaver/kryssord-2")
    parser.add_argument("--out", default="crossword")
    parser.add_argument("--format", choices=["jpg", "pdf", "both"], default="pdf")
    parser.add_argument("--selector", default='[class*="-crosswordType-"]',
                        help="Selector for the grid container inside the iframe.")
    parser.add_argument("--trim-tol", type=int, default=10,
                        help="Background trim tolerance (0–255). Increase if thin margins remain.")
    parser.add_argument("--pad", type=int, default=8,
                        help="Padding (px) to keep around the cropped grid after trimming.")
    args = parser.parse_args()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1600, "height": 1200}, device_scale_factor=2)
        page = ctx.new_page()

        try:
            page.goto(args.url, timeout=30000)
        except PWTimeout:
            raise SystemExit("Page load timed out.")

        click_cookie_accept(page)

        # Access iframe
        frame = page.frame(name="crossword")
        if not frame:
            for f in page.frames:
                if "egmont-crosswords-frontend" in (f.url or ""):
                    frame = f
                    break
        if not frame:
            raise SystemExit("Crossword iframe not found.")

        # Ensure the grid exists
        try:
            frame.wait_for_selector(args.selector, timeout=12000)
        except PWTimeout:
            raise SystemExit(f"Grid element not found with selector: {args.selector}")

        # Hide keyboard & raise the grid above everything
        try:
            frame.evaluate(JS_HIDE_KEYBOARD)
        except Exception:
            pass
        frame.evaluate(JS_ZBOOST, args.selector)

        # Element-only screenshot
        loc = frame.locator(args.selector).first
        loc.scroll_into_view_if_needed(timeout=2000)
        png_bytes = loc.screenshot()

        browser.close()

    # Trim whitespace around the grid
    img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    trimmed = trim_uniform_bg(img, bg=None, tol=args.trim_tol, pad=args.pad)

    outs = save_outputs(trimmed, args.out, args.format)
    print("Saved:", ", ".join(str(p) for p in outs))


if __name__ == "__main__":
    main()
