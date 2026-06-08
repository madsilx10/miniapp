import asyncio
import requests
import json
from pyrogram import Client
from pyrogram.raw.functions.messages import RequestAppWebView
from pyrogram.raw.types import InputBotAppShortName
from urllib.parse import unquote

# ===================== CONFIG =====================
API_ID = ""       # isi api_id lu
API_HASH = ""     # isi api_hash lu
BOT_USERNAME = "CryptoCatGame_Bot"
APP_SHORT_NAME = "start"
START_PARAM = "u_1878121"
BASE_URL = "https://bot.cryptocat.io/api"
# ==================================================

SESSIONS_FILE = "sessions.txt"


def load_sessions():
    with open(SESSIONS_FILE, "r") as f:
        return [line.strip() for line in f if line.strip()]


async def get_init_data(session_string):
    client = Client(
        name="session",
        api_id=API_ID,
        api_hash=API_HASH,
        session_string=session_string,
        in_memory=True
    )
    async with client:
        peer = await client.resolve_peer(BOT_USERNAME)
        web_view = await client.invoke(
            RequestAppWebView(
                peer=peer,
                app=InputBotAppShortName(bot_id=peer, short_name=APP_SHORT_NAME),
                platform="android",
                write_allowed=True,
                start_param=START_PARAM
            )
        )
        url = web_view.url
        init_data = unquote(url.split("tgWebAppData=")[1].split("&tgWebAppVersion")[0])
        return init_data


async def join_channels(session_string, channels):
    if not channels:
        return
    client = Client(
        name="session",
        api_id=API_ID,
        api_hash=API_HASH,
        session_string=session_string,
        in_memory=True
    )
    async with client:
        for ch in channels:
            try:
                await client.join_chat(ch)
                print(f"    ✅ Joined channel: {ch}")
                await asyncio.sleep(2)
            except Exception as e:
                print(f"    ⚠️ Gagal join {ch}: {e}")


def make_headers(init_data):
    return {
        "Authorization": init_data,
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://bot.cryptocat.io",
        "Referer": "https://bot.cryptocat.io/bot/tasks",
        "Host": "bot.cryptocat.io",
    }


def api_get(url, headers):
    s = requests.Session()
    s.mount("https://", requests.adapters.HTTPAdapter())
    r = s.get(url, headers=headers, verify=True)
    return r


def api_post(url, headers, payload=None):
    s = requests.Session()
    s.mount("https://", requests.adapters.HTTPAdapter())
    r = s.post(url, headers=headers, json=payload, verify=True)
    return r


async def do_quests(headers, session_string):
    r = api_get(f"{BASE_URL}/categories", headers)
    print(f"    🔍 Status: {r.status_code} | Raw: {r.text[:300]}")
    data = r.json()

    all_tasks = []
    for cat in data:
        for task in cat.get("tasks", []):
            if not task.get("done") and task.get("ready"):
                all_tasks.append(task)

    print(f"    📋 Quest tersedia: {len(all_tasks)}")

    for task in all_tasks:
        task_id = task["id"]
        task_name = task.get("name", {}).get("en", f"Task {task_id}")
        param = task.get("param", "")

        # Join channel dulu kalau param ada t.me/
        if "t.me/" in str(param) and "boost" not in str(param) and "tapps_bot" not in str(param):
            ch = param.replace("https://t.me/", "").replace("http://t.me/", "").replace("@", "").split("?")[0]
            if ch:
                print(f"    🔗 Join channel: {ch}")
                await join_channels(session_string, [ch])

        r = api_post(f"{BASE_URL}/tasks/{task_id}", headers)
        res = r.json()
        if res.get("success"):
            print(f"    ✅ Quest done: {task_name}")
        else:
            print(f"    ❌ Quest gagal: {task_name} | {res}")
        await asyncio.sleep(1)


async def do_farming(headers):
    r = api_get(f"{BASE_URL}/me", headers)
    me = r.json()

    farming = me.get("farming")
    if farming and farming.get("will_end_at"):
        print(f"    🌾 Farming sudah aktif, selesai: {farming['will_end_at']}")
    else:
        r = api_post(f"{BASE_URL}/farming/start", headers)
        print(f"    🌾 Farming started: {r.json()}")


async def do_tapping(headers):
    r = api_get(f"{BASE_URL}/boost", headers)
    boost = r.json()

    current = boost.get("current", 0)
    if current <= 0:
        print(f"    👆 Energy habis, skip tapping")
        return

    api_post(f"{BASE_URL}/clicking/start", headers)

    r = api_post(f"{BASE_URL}/clicking/stop", headers, {"clicks": current})
    print(f"    👆 Tap {current} klik: {r.json()}")


async def process_account(idx, session_string, task_choice):
    print(f"\n{'='*40}")
    print(f"Akun #{idx+1}")
    print(f"{'='*40}")

    try:
        print("  🔑 Generate initData...")
        init_data = await get_init_data(session_string)
        print(f"  🔍 initData: {init_data[:150]}")
        headers = make_headers(init_data)

        if task_choice in [1, 3]:
            print("  📋 Mengerjakan quest...")
            await do_quests(headers, session_string)

        if task_choice in [1, 2, 4]:
            print("  🌾 Farming...")
            await do_farming(headers)

        if task_choice in [1, 2, 5]:
            print("  👆 Tapping...")
            await do_tapping(headers)

        print(f"  ✅ Akun #{idx+1} selesai!")

    except Exception as e:
        print(f"  ❌ Error akun #{idx+1}: {e}")


def print_menu():
    print("\n========== CRYPTOCAT BOT ==========")
    print("Pilih akun:")
    print("  1. Satu akun")
    print("  2. Mulai dari akun ke-X sampai selesai")
    print("  3. Semua akun")

    acc_choice = int(input("\nPilihan: "))
    sessions = load_sessions()

    if acc_choice == 1:
        print(f"\nTotal akun: {len(sessions)}")
        start = int(input("Nomor akun: ")) - 1
        selected = [sessions[start]]
        start_idx = start
    elif acc_choice == 2:
        print(f"\nTotal akun: {len(sessions)}")
        start = int(input("Mulai dari akun ke: ")) - 1
        selected = sessions[start:]
        start_idx = start
    else:
        selected = sessions
        start_idx = 0

    print("\nPilih task:")
    print("  1. Full (quest + farm + tap)")
    print("  2. Farm + tap")
    print("  3. Quest only")
    print("  4. Farm only")
    print("  5. Tap only")

    task_choice = int(input("\nPilihan: "))

    return selected, start_idx, task_choice


async def main():
    selected, start_idx, task_choice = print_menu()

    print(f"\n🚀 Memproses {len(selected)} akun...")

    for i, session_string in enumerate(selected):
        await process_account(start_idx + i, session_string, task_choice)
        await asyncio.sleep(3)

    print("\n✅ Semua akun selesai!")


if __name__ == "__main__":
    asyncio.run(main())
