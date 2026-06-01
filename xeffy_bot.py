import asyncio
import json
import os
import urllib.parse
import requests as req
from pyrogram import Client
from pyrogram.raw.functions.messages import RequestWebView

# ── Config ──────────────────────────────────────────────
API_ID   = 0        # isi API ID lu
API_HASH = ""       # isi API Hash lu
BOT_USERNAME = "Xeffy_Bot"
ORG_SLUG = "xeffy"
CAMPAIGN_ID = "447eb124-e731-4853-be60-39aae9bb0127"
BASE_URL = "https://api.go.xeffy.io/api/mini"
DELAY_BETWEEN_ACCOUNTS = 10

# ── Load data ────────────────────────────────────────────
def load_file(path):
    if not os.path.exists(path):
        return []
    with open(path, "r") as f:
        return [line.strip() for line in f if line.strip()]

def load_quiz_answer():
    if not os.path.exists("answers.txt"):
        return None
    with open("answers.txt", "r") as f:
        val = f.read().strip()
        return int(val) if val.isdigit() else None

# ── Xeffy API ────────────────────────────────────────────
def make_headers(session_token):
    return {
        "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Origin": "https://tg.go.xeffy.io",
        "Referer": "https://tg.go.xeffy.io/",
        "Cookie": f"__Secure-xeffy_contrib.session_token={session_token}"
    }

def xeffy_login(init_data):
    r = req.post(
        f"{BASE_URL}/be-auth/sign-in/telegram",
        json={"initData": init_data, "orgSlug": ORG_SLUG},
        headers={
            "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Origin": "https://tg.go.xeffy.io",
            "Referer": "https://tg.go.xeffy.io/",
        }
    )
    if r.status_code in [200, 201]:
        for cookie in r.cookies:
            if "session_token" in cookie.name:
                return cookie.value
    print(f"  Login failed: {r.status_code} | {r.text[:150]}")
    return None

def check_in(session_token):
    r = req.post(f"{BASE_URL}/attendance", headers=make_headers(session_token))
    return r.status_code in [200, 201]

def get_tasks(session_token):
    r = req.get(f"{BASE_URL}/campaigns/{CAMPAIGN_ID}/tasks", headers=make_headers(session_token))
    if r.status_code == 200:
        return r.json().get("items", [])
    return []

def submit_task(session_token, task_id, proof=None):
    if proof is None:
        proof = {}
    r = req.post(
        f"{BASE_URL}/submissions",
        json={"taskId": task_id, "proof": proof},
        headers=make_headers(session_token)
    )
    return r.status_code in [200, 201]

