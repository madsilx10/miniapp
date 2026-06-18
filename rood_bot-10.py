import asyncio
import urllib.parse
import requests as req
from pyrogram import Client
from pyrogram.raw.functions.messages import RequestWebView

def _silence_closed_db_error(loop, context):
    """Pyrogram kadang masih nulis update di background pas client udah
    di-stop, munculin 'Cannot operate on a closed database'. Ini harmless
    (cuma metadata peer, ga ngaruh ke initData/referral), jadi diredam aja
    biar log bersih."""
    exc = context.get("exception")
    if exc and "closed database" in str(exc):
        return
    loop.default_exception_handler(context)

# ── Config ──────────────────────────────────────────────
API_ID       = 0       # isi API ID lu
API_HASH     = ""      # isi API Hash lu
BOT_USERNAME = "RoodcoinBot"
BOT_APP      = "rood"
REF_ID       = "2005545171"
CHANNEL      = "roodcoin"
BASE_URL     = "https://rood-miner-production.up.railway.app/api"
WEBAPP_URL   = "https://rood-telegram-mini-app-production.up.railway.app/"
DELAY        = 10

# ── Load sessions ────────────────────────────────────────
def load_file(path):
    try:
        with open(path, "r") as f:
            return [l.strip() for l in f if l.strip()]
    except FileNotFoundError:
        return []

# ── Headers ──────────────────────────────────────────────
def make_headers(init_data):
    return {
        "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Origin": WEBAPP_URL.rstrip("/"),
        "Referer": WEBAPP_URL,
        "X-Init-Data": init_data,
    }

# ── API Calls ────────────────────────────────────────────
def get_state(init_data):
    r = req.get(f"{BASE_URL}/state", headers=make_headers(init_data))
    if r.status_code == 200:
        return r.json()
    return None

def post_referral(init_data):
    r = req.post(f"{BASE_URL}/referral", json={"referrerId": REF_ID}, headers=make_headers(init_data))
    return r.status_code in [200, 201]

def get_challenge(init_data):
    r = req.get(f"{BASE_URL}/market/claim-challenge", headers=make_headers(init_data))
    if r.status_code == 200:
        return r.json()
    return None

def solve_captcha(question):
    try:
        # Soal format: "1 + 3", "5 - 2", dll
        return str(eval(question))
    except Exception:
        return None

def claim_reward(init_data, captcha_answer, captcha_token):
    r = req.post(
        f"{BASE_URL}/market/claim-reward",
        json={"captchaAnswer": captcha_answer, "captchaToken": captcha_token},
        headers=make_headers(init_data)
    )
    if r.status_code == 200:
        return r.json()
    return None

def claim_mining(init_data):
    r = req.post(f"{BASE_URL}/claim", headers=make_headers(init_data))
    if r.status_code == 200:
        return r.json()
    return None

def install_gpu(init_data, gpu_id, rig_id, slot_index=0):
    r = req.post(
        f"{BASE_URL}/inventory/install",
        json={"gpuId": gpu_id, "rigId": rig_id, "slotIndex": slot_index},
        headers=make_headers(init_data)
    )
    if r.status_code == 200:
        return r.json()
    return None

# ── Get InitData via Pyrogram ─────────────────────────────
async def get_init_data(session_string, index):
    app = Client(
        name=f"acc_{index}",
        api_id=API_ID,
        api_hash=API_HASH,
        session_string=session_string,
        in_memory=True
    )
    await app.start()
    try:
        me = await app.get_me()
        print(f"[Akun {index}] @{me.username} ({me.id})")

        bot_peer = await app.resolve_peer(BOT_USERNAME)
        web_view = await app.invoke(
            RequestWebView(
                peer=bot_peer,
                bot=bot_peer,
                platform="android",
                url=WEBAPP_URL,
                start_param=REF_ID,
            )
        )

        url = web_view.url
        fragment = url.split("#")[1] if "#" in url else url.split("?", 1)[1]
        params = urllib.parse.parse_qs(fragment)
        tg_web_app_data = params.get("tgWebAppData", [None])[0]

        result = urllib.parse.unquote(tg_web_app_data) if tg_web_app_data else None
    finally:
        await app.stop()

    return result, me

