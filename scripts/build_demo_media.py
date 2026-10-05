import os
import sys
import time
import asyncio
import subprocess
from pathlib import Path
import edge_tts
from playwright.async_api import async_playwright
import imageio_ffmpeg

ASSETS_DIR = Path("assets")
SCREENSHOTS_DIR = ASSETS_DIR / "screenshots"
RAW_VIDEO_DIR = ASSETS_DIR / "raw_video"

SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
RAW_VIDEO_DIR.mkdir(parents=True, exist_ok=True)

VOICEOVER_PATH = ASSETS_DIR / "demo_voiceover.mp3"
FINAL_VIDEO_PATH = ASSETS_DIR / "demo_video.mp4"

VOICEOVER_SCRIPT = """
Under Switzerland's revised Federal Act on Data Protection and FINMA Circular 2018/3, institutions face executive liabilities of up to 250,000 Swiss Francs for unlawful cross-border data transfers.
Foundational models like Apertus unlock unprecedented sovereign intelligence, but enterprises cannot adopt them if sensitive PII traverses unverified boundaries.
Meet Apertus SovereignGate — an enterprise-grade, zero-retention sovereign airlock proxy ensuring complete data residency on Swiss soil.
In our live workbench, an enterprise client ingests confidential healthcare records containing Swiss AHV numbers and medical notes.
In under 0.15 milliseconds, our inbound airlock intercepts the payload. Direct identifiers are converted into deterministic surrogate tokens, keeping CSCS inference nodes strictly anonymized.
As Apertus 70B streams its response back, our outbound restorer unmasks the context dynamically in-flight. Toggling to 'Restored' demonstrates seamless contextual reconstruction.
SovereignGate guarantees strict zero-data-retention via native ctypes memset memory zeroization upon request completion.
With one click on HTML Certificate, compliance officers generate a tamper-proof audit attestation sealed with a cryptographic SHA-256 signature.
With 1-line OpenAI SDK drop-in integration, enterprise adoption requires zero code rewrites. Apertus SovereignGate bridges regulation and AI — verifiable, high-performance, and 100% on Swiss soil.
"""

async def generate_voiceover():
    print("[1/4] Generating Studio Neural Voiceover...")
    communicate = edge_tts.Communicate(VOICEOVER_SCRIPT.strip(), "en-US-ChristopherNeural", rate="+2%")
    await communicate.save(str(VOICEOVER_PATH))

async def run_browser_automation():
    print("[2/4] Recording UI Workflow & Capturing Screenshots...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            record_video_dir=str(RAW_VIDEO_DIR),
            record_video_size={"width": 1920, "height": 1080}
        )
        page = await context.new_page()

        # 1. Hero Dashboard
        await page.goto("http://127.0.0.1:8000", wait_until="networkidle")
        await page.wait_for_timeout(4000)
        await page.screenshot(path=str(SCREENSHOTS_DIR / "01_hero_dashboard.png"), full_page=True)

        # 2. Preset & Airlock Transmit
        healthcare_btn = page.locator("button:has-text('Healthcare'), button:has-text('Clinical')").first
        if await healthcare_btn.count() > 0:
            await healthcare_btn.click()
            await page.wait_for_timeout(1500)

        transmit_btn = page.locator("button:has-text('Transmit Sovereign Airlock')").first
        await transmit_btn.click()
        await page.wait_for_timeout(10000)
        await page.screenshot(path=str(SCREENSHOTS_DIR / "02_inbound_airlock_masking.png"), full_page=True)

        # 3. Restored Output
        restored_tab = page.locator("button:has-text('Restored')").first
        if await restored_tab.count() > 0:
            await restored_tab.click()
            await page.wait_for_timeout(3000)
        await page.screenshot(path=str(SCREENSHOTS_DIR / "03_outbound_restored_view.png"), full_page=True)

        # 4. Certificate
        # Notice: exportFADPCertificateHTML opens a new tab via window.open
        async with context.expect_page() as new_page_info:
            cert_btn = page.locator("button:has-text('HTML Certificate'), a:has-text('HTML Certificate')").first
            if await cert_btn.count() > 0:
                await cert_btn.click()
        
        cert_page = await new_page_info.value
        await cert_page.wait_for_load_state("networkidle")
        await cert_page.wait_for_timeout(2000)
        await cert_page.screenshot(path=str(SCREENSHOTS_DIR / "04_fadp_audit_certificate.png"), full_page=True)
        await cert_page.close()

        # 5. Top Telemetry Bar
        await page.screenshot(path=str(SCREENSHOTS_DIR / "05_zero_retention_telemetry.png"), clip={"x": 0, "y": 0, "width": 1920, "height": 280})

        # 6. OpenAI SDK Drawer Modal (to provide 6 HD Screenshots total)
        sdk_btn = page.locator("button:has-text('OpenAI SDK')").first
        if await sdk_btn.count() > 0:
            await sdk_btn.click()
            await page.wait_for_timeout(1500)
            await page.screenshot(path=str(SCREENSHOTS_DIR / "06_openai_dropin_sdk.png"), full_page=True)

        await page.wait_for_timeout(3000)
        await context.close()
        await browser.close()

def run_cli_tests():
    print("[3/4] Running OpenAI Drop-in Verification...")
    subprocess.run([sys.executable, "tests/test_openai_dropin.py"], check=True)

def mux_video():
    print("[4/4] Muxing Video & Audio via FFmpeg...")
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    recorded_videos = list(RAW_VIDEO_DIR.glob("*.webm"))
    if not recorded_videos:
        print("Error: No recorded webm found.")
        return
    raw_video = recorded_videos[0]
    cmd = [
        ffmpeg_exe, "-y",
        "-i", str(raw_video),
        "-i", str(VOICEOVER_PATH),
        "-c:v", "libx264",
        "-preset", "fast",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        str(FINAL_VIDEO_PATH)
    ]
    subprocess.run(cmd, check=True)
    print(f"\n[DONE] Video ready at: {FINAL_VIDEO_PATH}")
    print(f"[DONE] 6 Screenshots ready at: {SCREENSHOTS_DIR}")

async def main():
    await generate_voiceover()
    await run_browser_automation()
    run_cli_tests()
    mux_video()

if __name__ == "__main__":
    asyncio.run(main())
