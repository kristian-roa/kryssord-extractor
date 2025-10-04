import argparse, io, re
from pathlib import Path
from collections import Counter
from PIL import Image
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# --- helpers ---------------------------------------------------------------

def click_cookie_accept(page):
    try: page.locator("#cookie-consent-accept").click(timeout=1500)
    except Exception: pass

JS_ZBOOST = """
(sel) => {
  const el = document.querySelector(sel); if (!el) return false;
  el.style.position = 'relative'; el.style.zIndex = '2147483647';
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
    w,h = img.size
    pts = [(0,0),(w-1,0),(0,h-1),(w-1,h-1)]
    colors = [img.getpixel(p) for p in pts]
    colors = [c[:3] if isinstance(c, tuple) and len(c)==4 else c for c in colors]
    return Counter(colors).most_common(1)[0][0]

def trim_uniform_bg(img: Image.Image, tol=12, pad=10) -> Image.Image:
    if img.mode != "RGB": img = img.convert("RGB")
    bg = most_common_corner_color(img)
    import numpy as np
    arr = np.asarray(img, dtype=np.int16)
    bg_arr = np.array(bg, dtype=np.int16).reshape(1,1,3)
    diff = np.max(np.abs(arr - bg_arr), axis=2)
    mask = diff > tol
    if not mask.any(): return img
    ys, xs = np.where(mask)
    l, r, t, b = xs.min(), xs.max(), ys.min(), ys.max()
    l = max(0, l-pad); t = max(0, t-pad)
    r = min(img.width-1, r+pad); b = min(img.height-1, b+pad)
    return img.crop((l, t, r+1, b+1))

def save_pdf(rgb_img: Image.Image, out_base: str):
    import img2pdf
    buf = io.BytesIO(); rgb_img.save(buf, format="PNG")  # ensure opaque
    pdf_path = Path(out_base).with_suffix(".pdf")
    with open(pdf_path, "wb") as f: f.write(img2pdf.convert(buf.getvalue()))
    return pdf_path

# --- reveal via the “Vis” eye menu ----------------------------------------

def click_eye_and_reveal(frame) -> bool:
    """
    Open the eye (“Vis”) menu and click “Vis hele løsningen”.
    """

    # Directly target the button by its tooltip attribute
    try:
        eye = frame.locator('button[data-tooltip-content="Vis"]').first
        eye.click(timeout=1500)
    except Exception:
        print("Could not click eye button")
        return False

    # Then click the “Vis hele løsningen” item
    try:
        frame.locator('text=/Vis hele løsningen/i').click(timeout=2000)
        return True
    except Exception:
        print("Could not click 'Vis hele løsningen'")
        return False


# --- main ------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Save crossword + solution as trimmed PDFs (using 'Vis' eye menu).")
    ap.add_argument("--url", default="https://kryssord.no/oppgaver/kryssord-2")
    ap.add_argument("--out", default="crossword")
    ap.add_argument("--selector", default='[class*="-crosswordType-"]',
                    help="Grid container selector inside the iframe.")
    ap.add_argument("--trim-tol", type=int, default=12)
    ap.add_argument("--pad", type=int, default=10)
    args = ap.parse_args()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width":1600,"height":1200}, device_scale_factor=2)
        page = ctx.new_page()

        try:
            page.goto(args.url, timeout=30000)
        except PWTimeout:
            raise SystemExit("Page load timed out.")

        click_cookie_accept(page)

        # iframe
        frame = page.frame(name="crossword")
        if not frame:
            for f in page.frames:
                if "egmont-crosswords-frontend" in (f.url or ""): frame = f; break
        if not frame: raise SystemExit("Crossword iframe not found.")

        # grid present
        try:
            frame.wait_for_selector(args.selector, timeout=12000)
        except PWTimeout:
            raise SystemExit(f"Grid element not found with selector: {args.selector}")

        # Hide keyboard; bring grid front
        try: frame.evaluate(JS_HIDE_KEYBOARD)
        except Exception: pass
        frame.evaluate(JS_ZBOOST, args.selector)
        grid = frame.locator(args.selector).first
        grid.scroll_into_view_if_needed(timeout=1500)

        # --- 1) base puzzle ---
        png = grid.screenshot()
        base_img = Image.open(io.BytesIO(png)).convert("RGB")
        base_trim = trim_uniform_bg(base_img, tol=args.trim_tol, pad=args.pad)
        base_pdf = save_pdf(base_trim, args.out)

        # --- 2) open “Vis” eye and click “Vis hele løsningen” ---
        revealed = click_eye_and_reveal(frame)
        page.wait_for_timeout(800)  # let DOM update

        sol_pdf = None
        if revealed:
            # re-apply safety tweaks in case of re-render
            try: frame.evaluate(JS_HIDE_KEYBOARD)
            except Exception: pass
            frame.evaluate(JS_ZBOOST, args.selector)
            png2 = grid.screenshot()
            sol_img = Image.open(io.BytesIO(png2)).convert("RGB")
            sol_trim = trim_uniform_bg(sol_img, tol=args.trim_tol, pad=args.pad)
            sol_pdf = save_pdf(sol_trim, f"{args.out}-solution")
        else:
            print("Warning: couldn’t click the solution item via the eye menu. "
                  "If the label differs, adjust the regexes in click_eye_and_reveal().")

        browser.close()

    msg = f"Saved: {base_pdf}"
    if sol_pdf: msg += f", {sol_pdf}"
    print(msg)

if __name__ == "__main__":
    main()