# ── Join Channel ──────────────────────────────────────────
async def join_channel(session_string, index):
    async with Client(
        name=f"acc_{index}",
        api_id=API_ID,
        api_hash=API_HASH,
        session_string=session_string,
        in_memory=True
    ) as app:
        try:
            await app.join_chat(CHANNEL)
            print(f"[Akun {index}] ✅ Join @{CHANNEL}")
        except Exception as e:
            print(f"[Akun {index}] ⚠️ Join channel: {e}")

# ── Modes ─────────────────────────────────────────────────
async def mode_install(init_data, index):
    """Claim free GPU card lalu install ke rig"""
    state = get_state(init_data)
    if not state:
        print(f"[Akun {index}] ❌ Gagal ambil state")
        return

    rigs = state.get("rigs", [])
    if not rigs:
        print(f"[Akun {index}] ❌ Tidak ada rig ditemukan")
        return
    rig_id = rigs[0]["id"]
    slot_count = rigs[0].get("slot_count", 7)

    # Hitung slot yang sudah terpakai
    inventory = state.get("inventory", [])
    used_slots = {item["slot_index"] for item in inventory if item.get("rig_id") == rig_id}
    available_slots = [s for s in range(slot_count) if s not in used_slots]

    if not available_slots:
        print(f"[Akun {index}] ⚠️ Semua slot penuh ({slot_count}/{slot_count})")
        return

    # Claim card
    print(f"[Akun {index}] 🎰 Claim free GPU card...")
    challenge = get_challenge(init_data)
    if not challenge:
        print(f"[Akun {index}] ❌ Gagal ambil challenge")
        return

    question = challenge.get("question", "")
    token = challenge.get("token", "")
    answer = solve_captcha(question)
    print(f"[Akun {index}] 🔢 Captcha: {question} = {answer}")

    if not answer:
        print(f"[Akun {index}] ❌ Gagal solve captcha")
        return

    result = claim_reward(init_data, answer, token)
    if not result or not result.get("ok"):
        print(f"[Akun {index}] ❌ Claim reward gagal: {result}")
        return

    gpu_id = result.get("gpuId")
    print(f"[Akun {index}] ✅ Dapat GPU ID: {gpu_id}")

    # Install
    slot = available_slots[0]
    print(f"[Akun {index}] 🔧 Install GPU ke slot {slot}...")
    res = install_gpu(init_data, gpu_id, rig_id, slot)
    if res and res.get("ok"):
        print(f"[Akun {index}] ✅ GPU terinstall di slot {slot}")
    else:
        print(f"[Akun {index}] ❌ Install gagal: {res}")

async def mode_install_only(init_data, index):
    """Install GPU dari inventory yang belum terpasang"""
    state = get_state(init_data)
    if not state:
        print(f"[Akun {index}] ❌ Gagal ambil state")
        return

    rigs = state.get("rigs", [])
    if not rigs:
        print(f"[Akun {index}] ❌ Tidak ada rig ditemukan")
        return
    rig_id = rigs[0]["id"]
    slot_count = rigs[0].get("slot_count", 7)

    inventory = state.get("inventory", [])
    uninstalled = [item for item in inventory if not item.get("rig_id")]
    used_slots = {item["slot_index"] for item in inventory if item.get("rig_id") == rig_id}
    available_slots = [s for s in range(slot_count) if s not in used_slots]

    if not uninstalled:
        print(f"[Akun {index}] ⚠️ Tidak ada GPU di inventory yang belum terpasang")
        return

    if not available_slots:
        print(f"[Akun {index}] ⚠️ Semua slot penuh ({slot_count}/{slot_count})")
        return

    for gpu, slot in zip(uninstalled, available_slots):
        gpu_id = gpu["id"]
        print(f"[Akun {index}] 🔧 Install GPU {gpu_id} ke slot {slot}...")
        res = install_gpu(init_data, gpu_id, rig_id, slot)
        if res and res.get("ok"):
            print(f"[Akun {index}] ✅ GPU {gpu_id} terinstall di slot {slot}")
        else:
            print(f"[Akun {index}] ❌ Install gagal: {res}")
        await asyncio.sleep(1)

