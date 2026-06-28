from __future__ import annotations

import base64
import re
import time
from pathlib import Path
from typing import Any

from .config import config


class BrowserWorkflowError(RuntimeError):
    pass


def _safe_filename(value: str) -> str:
    stem = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:72] or "generated-image"
    return f"{stem}.png"


def _desktop_path(name: str | None, prompt: str) -> Path:
    requested = Path(name).expanduser() if name else Path.home() / "Desktop" / _safe_filename(prompt)
    if requested.is_dir() or str(requested).endswith("/"):
        requested = requested / _safe_filename(prompt)
    if requested.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
        requested = requested.with_suffix(".png")
    requested.parent.mkdir(parents=True, exist_ok=True)
    return requested.resolve()


def _data_url_bytes(data_url: str) -> bytes:
    try:
        _, encoded = data_url.split(",", 1)
        return base64.b64decode(encoded)
    except Exception as exc:
        raise BrowserWorkflowError("browser returned an invalid image payload") from exc


def _extract_image(page: Any, destination: Path) -> dict[str, Any]:
    selectors = [
        "main img[src]",
        "article img[src]",
        "img[src*='blob:']",
        "img[src*='oaidalleapiprodscus']",
    ]
    image = None
    for selector in selectors:
        locator = page.locator(selector)
        if locator.count() > 0:
            image = locator.last
            try:
                image.wait_for(state="visible", timeout=5000)
                break
            except Exception:
                image = None
    if image is None:
        raise BrowserWorkflowError("the generated image was not found in the browser page")

    src = image.get_attribute("src")
    if not src:
        raise BrowserWorkflowError("the generated image has no downloadable source")

    data_url = page.evaluate(
        """async (src) => {
          const response = await fetch(src);
          if (!response.ok) throw new Error(`image download failed: ${response.status}`);
          const blob = await response.blob();
          return await new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onerror = () => reject(reader.error);
            reader.onloadend = () => resolve(reader.result);
            reader.readAsDataURL(blob);
          });
        }""",
        src,
    )
    content = _data_url_bytes(data_url)
    if len(content) < 1024:
        raise BrowserWorkflowError("the downloaded image is unexpectedly small and was not saved")
    destination.write_bytes(content)
    if not destination.is_file() or destination.stat().st_size != len(content):
        raise BrowserWorkflowError("the generated image could not be verified after saving")
    return {"type": "browser_workflow", "workflow": "chatgpt_image", "path": str(destination), "bytes": len(content), "verified": True}


def _chatgpt_image(page: Any, payload: dict[str, Any]) -> dict[str, Any]:
    prompt = str(payload.get("prompt") or "").strip()
    if not prompt:
        raise BrowserWorkflowError("chatgpt image workflow requires a prompt")
    destination = _desktop_path(payload.get("destination"), prompt)

    page.goto("https://chatgpt.com/", wait_until="domcontentloaded", timeout=config.browser_timeout_seconds * 1000)
    composer = page.locator("#prompt-textarea")
    if composer.count() == 0:
        composer = page.locator("div[contenteditable='true']").first
    try:
        composer.wait_for(state="visible", timeout=30000)
    except Exception as exc:
        raise BrowserWorkflowError(
            "ChatGPT is not ready. Sign in once in the persistent Operator Browser window, then retry."
        ) from exc

    composer.click()
    composer.fill(prompt)
    composer.press("Enter")

    deadline = time.monotonic() + config.browser_timeout_seconds
    while time.monotonic() < deadline:
        candidates = page.locator("main img[src], article img[src]")
        count = candidates.count()
        if count:
            try:
                candidate = candidates.last
                candidate.wait_for(state="visible", timeout=1000)
                src = candidate.get_attribute("src") or ""
                if src:
                    return _extract_image(page, destination)
            except Exception:
                pass
        page.wait_for_timeout(1500)
    raise BrowserWorkflowError("ChatGPT did not produce a downloadable image before the browser timeout")


def _generic(page: Any, payload: dict[str, Any]) -> dict[str, Any]:
    steps = payload.get("steps")
    if not isinstance(steps, list) or not steps:
        raise BrowserWorkflowError("browser workflow requires non-empty steps")
    evidence: list[dict[str, str]] = []
    for step in steps:
        if not isinstance(step, dict):
            raise BrowserWorkflowError("browser workflow step must be an object")
        kind = step.get("action")
        if kind == "goto":
            url = str(step.get("url") or "")
            if not url.startswith(("http://", "https://")):
                raise BrowserWorkflowError("browser navigation requires an http(s) URL")
            page.goto(url, wait_until="domcontentloaded", timeout=config.browser_timeout_seconds * 1000)
            evidence.append({"action": "goto", "url": url})
        elif kind == "fill":
            page.locator(str(step["selector"])).fill(str(step.get("text") or ""))
            evidence.append({"action": "fill", "selector": str(step["selector"])})
        elif kind == "click":
            page.locator(str(step["selector"])).click()
            evidence.append({"action": "click", "selector": str(step["selector"])})
        elif kind == "press":
            page.locator(str(step["selector"])).press(str(step.get("key") or "Enter"))
            evidence.append({"action": "press", "selector": str(step["selector"])})
        elif kind == "wait_for":
            page.locator(str(step["selector"])).wait_for(state="visible", timeout=config.browser_timeout_seconds * 1000)
            evidence.append({"action": "wait_for", "selector": str(step["selector"])})
        else:
            raise BrowserWorkflowError(f"unsupported browser workflow step: {kind}")
    return {"type": "browser_workflow", "workflow": "generic", "url": page.url, "steps": evidence, "verified": True}


def run_browser_workflow(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise BrowserWorkflowError("Playwright is not installed. Run the repository sync command to install browser support.") from exc

    profile = Path(config.browser_profile_dir).expanduser()
    profile.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile),
            headless=config.browser_headless,
            accept_downloads=True,
        )
        page = context.pages[0] if context.pages else context.new_page()
        try:
            workflow = str(payload.get("workflow") or "generic")
            if workflow == "chatgpt_image":
                return _chatgpt_image(page, payload)
            return _generic(page, payload)
        finally:
            context.close()
