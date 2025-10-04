import argparse
import io
from pathlib import Path
from PIL import Image
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

  // Bring target above everything
  el.style.position = 'relative';
  el.style.zIndex = '2147483647';

  // Ensure parents don't clip it
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
  // Try to detect a keyboard by many 1-letter buttons (incl. Æ Ø Å)
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
  if (kb) {
    kb.style.display = 'none';
    return true;
  }

  // CSS catch-all
  const style = document.createElement('style');
  style.textContent = `
    .keyboard, [class*="keyboard" i], [aria-label*="keyboard" i],
    [aria-label*="tastatur" i], [data-testid*="keyboard" i],
    .virtual-keyboard, [class*="virtual-keyboard" i],
    .bottom-bar, [class*="bottom-bar" i] { display:none!important; visibility:hidden!important; opacity:0!important; height:0!important; }
  `;
  document.head.appendChild(style);
  return false;
}
"""

def save_outputs(png_bytes: bytes, out_base: str, fmt: str):
    rgb = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    outputs = []
    if fmt in ("jpg", "both"):
        jp = Path(out_base).with_suffix(".jpg")
        rgb.save(jp, "JPEG", quality=92)
        outputs.append(jp)
    if fmt in ("pdf", "both"):
        import img2pdf
        # round-trip through PNG bytes to avoid transparency issues (should be none, but safe)
        buf = io.BytesIO()
        rgb.save(buf, format="PNG")
        pp = Path(out_base).with_suffix(".pdf")
        with open(pp, "wb") as f:
            f.write(img2pdf.convert(buf.getvalue()))
        outputs.append(pp)
    return outputs


def main():
    ap = argparse.ArgumentParser(description="Screenshot ONLY the crossword grid (DOM element) without keyboard.")
    ap.add_argument("--url", default="https://kryssord.no/oppgaver/kryssord-2")
    ap.add_argument("--out", default="crossword")
    ap.add_argument("--format", choices=["jpg", "pdf", "both"], default="both")
    # If the site changes, you can pass your own selector for the grid element:
    ap.add_argument("--selector", default='[class*="-crosswordType-"]')
    args = ap.parse_args()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1600, "height": 1200}, device_scale_factor=2)
        page = ctx.new_page()

        try:
            page.goto(args.url, timeout=30000)
        except PWTimeout:
            raise SystemExit("Page load timed out.")

        click_cookie_accept(page)

        # Get the crossword iframe
        frame = page.frame(name="crossword")
        if not frame:
            for f in page.frames:
                if "egmont-crosswords-frontend" in (f.url or ""):
                    frame = f
                    break
        if not frame:
            raise SystemExit("Crossword iframe not found.")

        # Wait for the grid element to exist
        grid = frame.query_selector(args.selector)
        if not grid:
            try:
                frame.wait_for_selector(args.selector, timeout=12000)
                grid = frame.query_selector(args.selector)
            except PWTimeout:
                raise SystemExit(f"Grid element not found using selector: {args.selector}")
        if not grid:
            raise SystemExit(f"Grid element not found using selector: {args.selector}")

        # Hide keyboard and raise the grid
        try:
            frame.evaluate(JS_HIDE_KEYBOARD)
        except Exception:
            pass
        frame.evaluate(JS_ZBOOST, args.selector)

        # Ensure in view and screenshot the element only
        loc = frame.locator(args.selector).first
        loc.scroll_into_view_if_needed(timeout=2000)
        png = loc.screenshot()  # element-only screenshot inside the iframe

        browser.close()

    outs = save_outputs(png, args.out, args.format)
    print("Saved:", ", ".join(str(p) for p in outs))


if __name__ == "__main__":
    main()