async def mode_claim(init_data, index):
    """Klaim hasil mining"""
    state = get_state(init_data)
    if not state:
        print(f"[Akun {index}] ❌ Gagal ambil state")
        return

    pending = state.get("pendingReward", 0)
    balance = state.get("balance", 0)
    print(f"[Akun {index}] 💰 Balance: {balance} | Pending: {pending}")

    if pending <= 0:
        print(f"[Akun {index}] ⚠️ Tidak ada reward untuk diklaim")
        return

    result = claim_mining(init_data)
    if result and result.get("ok"):
        print(f"[Akun {index}] ✅ Claim berhasil! Balance: {result.get('balance', 0)} | Claimed: {result.get('claimed', 0)}")
    else:
        print(f"[Akun {index}] ❌ Claim gagal: {result}")

# ── Run per akun ──────────────────────────────────────────
async def run_account(session_string, index, mode):
    print(f"\n{'='*50}")
    print(f"[Akun {index}] Mulai... (mode: {mode})")

    # Join channel dulu (mode install)
    if mode in ["install", "install_only"]:
        await join_channel(session_string, index)

    # Ambil initData
    init_data, me = await get_init_data(session_string, index)
    if not init_data:
        print(f"[Akun {index}] ❌ Gagal dapat initData")
        return

    print(f"[Akun {index}] ✅ InitData OK")

    # Trigger dulu /state biar backend bikin record user (kalau belum ada)
    get_state(init_data)

    # Baru daftarin referral, setelah user pasti exist di backend
    ref_ok = post_referral(init_data)
    if ref_ok:
        print(f"[Akun {index}] ✅ Referral terdaftar (REF_ID: {REF_ID})")
    else:
        print(f"[Akun {index}] ⚠️ Referral gagal/sudah terdaftar sebelumnya")

    if mode == "install":
        await mode_install(init_data, index)
    elif mode == "install_only":
        await mode_install_only(init_data, index)
    elif mode == "claim":
        await mode_claim(init_data, index)

    print(f"[Akun {index}] ✅ Selesai!")

# ── Main ──────────────────────────────────────────────────
async def main():
    sessions = load_file("sessions.txt")
    total = len(sessions)

    print("\n╔══════════════════════════════╗")
    print("║        ROOD MINER BOT        ║")
    print("╠══════════════════════════════╣")
    print(f"║  Total akun: {total:<17}║")
    print("╠══════════════════════════════╣")
    print("║  Pilih akun:                 ║")
    print("║  1. Semua akun               ║")
    print("║  2. Satu akun                ║")
    print("║  3. Dari akun ke-N           ║")
    print("╠══════════════════════════════╣")
    print("║  Mode:                       ║")
    print("║  A. Claim card + Install GPU ║")
    print("║  B. Install GPU (dari invent)║")
    print("║  C. Claim mining reward      ║")
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
        mode = "install"
    elif mode_input == "B":
        mode = "install_only"
    elif mode_input == "C":
        mode = "claim"
    else:
        print("Mode tidak valid.")
        return

    for i in indices:
        await run_account(sessions[i], i + 1, mode)
        if i != indices[-1]:
            print(f"\n⏳ Delay {DELAY} detik...")
            await asyncio.sleep(DELAY)

    print("\n✅ Semua akun selesai!")

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.set_exception_handler(_silence_closed_db_error)
    loop.run_until_complete(main())
