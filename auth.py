import json
from pathlib import Path
from typing import Optional

cookies_path = Path.home() / ".cx-assistant-cookies.json"

HOSTS = {
    "production": "https://cxassistant.cisco.com",
    "stage": "https://cxassistant-stage.cisco.com"
}

def save_cookies(cookies: list, path: Path = cookies_path) -> None:
    """Save browser cookies to local JSON file."""
    path.write_text(json.dumps(cookies, indent=2))

def load_cookies(path: Path = cookies_path) -> Optional[list]:
    """Load cookies from local JSON file. Returns None if missing or corrupt."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None

def cookies_as_dict(cookies: list) -> dict:
    """Convert Playwright cookie list to {name: value} dict for httpx."""
    return {c["name"]: c["value"] for c in cookies}

async def _launch_browser(p):
    """Try Chromium -> Edge -> WebKit in order. Returns (browser, label)."""
    attempts = [
        (p.chromium, {}, "Chromium"),
        (p.chromium, {"channel": "msedge"}, "Edge"),
        (p.webkit, {}, "WebKit/Safari"),
    ]
    last_error = None
    for engine, kwargs, label in attempts:
        try:
            browser = await engine.launch(headless=False, **kwargs)
            return browser, label
        except Exception as e:
            last_error = e
            continue
    raise RuntimeError(
        f"No supported browser found (tried Chromium, Edge, WebKit). "
        f"Last error: {last_error}. "
        f"Run 'playwright install chromium' or install Edge/Chrome."
    )

async def browser_login(environment: str = "production") -> str:
    """Open headed browser for Cisco Duo login. Saves cookies on success.

    NOTE: Cisco SSO cookies are HttpOnly — cannot be detected via document.cookie.
    Instead we wait for the post-login URL redirect back to the app.

    For stage: tries Chromium -> Edge -> WebKit if earlier browsers fail.
    For production: uses Chromium only.
    """
    from playwright.async_api import async_playwright
    host = HOSTS.get(environment, HOSTS["production"])
    async with async_playwright() as p:
        if environment == "stage":
            browser, label = await _launch_browser(p)
            print(f"[cx-assistant] Opened {label} at {host}. Complete Cisco Duo login...")
        else:
            browser = await p.chromium.launch(headless=False)
            print(f"[cx-assistant] Browser opened at {host}. Complete Cisco Duo login...")
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto(host)
        # Wait for post-login redirect back to the app (not SSO/Duo domain)
        await page.wait_for_url(
            f"{host}/**",
            timeout=180_000
        )
        # Extra wait for cookies to fully settle — best effort only.
        # Some pages never reach networkidle due to background polling.
        try:
            await page.wait_for_load_state("networkidle", timeout=15_000)
        except Exception:
            pass
        cookies = await context.cookies()
        await browser.close()
    save_cookies(cookies)
    return f"Login successful for {environment}. Cookies saved."
