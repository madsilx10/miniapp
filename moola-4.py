import asyncio
import json
import urllib.parse
import urllib.request
import time
from pyrogram import Client
from pyrogram.raw import functions

# ── config ──────────────────────────────────────────────────────────────────
SESSION_FILE = "sessions.txt"
BOT_USERNAME = "MoolasBot"
START_PARAM  = "2005545171"
BASE_URL     = "https://moola-peach.vercel.app"

API_ID   = 0          # ← isi
API_HASH = ""         # ← isi

TASKS = ["join_channel", "join_partner"]

# ── helpers ──────────────────────────────────────────────────────────────────
async def get_init_data(app: Client, bot_username: str, start_param: str) -> str:
    bot_peer = await app.resolve_peer(bot_username)
    bot_entity = await app.invoke(
        functions.contacts.ResolveUsername(username=bot_username)
    )
    bot_id = bot_entity.users[0].id

    result = await app.invoke(
        functions.messages.RequestWebView(
            peer=bot_peer,
            bot=await app.resolve_peer(bot_id),
            platform="android",
            url=f"{BASE_URL}/",
            start_param=start_param,
        )
    )
    fragment = result.url.split("#")[1]
    params = dict(urllib.parse.parse_qsl(fragment))

    # decode tgWebAppData (kadang double-encoded)
    raw = params.get("tgWebAppData", "")
    decoded = urllib.parse.unquote(raw)

    # inject start_param kalau belum ada
    inner = dict(urllib.parse.parse_qsl(decoded))
    if "start_param" not in inner:
        decoded = decoded + f"&start_param={start_param}"

    return decoded


def make_headers(init_data: str) -> dict:
    return {
        "accept": "*/*",
        "accept-encoding": "gzip, deflate, br, zstd",
        "accept-language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
        "content-type": "application/json",
        "origin": BASE_URL,
        "referer": f"{BASE_URL}/",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "sec-fetch-storage-access": "active",
        "user-agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
        "x-init-data": init_data,
    }


# ── API calls ────────────────────────────────────────────────────────────────
def api_post(url: str, headers: dict, body: dict = {}) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"_error": str(e)}


def api_get(url: str, headers: dict) -> dict:
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"_error": str(e)}


# ── main flow per akun ───────────────────────────────────────────────────────
async def process_account(session_str: str, idx: int, total: int):
    app = Client(
        name=f"acc_{idx}",
        api_id=API_ID,
        api_hash=API_HASH,
        session_string=session_str,
    )

    async with app:
        me = await app.get_me()
        print(f"\n{'='*55}")
        print(f"[{idx}/{total}] @{me.username} ({me.id})")

        print("  [*] Ambil initData...")
        try:
            init_data = await get_init_data(app, BOT_USERNAME, START_PARAM)
        except Exception as e:
            print(f"  [!] Gagal ambil initData: {e}")
            return

        if not init_data:
            print("  [!] initData kosong, skip.")
            return

        headers = make_headers(init_data)
        print(f"  [+] initData OK ({len(init_data)} chars)")

        # stats warm-up
        stats = api_get(f"{BASE_URL}/api/stats", headers)
        print(f"  [*] totalUsers: {stats.get('totalUsers', '?')}")

        # me
        me_data = api_post(f"{BASE_URL}/api/me", headers, {})
        user = me_data.get("user", {})
        print(f"  [*] onboarded: {user.get('onboarded')} | mining: {user.get('mining', {}).get('active')}")

        # onboard
        if not user.get("onboarded"):
            print("  [*] Onboard...")
            res = api_post(f"{BASE_URL}/api/onboard", headers, {})
            user = res.get("user", user)
            print(f"  [+] onboarded: {user.get('onboarded')}")
            await asyncio.sleep(2)
        else:
            print("  [*] Sudah onboarded.")

        # social tasks
        social_done = user.get("socialDone", [])
        for task_id in TASKS:
            if task_id in social_done:
                print(f"  [*] {task_id}: sudah done.")
                continue
            res = api_post(f"{BASE_URL}/api/tasks/social", headers, {"taskId": task_id})
            new_done = res.get("user", {}).get("socialDone", [])
            print(f"  [+] {task_id}: socialDone={new_done} | credited={res.get('credited')}")
            await asyncio.sleep(3)

        # re-check
        me_data2 = api_post(f"{BASE_URL}/api/me", headers, {})
        user2 = me_data2.get("user", {})

        # mine/start
        mining = user2.get("mining", {})
        if mining.get("active"):
            ends_dt = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(mining.get("endsAt", 0) / 1000))
            print(f"  [*] Mining aktif, selesai: {ends_dt}")
        else:
            res = api_post(f"{BASE_URL}/api/mine/start", headers, {})
            m2 = res.get("user", {}).get("mining", {})
            if m2.get("active"):
                ends_dt = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(m2.get("endsAt", 0) / 1000))
                print(f"  [+] Mining started! Selesai: {ends_dt}")
            else:
                print(f"  [!] Mining gagal: {res}")

    print(f"  [+] Done: @{me.username}")


# ── menu pemilihan mode ───────────────────────────────────────────────────────
def parse_args(sessions: list) -> list:
    total = len(sessions)

    print(f"\n{'='*55}")
    print(f"  Moola Bot | Total akun: {total}")
    print(f"{'='*55}")
    print("  [1] 1 akun saja (pilih nomor)")
    print("  [2] Semua akun")
    print(f"  [3] Dari akun ke-X sampai akhir")
    print(f"{'='*55}")

    choice = input("  Pilih mode [1/2/3]: ").strip()

    if choice == "1":
        num = input(f"  Nomor akun (1-{total}): ").strip()
        try:
            idx = int(num) - 1
            if 0 <= idx < total:
                return [sessions[idx]]
            else:
                print(f"  [!] Nomor tidak valid, jalanin akun pertama.")
                return [sessions[0]]
        except ValueError:
            print("  [!] Input tidak valid, jalanin akun pertama.")
            return [sessions[0]]

    elif choice == "2":
        print(f"  [*] Mode: semua {total} akun")
        return sessions

    elif choice == "3":
        start = input(f"  Mulai dari akun ke- (1-{total}): ").strip()
        try:
            idx = int(start) - 1
            if 0 <= idx < total:
                selected = sessions[idx:]
                print(f"  [*] Mode: akun #{idx+1} sampai #{total} ({len(selected)} akun)")
                return selected
            else:
                print("  [!] Nomor tidak valid, jalanin semua.")
                return sessions
        except ValueError:
            print("  [!] Input tidak valid, jalanin semua.")
            return sessions

    else:
        print("  [!] Pilihan tidak dikenal, jalanin semua.")
        return sessions


# ── entry point ──────────────────────────────────────────────────────────────
async def main():
    with open(SESSION_FILE, "r") as f:
        all_sessions = [line.strip() for line in f if line.strip()]

    selected = parse_args(all_sessions)
    total = len(selected)

    print(f"\n  [*] Mulai proses {total} akun...\n")

    for i, session_str in enumerate(selected, 1):
        try:
            await process_account(session_str, i, total)
        except Exception as e:
            print(f"  [!] Error akun #{i}: {e}")
        if i < total:
            await asyncio.sleep(5)

    print(f"\n{'='*55}")
    print(f"  [+] Selesai! {total} akun diproses.")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    asyncio.run(main())
