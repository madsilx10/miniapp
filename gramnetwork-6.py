"""
GramNetwork Bot
- Quest (complete semua task yang belum selesai, dengan delay 30 detik per task)
- Start Mining
- Claim Mining
- Join Channel (via Pyrogram)
"""

import asyncio
import json
import logging
import time
from urllib.parse import urlparse, parse_qs, urlencode
import urllib.parse

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
    "Referer":      "https://app.gramnetwork.online/",
    "User-Agent":   "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
    "Content-Type": "application/x-www-form-urlencoded",
}
TASK_DELAY    = 32  # detik tunggu sebelum verify task (non-channel)
CHANNEL_DELAY = 5   # detik untuk quest join channel (langsung auto verify)

# Link channel yang mau di-join (isi username doang, tanpa t.me/)
CHANNELS = [
    "Community_Crypto_1",
    "Yes_C_rypto",
    "zoomcrypto_24",
]


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
    url      = result.url
    fragment = url.split("#")[1] if "#" in url else url.split("?")[1]
    params   = urllib.parse.parse_qs(fragment)
    raw      = params.get("tgWebAppData", [None])[0]
    return urllib.parse.unquote(raw)


# ===================== API =====================
def get_user_data(init_data):
    r = requests.get(f"{API_BASE}/get_user_data.php",
                     params={"initData": init_data}, headers=HEADERS, timeout=15)
    r.raise_for_status()
    return r.json()

def get_tasks(init_data):
    r = requests.get(f"{API_BASE}/get_tasks.php",
                     params={"initData": init_data}, headers=HEADERS, timeout=15)
    r.raise_for_status()
    return r.json().get("tasks", [])

def complete_task(init_data, task_id):
    payload = urlencode({"initData": init_data, "task_id": task_id})
    r = requests.post(f"{API_BASE}/complete_task.php", data=payload, headers=HEADERS, timeout=15)
    try:
        return r.json()
    except Exception:
        return {"success": r.status_code == 200}

def start_mining(init_data):
    payload = urlencode({"initData": init_data})
    r = requests.post(f"{API_BASE}/start_mining.php", data=payload, headers=HEADERS, timeout=15)
    try:
        return r.json()
    except Exception:
        return {"success": r.status_code == 200}

def claim_mining(init_data):
    payload = urlencode({"initData": init_data})
    r = requests.post(f"{API_BASE}/claim_mining.php", data=payload, headers=HEADERS, timeout=15)
    try:
        return r.json()
    except Exception:
        return {"success": r.status_code == 200}


# ===================== MODES =====================
async def run_join_channels(client: Client, tag: str):
    if not CHANNELS:
        print(f"{tag} gak ada channel di config")
        return
    for ch in CHANNELS:
        try:
            await client.join_chat(ch)
            print(f"{tag} join @{ch} OK")
        except Exception as e:
            print(f"{tag} join @{ch} gagal: {e}")
        await asyncio.sleep(2)


async def run_quest(init_data: str, tag: str, client: Client = None, join_ch: bool = False):
    if join_ch and client:
        await run_join_channels(client, tag)

    tasks = get_tasks(init_data)
    todo  = [t for t in tasks if not t.get("is_completed") and
             t.get("total_complete", 0) < t.get("completed_limit", 0)]

    print(f"{tag} {len(todo)} task belum selesai")

    for t in todo:
        tid   = t["id"]
        title = t["title"]
        ttype = t.get("type", "")

        is_channel = ttype in ("telegram_chat", "telegram_bot")
        delay = CHANNEL_DELAY if is_channel else TASK_DELAY

        print(f"{tag} task [{tid}] {title} | tunggu {delay}s...")
        time.sleep(delay)

        res = complete_task(init_data, tid)
        if res.get("success"):
            reward = res.get("reward", "?")
            bal    = res.get("new_balance", "?")
            print(f"{tag} ✅ {title} | +{reward} GRM | balance: {bal}")
        else:
            print(f"{tag} ❌ {title} | {res}")


def run_start_mining(init_data: str, tag: str):
    data = get_user_data(init_data)
    user = data.get("user", {})
    status = user.get("mining_status", "")

    if status == "Active":
        time_left = user.get("time_left", "00:00:00")
        print(f"{tag} mining udah aktif, sisa: {time_left}")
        return

    res = start_mining(init_data)
    if res.get("success"):
        print(f"{tag} ✅ start mining OK")
    else:
        print(f"{tag} ❌ start mining gagal: {res}")


def run_claim_mining(init_data: str, tag: str):
    data  = get_user_data(init_data)
    user  = data.get("user", {})
    claim_in = user.get("claim_in", "")
    time_left_seconds = user.get("time_left_seconds", 1)

    if time_left_seconds > 0:
        print(f"{tag} belum bisa claim, sisa: {claim_in}")
        return

    res = claim_mining(init_data)
    if res.get("success"):
        bal = res.get("new_balance") or user.get("total_balance", "?")
        print(f"{tag} ✅ claim mining OK | balance: {bal}")
    else:
        print(f"{tag} ❌ claim gagal: {res}")


# ===================== PER ACCOUNT =====================
async def process(session_string: str, idx: int, total: int, mode: str):
    tag = f"[Akun {idx}/{total}]"
    print(f"\n{'='*40}\n{tag} mulai | mode: {mode}")

    async with Client(name=f"gram{idx}", session_string=session_string,
                      in_memory=True, no_updates=True) as client:
        init_data = await get_init_data(client)

        if mode == "1":
            await run_quest(init_data, tag, client=client, join_ch=True)
            run_start_mining(init_data, tag)
        elif mode == "2":
            await run_quest(init_data, tag)
        elif mode == "3":
            run_start_mining(init_data, tag)
        elif mode == "4":
            run_claim_mining(init_data, tag)


# ===================== MENU =====================
def select_mode():
    print("\nMode:")
    print("  1. Quest + Join Channel + Start Mining")
    print("  2. Quest doang")
    print("  3. Start Mining doang")
    print("  4. Claim Mining doang")
    return input("Pilih mode (1/2/3/4): ").strip()

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

    mode    = select_mode()
    indexed = select_accounts()
    total   = len(indexed)

    for idx, s in indexed:
        try:
            await process(s, idx, total, mode)
        except Exception as e:
            print(f"[Akun {idx}] Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
