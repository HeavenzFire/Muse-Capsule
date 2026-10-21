"""Browse worker: READ-ONLY web automation via Playwright.

- No credential autofill, no login bypass, no form submission.
- Destructive page actions are not implemented at all.
- Uses a persistent profile dir so Zachary signs in himself, once.
"""
import os

CAPABILITIES = ["browse.open"]

PROFILE_DIR = os.path.join(os.path.dirname(__file__), "..", "browser-profile")


def run(task, signal):
    args = task.get("args", {})
    url = args.get("url", "")
    if not (url.startswith("http://") or url.startswith("https://")):
        return {"ok": False, "error": "only http(s) URLs"}
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"ok": False, "error": "playwright not installed"}
    os.makedirs(os.path.abspath(PROFILE_DIR), exist_ok=True)
    try:
        with sync_playwright() as pw:
            ctx = pw.chromium.launch_persistent_context(
                os.path.abspath(PROFILE_DIR), headless=True)
            page = ctx.new_page()
            page.goto(url, timeout=30000, wait_until="domcontentloaded")
            title = page.title()
            text = page.inner_text("body")[:8000]
            final_url = page.url
            ctx.close()
        return {"ok": True, "url": final_url, "title": title, "text": text}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}
