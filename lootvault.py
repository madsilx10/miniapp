import asyncio
import random
import requests
from pyrogram import Client
from pyrogram.raw.functions.messages import RequestWebView
from pyrogram.raw.types import InputUser
from tonsdk.crypto import mnemonic_to_wallet_key
from tonsdk.contract.wallet import Wallets, WalletVersionEnum
from urllib.parse import unquote

API_ID = 0        # ganti dengan api_id lo
API_HASH = ""     # ganti dengan api_hash lo

BOT_USERNAME = "LootVaultDexBot"
REF_ID = "ref_2005545171"
MINI_APP_URL = "https://lootvault.lol/"
BASE_URL = "https://lootvault.lol/vx"

UA = "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"

def get_headers(init_data: str) -> dict:
    return {
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
        "Content-Type": "application/json",
        "Host": "lootvault.lol",
        "Origin": "https://lootvault.lol",
        "Referer": "https://lootvault.lol/",
        "Sec-Ch-Ua": '"Mises";v="141", "Not?A_Brand";v="8", "Chromium";v="141"',
        "Sec-Ch-Ua-Mobile": "?1",
        "Sec-Ch-Ua-Platform": '"Android"',
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-Storage-Access": "active",
        "User-Agent": UA,
        "X-Tg-Init": init_data,
    }

def ton_addr_from_mnemonic(phrase: str) -> str:
    words = phrase.strip().split()
    _, pub_key = mnemonic_to_wallet_key(words)
    _, _, _, wallet = Wallets.create(WalletVersionEnum.v4r2, pub_key=pub_key, workchain=0)
    return wallet.address.to_string(True, True, True)

async def get_init_data(session_string: str) -> str:
    app = Client(
        name="session",
        session_string=session_string,
        api_id=API_ID,
        api_hash=API_HASH,
        no_updates=True,
    )
    async with app:
        peer = await app.resolve_peer(BOT_USERNAME)
        await app.send_message(BOT_USERNAME, f"/start {REF_ID}")
        await asyncio.sleep(2)
        web_view = await app.invoke(
            RequestWebView(
                peer=peer,
                bot=peer,
                platform="android",
                url=MINI_APP_URL,
                start_param=REF_ID,
            )
        )
        init_data = unquote(web_view.url.split("tgWebAppData=")[1].split("&tgWebAppVersion")[0])
        return init_data

def http_get(url, headers):
    r = requests.get(url, headers=headers)
    return r.json()

def http_post(url, headers, payload):
    r = requests.post(url, headers=headers, json=payload)
    return r.json()

async def register_account(session: str, phrase: str):
    print(f"[*] Mulai proses akun...")

    try:
        init_data = await get_init_data(session)
        print(f"[+] initData OK")
    except Exception as e:
        print(f"[-] Gagal ambil initData: {e}")
        return

    try:
        ton_addr = ton_addr_from_mnemonic(phrase)
        print(f"[+] TON addr: {ton_addr[:20]}...")
    except Exception as e:
        print(f"[-] Gagal derive wallet: {e}")
        return

    headers = get_headers(init_data)

    # Step 1: cek status akun
    data = await asyncio.to_thread(http_get, f"{BASE_URL}/a0", headers)
    if not data.get("ok"):
        print(f"[-] a0 gagal: {data}")
        return
    if data["d"].get("registered"):
        print(f"[!] Akun sudah terdaftar, skip")
        return
    print(f"[+] a0 OK - belum registered")

    await asyncio.sleep(random.uniform(1, 2))

    # Step 2: ambil captcha slider
    data = await asyncio.to_thread(http_post, f"{BASE_URL}/cp1", headers, {})
    if not data.get("ok"):
        print(f"[-] cp1 gagal: {data}")
        return
    captcha_id = data["d"]["id"]
    print(f"[+] cp1 OK")

    await asyncio.sleep(random.uniform(1, 2))

    # Step 3: jawab slider
    slider_payload = {
        "id": captcha_id,
        "duration": random.randint(900, 1800),
        "moves": random.randint(150, 280),
        "slide": True,
    }
    data = await asyncio.to_thread(http_post, f"{BASE_URL}/cp2", headers, slider_payload)
    if not data.get("ok"):
        print(f"[-] cp2 gagal: {data}")
        return
    captcha_token = data["d"]["token"]
    print(f"[+] cp2 OK - token didapat")

    await asyncio.sleep(random.uniform(1, 2))

    # Step 4: konek wallet
    data = await asyncio.to_thread(http_post, f"{BASE_URL}/wc3", headers, {"addr": ton_addr})
    if not data.get("ok"):
        print(f"[-] wc3 gagal: {data}")
        return
    print(f"[+] wc3 OK")

    await asyncio.sleep(random.uniform(1, 2))

    # Step 5: register
    reg_payload = {
        "captchaToken": captcha_token,
        "addr": ton_addr,
        "termsAccepted": True,
    }
    data = await asyncio.to_thread(http_post, f"{BASE_URL}/a1", headers, reg_payload)
    if not data.get("ok"):
        print(f"[-] a1 gagal: {data}")
        return
    print(f"[+] Register OK - id: {data['d']['id']}")

    await asyncio.sleep(random.uniform(1, 2))

    # Step 6: dashboard
    data = await asyncio.to_thread(http_get, f"{BASE_URL}/d2", headers)
    if not data.get("ok"):
        print(f"[-] d2 gagal: {data}")
        return
    d = data["d"]
    print(f"[+] Dashboard OK")
    print(f"    Balance : {d.get('b', 0)}")
    print(f"    Level   : {d.get('lvl', 0)}")
    print(f"    Daily   : {d.get('daily', 0)}")
    print(f"    Speed   : {d.get('spd', 0)}/jam")
    print(f"    League  : {d.get('league', {}).get('name', '-')}")

async def run_accounts(sessions, wallets, indices):
    for i, idx in enumerate(indices):
        print(f"\n{'='*40}")
        print(f"[*] Akun {i+1}/{len(indices)} (#{idx+1})")
        await register_account(sessions[idx], wallets[idx])
        if i < len(indices) - 1:
            delay = random.uniform(10, 60)
            print(f"[*] Delay {delay:.1f}s...\n")
            await asyncio.sleep(delay)
    print(f"\n[*] Selesai!")

async def main():
    with open("sessions.txt") as f:
        sessions = [l.strip() for l in f if l.strip()]
    with open("wallet.txt") as f:
        wallets = [l.strip() for l in f if l.strip()]

    if len(sessions) != len(wallets):
        print(f"[!] Jumlah session ({len(sessions)}) != wallet ({len(wallets)})")
        return

    total = len(sessions)
    print(f"[*] Total akun: {total}\n")
    print(f"Pilih mode:")
    print(f"  1. Satu akun")
    print(f"  2. Semua akun")
    print(f"  3. Dari akun X sampai akhir")

    choice = input("\nPilihan (1/2/3): ").strip()

    if choice == "1":
        num = input(f"Nomor akun (1-{total}): ").strip()
        idx = int(num) - 1
        if not (0 <= idx < total):
            print("[!] Nomor tidak valid")
            return
        await run_accounts(sessions, wallets, [idx])

    elif choice == "2":
        await run_accounts(sessions, wallets, list(range(total)))

    elif choice == "3":
        start = input(f"Mulai dari akun nomor (1-{total}): ").strip()
        idx = int(start) - 1
        if not (0 <= idx < total):
            print("[!] Nomor tidak valid")
            return
        await run_accounts(sessions, wallets, list(range(idx, total)))

    else:
        print("[!] Pilihan tidak valid")

if __name__ == "__main__":
    asyncio.run(main())
