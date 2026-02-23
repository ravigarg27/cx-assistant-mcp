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
    """Load cookies from local JSON file. Returns None if file missing."""
    if not path.exists():
        return None
    return json.loads(path.read_text())

def cookies_as_dict(cookies: list) -> dict:
    """Convert Playwright cookie list to {name: value} dict for httpx."""
    return {c["name"]: c["value"] for c in cookies}

async def browser_login(environment: str = "production") -> str:
    """Open headed browser for Cisco Duo login. Saves cookies on success.

    NOTE: Cisco SSO cookies are HttpOnly — cannot be detected via document.cookie.
    Instead we wait for the post-login URL redirect back to the app.
    """
    from playwright.async_api import async_playwright
    host = HOSTS.get(environment, HOSTS["production"])
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto(host)
        print(f"[cx-assistant] Browser opened at {host}. Complete Cisco Duo login...")
        # Wait for post-login redirect back to the app (not SSO/Duo domain)
        await page.wait_for_url(
            f"{host}/**",
            timeout=180_000
        )
        # Extra wait for cookies to fully settle after redirect
        await page.wait_for_load_state("networkidle", timeout=15_000)
        cookies = await context.cookies()
        await browser.close()
    save_cookies(cookies)
    return f"Login successful for {environment}. Cookies saved."
