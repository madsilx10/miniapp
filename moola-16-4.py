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

SOCIAL_TASKS = [
    "join_channel", "join_partner",
    "follow_x", "subscribe_youtube",
    "fb_engage", "fb_follow",
    "tt_follow", "tt_like2", "tt_share", "tt_comment1",
    "yt_comment", "yt2_comment", "yt_like", "yt_share",
    "x_engage_all", "x_like", "x_retweet2", "x_comment", "x_vote",
    "retweet", "react_post", "boost_channel",
]

# ── helpers ──────────────────────────────────────────────────────────────────
async def get_init_data(app: Client, bot_username: str, start_param: str) -> str:
    bot_peer = await app.resolve_peer(bot_username)
    bot_entity = await app.invoke(
        functions.contacts.ResolveUsername(username=bot_username)
    )
    bot_id = bot_entity.users[0].id

    # Kirim /start <ref> dulu biar referral ke-register di Telegram
    try:
        await app.invoke(
            functions.messages.StartBot(
                bot=bot_peer,
                peer=bot_peer,
                start_param=start_param,
                random_id=int(time.time() * 1000),
            )
        )
        await asyncio.sleep(2)
    except Exception:
        pass  # akun udah pernah start sebelumnya, lanjut aja

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
    return params.get("tgWebAppData", "")


def make_headers(init_data: str) -> dict:
    return {
        "accept": "*/*",
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
def api_call(url: str, headers: dict, body: dict = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    method = "POST" if body is not None else "GET"
    h = {**headers, "accept-encoding": "identity"}
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body_txt = e.read().decode(errors="ignore")
        return {"_error": f"HTTP {e.code}", "_body": body_txt[:300]}
    except Exception as e:
        return {"_error": str(e)}


def api_post(url, headers, body={}):
    return api_call(url, headers, body)

def api_get(url, headers):
    return api_call(url, headers, None)


# ── flows ────────────────────────────────────────────────────────────────────
def do_onboard(headers, user):
    if not user.get("onboarded"):
        print("  [*] Onboard...")
        res = api_post(f"{BASE_URL}/api/onboard", headers, {})
        user = res.get("user", user)
        print(f"  [+] Onboarded: {user.get('onboarded')}")
        time.sleep(2)
    else:
        print("  [*] Sudah onboarded.")
    return user


def do_social_tasks(headers, user):
    social_done = user.get("socialDone", [])
    new_done = 0
    for task_id in SOCIAL_TASKS:
        if task_id in social_done:
            continue
        res = api_post(f"{BASE_URL}/api/tasks/social", headers, {"taskId": task_id})
        updated_done = res.get("user", {}).get("socialDone", [])
        credited = res.get("credited")
        if credited:
            print(f"  [+] {task_id}: credited ✓")
            new_done += 1
        elif "_error" in res:
            print(f"  [!] {task_id}: {res['_error']}")
        else:
            print(f"  [~] {task_id}: {res.get('_body', 'no credit')[:80]}")
        social_done = updated_done
        time.sleep(3)
    if new_done == 0:
        print("  [*] Semua social task sudah done.")


def do_checkin(headers, user):
    checkin = user.get("checkin", {})
    if not checkin.get("canClaim"):
        print(f"  [*] Checkin sudah dilakukan hari ini (day {checkin.get('day', '?')})")
        return
    res = api_post(f"{BASE_URL}/api/tasks/checkin", headers, {})
    new_checkin = res.get("user", {}).get("checkin", {})
    reward = res.get("reward") or new_checkin.get("reward")
    if "_error" in res:
        print(f"  [!] Checkin gagal: {res['_error']}")
    else:
        print(f"  [+] Checkin day {new_checkin.get('day', '?')} ✓ | reward: {reward}")


def do_mining(headers, user):
    mining = user.get("mining", {})
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
            print(f"  [!] Mining gagal: {res.get('_error', res)}")


# ── main flow per akun ───────────────────────────────────────────────────────
async def process_account(session_str: str, idx: int, total: int, mode: str):
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
        print(f"  [+] initData OK")

        me_data = api_post(f"{BASE_URL}/api/me", headers, {})
        user = me_data.get("user", {})

        if "_error" in me_data:
            print(f"  [!] Auth gagal: {me_data['_error']}")
            return

        bal = user.get("balance", "?")
        print(f"  [*] Balance: {bal} MOOLA | mining: {user.get('mining', {}).get('active')}")

        if mode == "full":
            user = do_onboard(headers, user)
            do_social_tasks(headers, user)
            me_data2 = api_post(f"{BASE_URL}/api/me", headers, {})
            user2 = me_data2.get("user", user)
            do_checkin(headers, user2)
            do_mining(headers, user2)

        elif mode == "daily":
            do_checkin(headers, user)
            do_mining(headers, user)

        elif mode == "tasks":
            user = do_onboard(headers, user)
            do_social_tasks(headers, user)

    print(f"  [+] Done: @{me.username}")


# ── menu ─────────────────────────────────────────────────────────────────────
def select_accounts(sessions: list) -> list:
    total = len(sessions)
    print(f"\n{'='*55}")
    print(f"  Moola Bot | Total akun: {total}")
    print(f"{'='*55}")
    print("  [1] 1 akun saja")
    print("  [2] Semua akun")
    print("  [3] Dari akun ke-X sampai akhir")
    print(f"{'='*55}")

    choice = input("  Pilih akun [1/2/3]: ").strip()
    if choice == "1":
        num = input(f"  Nomor akun (1-{total}): ").strip()
        try:
            idx = int(num) - 1
            return [sessions[idx]] if 0 <= idx < total else [sessions[0]]
        except ValueError:
            return [sessions[0]]
    elif choice == "3":
        start = input(f"  Mulai dari akun ke- (1-{total}): ").strip()
        try:
            idx = int(start) - 1
            return sessions[idx:] if 0 <= idx < total else sessions
        except ValueError:
            return sessions
    return sessions


def select_mode() -> str:
    print(f"\n{'='*55}")
    print("  Mode:")
    print("  [1] Full  — onboard + semua task + checkin + mining")
    print("  [2] Daily — checkin + mining saja")
    print("  [3] Tasks — onboard + social task saja")
    print(f"{'='*55}")
    choice = input("  Pilih mode [1/2/3]: ").strip()
    return {"1": "full", "2": "daily", "3": "tasks"}.get(choice, "daily")


# ── entry point ──────────────────────────────────────────────────────────────
async def main():
    with open(SESSION_FILE, "r") as f:
        all_sessions = [line.strip() for line in f if line.strip()]

    selected = select_accounts(all_sessions)
    mode = select_mode()
    total = len(selected)

    print(f"\n  [*] Mode: {mode} | Proses {total} akun...\n")

    for i, session_str in enumerate(selected, 1):
        try:
            await process_account(session_str, i, total, mode)
        except Exception as e:
            print(f"  [!] Error akun #{i}: {e}")
        if i < total:
            await asyncio.sleep(5)

    print(f"\n{'='*55}")
    print(f"  [+] Selesai! {total} akun diproses.")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    asyncio.run(main())
