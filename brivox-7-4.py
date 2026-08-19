import asyncio
import json
import time
import sys
import os
import urllib.parse
from pyrogram import Client
from pyrogram.raw.functions.messages import RequestWebView
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from curl_cffi import requests as cffi_requests

# ── Config ───────────────────────────────────────────────────────────────────
API_ID       = 0          # ganti
API_HASH     = ""         # ganti
BASE_URL     = "https://brivoxweb3.vip"
BOT_USERNAME = "BrivoxWbe3_bot"
WEBAPP_URL   = "https://brivoxweb3.vip/"
REF_CODE     = "MT04BL7P"
DEAL_ID      = 15
DELAY        = 2          # detik antar request

# ── AES key buat header Authorization (dari Bz5_rvbB.js -> We.encrypt) ────────
AES_KEY = b"J8gD4uKpT2rV9ZbQ"
AES_IV  = b"L1hW7gFqP3kM0VbY"

# ── Warna ────────────────────────────────────────────────────────────────────
R = "\033[31m"; G = "\033[32m"; Y = "\033[33m"
C = "\033[36m"; M = "\033[35m"; W = "\033[0m"

def log(tag, msg, color=C):
    ts = time.strftime("%H:%M:%S")
    print(f"\033[90m[{ts}]\033[0m {color}[{tag}]{W} {msg}")

def ok(t, m):   log(t, m, G)
def warn(t, m): log(t, m, Y)
def err(t, m):  log(t, m, R)
def info(t, m): log(t, m, C)

# ── HTTP helper (curl_cffi -> niru TLS fingerprint Chrome asli) ────────────────
# Session persisten biar TLS handshake & cookies konsisten kayak browser
_session = cffi_requests.Session(impersonate="chrome124")

DEBUG_HTTP = False  # set True lagi kalau butuh debug

def _http_sync(method: str, url: str, headers: dict, json_data: dict | None):
    try:
        resp = _session.request(method, url, headers=headers or {}, json=json_data, timeout=30)
        if DEBUG_HTTP:
            print(f"\033[90m[DEBUG] {method} {url} -> HTTP {resp.status_code}\033[0m")
            interesting = {k: v for k, v in resp.headers.items()
                            if k.lower() in ("server", "cf-ray", "cf-mitigated", "cf-cache-status", "content-type", "set-cookie")}
            print(f"\033[90m[DEBUG] response headers: {interesting}\033[0m")
            print(f"\033[90m[DEBUG] raw body: {resp.text[:500]}\033[0m")
        try:
            return resp.json()
        except Exception:
            return {"error": f"HTTP {resp.status_code}", "detail": resp.text}
    except Exception as e:
        return {"error": "request_failed", "detail": str(e)}

async def http_post(url: str, headers: dict, json_data: dict | None = None) -> dict:
    return await asyncio.to_thread(_http_sync, "POST", url, headers, json_data)

async def http_get(url: str, headers: dict) -> dict:
    return await asyncio.to_thread(_http_sync, "GET", url, headers, None)