# ── Core logic per akun ──────────────────────────────────
async def run_account(session_string, index, tele_links, mode="full"):
    # mode: "full" | "checkin" | "daily"
    print(f"\n{'='*50}")
    print(f"[Akun {index}] Mulai...")

    async with Client(
        name=f"acc_{index}",
        api_id=API_ID,
        api_hash=API_HASH,
        session_string=session_string,
        in_memory=True
    ) as app:
        me = await app.get_me()
        print(f"[Akun {index}] @{me.username} ({me.id})")

        # Join channel/group — hanya mode full
        if mode == "full" and tele_links:
            print(f"[Akun {index}] Join {len(tele_links)} channel/group...")
            for link in tele_links:
                try:
                    username = link.replace("https://t.me/", "").replace("http://t.me/", "").replace("t.me/", "").strip("/")
                    await app.join_chat(username)
                    print(f"[Akun {index}] ✅ Join: {username}")
                except Exception as e:
                    print(f"[Akun {index}] ⚠️ Join gagal {username}: {e}")
                await asyncio.sleep(2)

        # Request WebView
        bot_peer = await app.resolve_peer(BOT_USERNAME)
        web_view = await app.invoke(
            RequestWebView(
                peer=bot_peer,
                bot=bot_peer,
                platform="android",
                url="https://tg.go.xeffy.io/",
            )
        )

        url = web_view.url
        fragment = url.split("#")[1] if "#" in url else url.split("?")[1]
        params = urllib.parse.parse_qs(fragment)
        tg_web_app_data = params.get("tgWebAppData", [None])[0]

        if not tg_web_app_data:
            print(f"[Akun {index}] ❌ Gagal dapat initData")
            return

        init_data = urllib.parse.unquote(tg_web_app_data)
        print(f"[Akun {index}] ✅ InitData OK")

    # Login
    print(f"[Akun {index}] Login Xeffy...")
    session_token = xeffy_login(init_data)
    if not session_token:
        print(f"[Akun {index}] ❌ Login gagal")
        return
    print(f"[Akun {index}] ✅ Login berhasil")

    # Check in
    ok = check_in(session_token)
    print(f"[Akun {index}] {'✅ Check in' if ok else '⚠️ Check in gagal/sudah'}")

    if mode == "checkin":
        print(f"[Akun {index}] ✅ Selesai!")
        return

    await asyncio.sleep(2)

    # Load jawaban quiz
    quiz_answer = load_quiz_answer()

    # Get tasks
    tasks = get_tasks(session_token)
    print(f"[Akun {index}] {len(tasks)} task ditemukan")

    for task in tasks:
        task_id = task.get("id")
        task_name = task.get("name", "unknown")
        task_kind = task.get("kind", "")
        can_submit = task.get("canSubmit", False)

        if not can_submit:
            continue

        if task_kind == "quiz":
            if quiz_answer is None:
                print(f"[Akun {index}] ⚠️ Skip quiz (answers.txt kosong): {task_name}")
                continue
            proof = {"quizSelectedIndex": quiz_answer}
        else:
            proof = {}

        ok = submit_task(session_token, task_id, proof)
        print(f"[Akun {index}] {'✅' if ok else '❌'} {task_name}")
        await asyncio.sleep(1)

    print(f"[Akun {index}] ✅ Selesai!")

# ── Menu ─────────────────────────────────────────────────
async def main():
    sessions = load_file("sessions.txt")
    tele_links = load_file("channel.txt")
    total = len(sessions)

    print("\n╔══════════════════════════════╗")
    print("║        XEFFY BOT             ║")
    print("╠══════════════════════════════╣")
    print(f"║  Total akun: {total:<17}║")
    print(f"║  Channel: {len(tele_links):<20}║")
    print("╠══════════════════════════════╣")
    print("║  1. Jalanin semua akun       ║")
    print("║  2. Pilih satu akun          ║")
    print("║  3. From akun ke-N           ║")
    print("╠══════════════════════════════╣")
    print("║  Mode:                       ║")
    print("║  A. Full (join + quest)      ║")
    print("║  B. Daily (check-in + quest) ║")
    print("║  C. Check-in only            ║")
    print("╚══════════════════════════════╝")

    choice = input("\nPilih akun (1/2/3): ").strip()

    if choice == "1":
        indices = list(range(total))
    elif choice == "2":
        idx = int(input(f"Pilih akun (1-{total}): ")) - 1
        indices = [idx]
    elif choice == "3":
        start = int(input(f"Mulai dari akun ke- (1-{total}): ")) - 1
        indices = list(range(start, total))
    else:
        print("Pilihan tidak valid.")
        return

    mode_input = input("Pilih mode (A/B/C): ").strip().upper()
    if mode_input == "A":
        mode = "full"
    elif mode_input == "B":
        mode = "daily"
    elif mode_input == "C":
        mode = "checkin"
    else:
        print("Mode tidak valid.")
        return

    for i in indices:
        await run_account(sessions[i], i + 1, tele_links, mode=mode)
        if i != indices[-1]:
            print(f"\n⏳ Delay {DELAY_BETWEEN_ACCOUNTS} detik...")
            await asyncio.sleep(DELAY_BETWEEN_ACCOUNTS)

    print("\n✅ Semua akun selesai!")

if __name__ == "__main__":
    asyncio.run(main())
