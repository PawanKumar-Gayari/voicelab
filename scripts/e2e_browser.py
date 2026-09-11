#!/usr/bin/env python3
"""Browser-level VoiceLab staging E2E checks.

Requires a staging URL and Playwright. This exercises the real authenticated
browser, workspace state, typed action path, Gemini screen vision, LiveKit
connection/token path, reload recovery, and persistence. Provider audio
interruption still requires a real microphone/speaker test because a synthetic
browser event cannot prove the media path.
"""
from __future__ import annotations
import argparse, os, sys, time
from playwright.sync_api import sync_playwright

BASE = os.getenv("E2E_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
USER = os.getenv("AUTH_USERNAME", "researcher")
PASSWORD = os.getenv("AUTH_PASSWORD", "")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()
    if not PASSWORD:
        print("AUTH_PASSWORD is required", file=sys.stderr)
        return 2

    failures = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.headed)
        context = browser.new_context(permissions=["microphone"], ignore_https_errors=False)
        page = context.new_page()
        try:
            page.goto(BASE + "/login", wait_until="networkidle")
            page.locator("#username").fill(USER)
            page.locator("#password").fill(PASSWORD)
            page.locator("button[type=submit]").click()
            page.wait_for_url(BASE + "/", timeout=10000)

            # Home -> owned session -> workspace.
            page.locator("#start-research").click()
            page.wait_for_url("**/workspace?session_id=*")
            page.wait_for_selector("#text-command-input")

            # BF3 is the canonical demo molecule and should already be visible.
            page.wait_for_function("document.body.innerText.includes('BF3')", timeout=10000)

            # Typed path exercises the same deterministic scientific tools.
            inp = page.locator("#text-command-input")
            inp.fill("Analyze this molecule")
            page.locator("#text-command-send").click()
            page.wait_for_timeout(1200)
            page.wait_for_function("document.body.innerText.includes('D3h')", timeout=10000)

            # Negative proof path.
            inp.fill("Test C4")
            page.locator("#text-command-send").click()
            page.wait_for_function("document.body.innerText.includes('C4 FAILED') || document.body.innerText.includes('C4 ✗ FAILED')", timeout=10000)

            # Screen vision is a real Gemini request in staging.
            page.locator("#vision-screen").click()
            page.wait_for_timeout(2500)
            if not page.locator("#vision-result").inner_text().strip():
                failures.append("Gemini vision result was empty")

            # LiveKit browser path: connect by clicking the voice orb.
            page.locator("#voice-orb").click()
            page.wait_for_timeout(2500)
            if "Connecting" not in page.locator("body").inner_text() and "Connected" not in page.locator("body").inner_text() and "Ready" not in page.locator("body").inner_text():
                failures.append("LiveKit browser connection state was not surfaced")

            # Reload recovery: session URL remains valid and state should return.
            current = page.url
            page.reload(wait_until="networkidle")
            page.wait_for_selector("#text-command-input")
            page.wait_for_function("document.body.innerText.includes('D3h')", timeout=10000)
            if page.url != current:
                failures.append("Workspace reload did not preserve session URL")
        finally:
            browser.close()

    if failures:
        for failure in failures:
            print("FAIL:", failure)
        return 1
    print("PASS: browser E2E auth/session/typed/science/vision/reload checks")
    print("NOTE: real microphone barge-in remains a media-device staging gate.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
