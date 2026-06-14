"""
GramNetwork Auto Verify
- Login via Pyrogram initData (RequestWebView, tanpa kurigram)
- POST verify_channel.php dengan retry otomatis
"""

import asyncio
import json
import logging
import time
import urllib.parse
from urllib.parse import urlparse, parse_qs, urlencode

import requests
from pyrogram import Client
from pyrogram.raw.functions.messages import RequestWebView

logging.getLogger("pyrogram").setLevel(logging.ERROR)

# ===================== CONFIG =====================
BOT_USERNAME  = "Gramnetwork_bot"
START_PARAM   = "2005545171"
WEBVIEW_URL   = "https://app.gramnetwork.online/"
SESSIONS_FILE = "sessions.txt"
API_BASE      = "https://app.gramnetwork.online/api"
HEADERS       = {
    "Origin":       "https://app.gramnetwork.online",
    "Referer":      f"https://app.gramnetwork.online/?tgWebAppStartParam={START_PARAM}",
    "User-Agent":   "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
    "Content-Type": "application/x-www-form-urlencoded",
}
MAX_RETRY   = 10
RETRY_DELAY = 3


def load_sessions():
    try:
        with open(SESSIONS_FILE) as f:
            return [l.strip() for l in f if l.strip()]
    except FileNotFoundError:
        return []

SESSIONS = load_sessions()


# ===================== INIT DATA =====================
async def get_init_data(client: Client) -> str:
    peer   = await client.resolve_peer(BOT_USERNAME)
    result = await client.invoke(
        RequestWebView(peer=peer, bot=peer, platform="android", url=WEBVIEW_URL)
    )
    url    = result.url
    fragment = url.split("#")[1] if "#" in url else url.split("?")[1]
    params   = urllib.parse.parse_qs(fragment)
    raw      = params.get("tgWebAppData", [None])[0]
    return urllib.parse.unquote(raw)


# ===================== VERIFY =====================
def verify(init_data: str, tag: str) -> bool:
    payload = urlencode({"initData": init_data})
    for attempt in range(1, MAX_RETRY + 1):
        try:
            r = requests.post(f"{API_BASE}/verify_channel.php", data=payload, headers=HEADERS, timeout=15)
            if r.status_code == 200:
                try:
                    data = r.json()
                    if data.get("success") == True:
                        print(f"{tag} verify OK (attempt {attempt})")
                        return True
                    else:
                        msg = data.get("message", "unknown")
                        print(f"{tag} gagal: {msg}, retry {attempt}/{MAX_RETRY}...")
                except Exception:
                    print(f"{tag} response gak valid, retry {attempt}/{MAX_RETRY}...")
            else:
                print(f"{tag} HTTP {r.status_code}, retry {attempt}/{MAX_RETRY}...")
        except Exception as e:
            print(f"{tag} error: {e}, retry {attempt}/{MAX_RETRY}...")
        time.sleep(RETRY_DELAY)
    print(f"{tag} verify gagal setelah {MAX_RETRY}x")
    return False


# ===================== PER ACCOUNT =====================
async def process(session_string: str, idx: int, total: int):
    tag = f"[Akun {idx}/{total}]"
    print(f"\n{'='*40}\n{tag} mulai")

    async with Client(name=f"gram{idx}", session_string=session_string, in_memory=True, no_updates=True) as client:
        init_data = await get_init_data(client)
    print(f"{tag} initData preview: {init_data[:150]}...")

    verify(init_data, tag)


# ===================== MENU =====================
def select_accounts():
    n = len(SESSIONS)
    print(f"\nTotal akun: {n}")
    print("  1. Satu akun")
    print("  2. Semua akun")
    print("  3. Range (dari - sampai)")
    choice = input("Pilih (1/2/3): ").strip()

    if choice == "1":
        idx = int(input(f"Index akun (1-{n}): ").strip())
        return [(idx, SESSIONS[idx - 1])]
    if choice == "3":
        start = int(input(f"Dari (1-{n}): ").strip())
        end   = int(input(f"Sampai (1-{n}): ").strip())
        return [(i, SESSIONS[i - 1]) for i in range(start, end + 1)]
    return list(enumerate(SESSIONS, start=1))


# ===================== MAIN =====================
async def main():
    if not SESSIONS:
        print("sessions.txt kosong / gak ketemu.")
        return

    indexed = select_accounts()
    total   = len(indexed)

    for idx, s in indexed:
        try:
            await process(s, idx, total)
        except Exception as e:
            print(f"[Akun {idx}] Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