# ── Warmup: buka halaman webapp dulu biar dapet cookie session/cf_clearance ────
def _warmup_sync():
    try:
        _session.get(WEBAPP_URL, headers={
            "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        }, timeout=30)
    except Exception as e:
        warn("WARMUP", f"Gagal warmup: {e}")

async def warmup():
    await asyncio.to_thread(_warmup_sync)

# ── Header Authorization ala frontend (bukan token asli, ini fingerprint) ─────
def brivox_encrypt(data: dict) -> str:
    plaintext = json.dumps(data, separators=(",", ":")).encode("utf-8")
    cipher = AES.new(AES_KEY, AES.MODE_CBC, AES_IV)
    ct = cipher.encrypt(pad(plaintext, AES.block_size))
    return __import__("base64").b64encode(ct).decode()

def build_auth_header(uid: str = "", token: str = "", device_id: str = "", referrer_code: str = "") -> str:
    payload = {
        "uid": uid,
        "token": token,
        "time": int(time.time() * 1000),
        "device_id": device_id,
        "referrer_code": referrer_code,
    }
    return brivox_encrypt(payload)

# ── Load sessions ─────────────────────────────────────────────────────────────
def load_sessions():
    if not os.path.exists("sessions.txt"):
        err("INIT", "sessions.txt tidak ditemukan!")
        sys.exit(1)
    lines = [l.strip() for l in open("sessions.txt").readlines() if l.strip()]
    if not lines:
        err("INIT", "sessions.txt kosong!")
        sys.exit(1)
    return lines

# ── Pyrogram: ambil initData ──────────────────────────────────────────────────
async def get_init_data(session_string: str, idx: int, send_start: bool = False) -> str | None:
    client = Client(
        name=f"acc_{idx}",
        api_id=API_ID,
        api_hash=API_HASH,
        session_string=session_string,
        in_memory=True,
        no_updates=True,
    )
    try:
        await client.start()
        info(f"ACC#{idx}", f"Connected: {(await client.get_me()).username}")

        bot = await client.get_users(BOT_USERNAME)

        # Start bot dulu (register/ref) — cuma perlu sekali di awal, bukan tiap run harian
        if send_start:
            try:
                await client.send_message(BOT_USERNAME, f"/start ref_{REF_CODE}")
                await asyncio.sleep(2)
            except Exception:
                pass

        # Request WebApp untuk dapat initData
        result = await client.invoke(
            RequestWebView(
                peer=await client.resolve_peer(BOT_USERNAME),
                bot=await client.resolve_peer(BOT_USERNAME),
                platform="android",
                url=WEBAPP_URL,
                from_bot_menu=False,
            )
        )

        # initData ada di URL fragment setelah #tgWebAppData=
        url = result.url
        if "tgWebAppData=" in url:
            init_data = url.split("tgWebAppData=")[1].split("&tgWebAppVersion")[0]
            init_data = urllib.parse.unquote(init_data)
            ok(f"ACC#{idx}", "initData berhasil didapat ✓")
            return init_data
        else:
            err(f"ACC#{idx}", f"initData tidak ditemukan di URL: {url[:80]}")
            return None

    except Exception as e:
        err(f"ACC#{idx}", f"Pyrogram error: {e}")
        return None
    finally:
        try:
            await client.stop()
        except Exception:
            pass

# ── API: Login ────────────────────────────────────────────────────────────────
async def login(init_data: str, idx: int) -> tuple[str, str] | None:
    try:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Lang": "en",
            "Time": str(int(time.time())),
            "Origin": BASE_URL,
            "Referer": WEBAPP_URL + "login",
            "Authorization": build_auth_header(referrer_code=REF_CODE),
            "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36",
            "Sec-Ch-Ua": '"Chromium";v="137", "Not/A)Brand";v="24"',
            "Sec-Ch-Ua-Mobile": "?1",
            "Sec-Ch-Ua-Platform": '"Android"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        }
        payload = {
            "initData": init_data,
            "referrer_code": REF_CODE,
            "turnstileToken": "",
        }
        data = await http_post(f"{BASE_URL}/api/user/login/tg", headers, payload)
        token = data.get("auth_info")
        uid = data.get("user_info", {}).get("uid", "")  # kode "MTxxxxxxxx", BUKAN user_id numerik
        if token:
            ok(f"ACC#{idx}", f"Login sukses → token: {token[:16]}...")
            return token, uid
        else:
            err(f"ACC#{idx}", f"Login gagal: {data}")
            return None
    except Exception as e:
        err(f"ACC#{idx}", f"Login error: {e}")
        return None

# ── API Headers ───────────────────────────────────────────────────────────────
def build_headers(token: str, uid: str = "") -> dict:
    return {
        "Authorization":  build_auth_header(uid=uid, token=token),
        "Content-Type":   "application/json",
        "Accept":         "application/json",
        "Lang":           "en",
        "Time":           str(int(time.time())),
        "Origin":         BASE_URL,
        "Referer":        BASE_URL + "/",
        "User-Agent":     "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
    }

# ── API: Balance ──────────────────────────────────────────────────────────────
async def get_balance(token: str, uid: str, idx: int):
    try:
        data = await http_get(f"{BASE_URL}/api/crypto/user/crypto-assets/list", build_headers(token, uid))
        brx = next((a for a in data.get("assetsList", []) if a["token"] == "BRX"), None)
        ok(f"ACC#{idx}", f"Balance: {brx['balance'] if brx else '?'} BRX")
    except Exception as e:
        err(f"ACC#{idx}", f"Balance error: {e}")

# ── API: Buy NFT ──────────────────────────────────────────────────────────────
async def buy_nft(token: str, uid: str, idx: int) -> bool:
    try:
        data = await http_post(f"{BASE_URL}/api/deal/user/load/create", build_headers(token, uid), {"deal_id": DEAL_ID})
        if data.get("msg") == "Purchase successful":
            ok(f"ACC#{idx}", "Buy NFT: sukses ✓")
            return True
        else:
            warn(f"ACC#{idx}", f"Buy NFT: {data}")
            return False
    except Exception as e:
        err(f"ACC#{idx}", f"Buy NFT error: {e}")
        return False

# ── API: Spin Info ────────────────────────────────────────────────────────────
async def get_spin_info(token: str, uid: str, idx: int) -> dict | None:
    try:
        data = await http_get(f"{BASE_URL}/api/user/user/user-lottery/info", build_headers(token, uid))
        spin = data.get("info", {})
        info(f"ACC#{idx}", f"Spin → punya: {spin.get('lottery_times')}, sudah: {spin.get('lottery_times_yet')}, limit: {spin.get('limit_times')}")
        return spin
    except Exception as e:
        err(f"ACC#{idx}", f"Spin info error: {e}")
        return None

# ── API: Do Spin ──────────────────────────────────────────────────────────────
async def do_spin(token: str, uid: str, idx: int) -> dict | None:
    try:
        data = await http_post(f"{BASE_URL}/api/user/user/user-lottery/create", build_headers(token, uid), {})
        if data.get("type"):
            ok(f"ACC#{idx}", f"Spin → menang: {data['number']} {data['type']} 🎉")
            return {"number": data["number"], "type": data["type"]}
        else:
            warn(f"ACC#{idx}", f"Spin: {data}")
            return None
    except Exception as e:
        err(f"ACC#{idx}", f"Spin error: {e}")
        return None

# ── Process 1 akun ────────────────────────────────────────────────────────────
async def process_account(session_string: str, idx: int, action: str) -> dict:
    rewards = {}  # {type: total_number} khusus akun ini
    print(f"\n{'─' * 50}")
    info(f"ACC#{idx}", f"Mulai proses akun ke-{idx}...")

    # 1. Ambil initData via Pyrogram
    init_data = await get_init_data(session_string, idx, send_start=(action == "full"))
    if not init_data:
        err(f"ACC#{idx}", "Skip akun ini (gagal ambil initData)")
        return rewards

    # 1.5 Warmup: buka halaman webapp dulu biar dapet cookie sebelum login
    await warmup()
    await asyncio.sleep(1)

    # 2. Login → dapat token + uid
    login_result = await login(init_data, idx)
    if not login_result:
        return rewards
    token, uid = login_result
    await asyncio.sleep(DELAY)

    # 3. Cek balance awal
    await get_balance(token, uid, idx)
    await asyncio.sleep(DELAY)

    # 4. Buy NFT (cuma kalau mode "full")
    if action == "full":
        await buy_nft(token, uid, idx)
        await asyncio.sleep(DELAY)

    # 5. Spin (selalu jalan, di kedua mode)
    spin_info = await get_spin_info(token, uid, idx)
    await asyncio.sleep(DELAY)
    if spin_info:
        available = spin_info.get("lottery_times", 0) - spin_info.get("lottery_times_yet", 0)
        if available <= 0:
            warn(f"ACC#{idx}", "Spin habis hari ini")
        else:
            info(f"ACC#{idx}", f"Spin {available}x...")
            for _ in range(available):
                result = await do_spin(token, uid, idx)
                if result:
                    rewards[result["type"]] = rewards.get(result["type"], 0) + float(result["number"])
                await asyncio.sleep(DELAY)

    # 6. Balance akhir
    await get_balance(token, uid, idx)

    if rewards:
        rekap = ", ".join(f"{v} {k}" for k, v in rewards.items())
        info(f"ACC#{idx}", f"Total reward akun ini: {rekap}")

    return rewards

# ── Main ──────────────────────────────────────────────────────────────────────
async def main():
    print(f"{M}")
    print("╔══════════════════════════════════════╗")
    print("║        BRIVOX WEB3 AUTOMATION        ║")
    print("╚══════════════════════════════════════╝")
    print(f"{W}")

    if not API_ID or not API_HASH:
        err("INIT", "Isi API_ID dan API_HASH dulu di config!")
        sys.exit(1)

    sessions = load_sessions()
    info("INIT", f"Loaded {len(sessions)} akun dari sessions.txt")

    # Mode pilih akun
    print("\nPilih mode:")
    print("  1) 1 akun saja")
    print("  2) Semua akun")
    print("  3) From X to end")
    mode = input("\nPilihan (1/2/3): ").strip()

    if mode == "1":
        idx = int(input(f"Nomor akun (1-{len(sessions)}): "))
        targets = [(sessions[idx - 1], idx)]
    elif mode == "2":
        targets = [(s, i + 1) for i, s in enumerate(sessions)]
    elif mode == "3":
        frm = int(input(f"Mulai dari akun ke- (1-{len(sessions)}): "))
        targets = [(s, frm + i) for i, s in enumerate(sessions[frm - 1:])]
    else:
        err("INPUT", "Pilihan tidak valid")
        sys.exit(1)

    print("\nMode aksi:")
    print("  1) Buy NFT + Spin")
    print("  2) Spin aja (harian)")
    action_input = input("\nPilihan (1/2): ").strip()
    action = "full" if action_input == "1" else "spin_only"

    print(f"\n→ Proses {len(targets)} akun, mode: {'Buy NFT + Spin' if action == 'full' else 'Spin aja'}\n")

    grand_total = {}  # {type: total_number} gabungan semua akun
    for session_string, idx in targets:
        rewards = await process_account(session_string, idx, action)
        for k, v in rewards.items():
            grand_total[k] = grand_total.get(k, 0) + v
        await asyncio.sleep(DELAY)

    print(f"\n{G}✓ Semua akun selesai!{W}")
    if grand_total:
        print(f"\n{M}══════ TOTAL REWARD SEMUA AKUN ══════{W}")
        for k, v in grand_total.items():
            print(f"  {G}{v} {k}{W}")
        print(f"{M}══════════════════════════════════════{W}\n")
    else:
        print(f"{Y}(tidak ada reward yang tercatat){W}\n")

if __name__ == "__main__":
    asyncio.run(main())
