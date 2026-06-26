"""
WormCup Snipe Bot — file terpisah dari wormcup.py
Semua fungsi diambil langsung dari wormcup__2_.py, ga ada yang dikarang sendiri.
Logic: polling tiap 10 detik, begitu match baru muncul langsung predict semua akun.
"""

import asyncio
import json
import logging
import os
import random
import time
import urllib.parse
from datetime import datetime, timezone, timedelta
from urllib.parse import unquote

import requests
from pyrogram import Client
from pyrogram.raw.functions.messages import RequestWebView

logging.getLogger("pyrogram").setLevel(logging.ERROR)

# ===================== CONFIG =====================
BOT_USERNAME  = "wormcupbot"
START_PARAM   = "PWJY9DP"
SESSIONS_FILE = "sessions.txt"
API_BASE      = "https://api.worm.wtf/api"
WC_BASE       = "https://wc.worm.wtf/api"
POLL_INTERVAL = 10

HEADERS_COMMON = {
    "Origin":     "https://wormcup.vercel.app",
    "Referer":    "https://wormcup.vercel.app/",
    "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
}

TOKEN_DIR = "tokens"
os.makedirs(TOKEN_DIR, exist_ok=True)

SCORES_FILE  = "snipe_scores.txt"
_score_cache = {}
BOOST_MAP    = {100: 2, 300: 3, 500: 5, 1000: 10}

def load_sessions():
    if not os.path.exists(SESSIONS_FILE):
        return []
    with open(SESSIONS_FILE) as f:
        return [line.strip() for line in f if line.strip()]

SESSIONS = load_sessions()

def load_snipe_scores():
    """
    Baca snipe_scores.txt, format tiap baris: home_score-away_score,jersey
    Contoh:
        2-1,9
        1-0,7
        3-2,11
    Return list of (home_score, away_score, jersey)
    """
    scores = []
    if not os.path.exists(SCORES_FILE):
        print(f"[!] {SCORES_FILE} ga ketemu, pakai random.")
        return scores
    with open(SCORES_FILE) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                skor, jersey = line.split(",")
                hs, as_ = map(int, skor.split("-"))
                scores.append((hs, as_, int(jersey)))
            except Exception:
                print(f"[!] Format salah di baris: '{line}', di-skip.")
    return scores


# ===================== PREDICT LOGIC (dari wormcup.py) =====================
def score_to_outcome(hs, as_):
    if hs > as_:   return "home"
    elif as_ > hs: return "away"
    else:          return "draw"

def match_open(m):
    if m.get("status") != "UPCOMING":
        return False
    return get_predict_tier(m) is not None

def get_predict_tier(m, mode="EXACT_SCORE"):
    for t in m.get("tiers", []) or []:
        if t.get("mode") == mode and t.get("status") == "OPEN":
            return t
    return None

def get_all_open_tiers(m):
    return [t for t in (m.get("tiers", []) or []) if t.get("status") == "OPEN"]

_debug_jersey_printed = False
def debug_jersey_error(m, tier, res):
    global _debug_jersey_printed
    if not _debug_jersey_printed and isinstance(res, dict) and res.get("error", {}).get("slug") == "scorer_jersey_required":
        print(f"\n[DEBUG] tier mentah yang kena scorer_jersey_required ({m['home']['code']} vs {m['away']['code']}):")
        print(json.dumps(tier, indent=2, default=str))
        _debug_jersey_printed = True


# ===================== INIT DATA (dari wormcup.py) =====================
async def get_init_data(client: Client) -> str:
    peer   = await client.resolve_peer(BOT_USERNAME)
    result = await client.invoke(
        RequestWebView(peer=peer, bot=peer, platform="android", url="https://wormcup.vercel.app/")
    )
    url      = result.url
    fragment = url.split("#")[1] if "#" in url else url.split("?")[1]
    params   = urllib.parse.parse_qs(fragment)
    raw      = params.get("tgWebAppData", [None])[0]
    return urllib.parse.unquote(raw)


# ===================== TOKEN STORAGE (dari wormcup.py) =====================
def token_path(user_id):
    return os.path.join(TOKEN_DIR, f"{user_id}.json")

def load_tokens(user_id):
    p = token_path(user_id)
    return json.load(open(p)) if os.path.exists(p) else None

def save_tokens(user_id, access_token, refresh_token):
    with open(token_path(user_id), "w") as f:
        json.dump({"access_token": access_token, "refresh_token": refresh_token}, f)

def is_token_valid(access_token):
    try:
        import base64
        b64 = access_token.split(".")[1]
        b64 += "=" * (-len(b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(b64))
        return payload["exp"] > time.time() + 60
    except Exception:
        return False


# ===================== SIGN-IN FLOW (dari wormcup.py) =====================
def login_with_init_data(init_data):
    headers_tma = {**HEADERS_COMMON, "Authorization": f"tma {init_data}"}

    me               = requests.get(f"{WC_BASE}/users/me/", headers=headers_tma)
    me.raise_for_status()
    address          = me.json()["data"]["address"]
    telegram_user_id = me.json()["data"]["telegram_user_id"]

    si = requests.get(f"{API_BASE}/sign-in/", params={"address": address, "network_type": 2}, headers=headers_tma)
    si.raise_for_status()
    nonce = si.json()["result"]["data"]["nonce"]

    issued_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + f"{datetime.now().microsecond // 1000:03d}Z"
    message = (
        f"www.worm.wtf wants you to sign in with your Solana account:\n{address}\n\n"
        f"Sign in with Solana to the app.\n\n"
        f"URI: https://www.worm.wtf\nVersion: 1\nChain ID: 1\nNonce: {nonce}\nIssued At: {issued_at}"
    )

    sign = requests.post(f"{WC_BASE}/signing/sign/", headers=headers_tma,
                         json={"kind": "worm_auth_message", "payload": message})
    sign.raise_for_status()
    signature = sign.json()["data"]["signed_payload"]

    final = requests.post(f"{API_BASE}/sign-in/", headers=HEADERS_COMMON,
                          json={"message": message, "signature": signature,
                                "address": address, "nonce": nonce, "invitation_code": START_PARAM})
    final.raise_for_status()
    data          = final.json()["result"]["data"]
    access_token  = data["access_token"]
    refresh_token = data["refresh_token"]
    save_tokens(str(telegram_user_id), access_token, refresh_token)

    requests.post(f"{API_BASE}/social/telegram/auth/miniapp/",
                  headers={**HEADERS_COMMON, "Authorization": f"Bearer {access_token}"},
                  json={"init_data": init_data})

    return access_token, telegram_user_id


# ===================== API HELPERS (dari wormcup.py) =====================
def ah(token):
    return {**HEADERS_COMMON, "Authorization": f"Bearer {token}"}

def get_matches(token):
    r = requests.get(f"{API_BASE}/worldcup/matches/", params={"limit": 20, "offset": 0}, headers=ah(token))
    r.raise_for_status()
    return r.json()["result"]["data"]

def predict(token, condition_id, home_score, away_score):
    r = requests.post(f"{API_BASE}/worldcup/predictions/",
                      headers=ah(token),
                      json={"condition_id": condition_id, "home_score": home_score,
                            "away_score": away_score})
    return r.json()

def predict_jackpot(token, condition_id, home_score, away_score, scorer_jersey):
    r = requests.post(f"{API_BASE}/worldcup/predictions/",
                      headers=ah(token),
                      json={"condition_id": condition_id, "home_score": home_score,
                            "away_score": away_score, "scorer_jersey": scorer_jersey})
    return r.json()

def predict_winner(token, condition_id, outcome):
    r = requests.post(f"{API_BASE}/worldcup/predictions/",
                      headers=ah(token),
                      json={"condition_id": condition_id, "outcome": outcome})
    return r.json()


# ===================== GET TOKEN (dari wormcup.py) =====================
async def get_token(session_string, idx, total):
    client = Client(name=f"snipe{idx}", session_string=session_string, in_memory=True, no_updates=True)
    await client.start()
    init_data = await get_init_data(client)
    await client.stop()

    user_part = unquote(init_data.split("user=")[1].split("&")[0])
    user_id   = str(json.loads(user_part)["id"])
    tag       = f"[Akun {idx}/{total} | {user_id}]"

    saved = load_tokens(user_id)
    if saved and is_token_valid(saved["access_token"]):
        return saved["access_token"], user_id, tag, init_data
    else:
        access_token, _ = login_with_init_data(init_data)
        print(f"{tag} login baru")
        return access_token, user_id, tag, init_data


# ===================== ATHLETE/JERSEY LOGIC =====================
def get_scorer_jersey_from_athletes(athletes, home_team, away_team, home_score, away_score):
    """
    Ambil jersey dari pemain penyerang (F).
    Prefer tim yang unggul di skor, tapi boleh dari tim lain kalau kurang.
    Hs > As → prefer home, fallback away
    As > Hs → prefer away, fallback home
    Hs = As → prefer home
    """
    # Tentuin tim yang unggul (prefer home kalau draw)
    if home_score >= away_score:
        prefer_team = home_team
        fallback_team = away_team
    else:
        prefer_team = away_team
        fallback_team = home_team
    
    # Filter athletes: prefer team + position F (forward)
    forwards_prefer = [a for a in athletes if a.get("team") == prefer_team and a.get("position") == "F"]
    
    # Kalau prefer team punya forward, ambil dari situ
    if forwards_prefer:
        # Ambil 4 forward pertama atau yang ada
        selected = forwards_prefer[:4] if len(forwards_prefer) >= 4 else forwards_prefer
        jersey = random.choice(selected)["jersey"]
        return jersey
    
    # Fallback ke team lain
    forwards_fallback = [a for a in athletes if a.get("team") == fallback_team and a.get("position") == "F"]
    if forwards_fallback:
        selected = forwards_fallback[:4] if len(forwards_fallback) >= 4 else forwards_fallback
        jersey = random.choice(selected)["jersey"]
        return jersey
    
    # Kalau masih ga ada, random 1-99
    return random.randint(1, 99)
async def do_snipe(match, tokens_per_acc, scores_queue):
    home, away = match["home"]["code"], match["away"]["code"]
    tiers      = get_all_open_tiers(match)
    if not tiers:
        return

    # Ambil skor dari queue, kalau habis pakai random
    if scores_queue:
        hs, as_, jersey_fixed = scores_queue.pop(0)
        jersey = jersey_fixed
        print(f"  Skor dari file: {hs}-{as_} jersey={jersey}")
    else:
        _total_w = [8, 20, 25, 22, 12, 7, 4, 2]
        total    = random.choices(range(8), weights=_total_w, k=1)[0]
        hs       = random.randint(0, total)
        as_      = total - hs
        
        # Ambil jersey dari athletes (tim pemenang + forward)
        athletes = match.get("athletes", [])
        home_code = match["home"]["code"]
        away_code = match["away"]["code"]
        jersey = get_scorer_jersey_from_athletes(athletes, home_code, away_code, hs, as_)
        print(f"  Skor random: {hs}-{as_} jersey={jersey}")

    outcome = score_to_outcome(hs, as_)

    try:
        ko_utc = datetime.fromisoformat(match["kickoff"].replace("Z", "+00:00"))
        ko_wib = (ko_utc + timedelta(hours=7)).strftime("%d/%m %H:%M WIB")
    except Exception:
        ko_wib = match.get("kickoff", "?")

    print(f"\n🎯 SNIPE: {home} vs {away} | {ko_wib} | predict {hs}-{as_}")

    for tag, token in tokens_per_acc:
        for t in tiers:
            if t.get("my_prediction") is not None:
                continue
            tier_name = t.get("tier", t.get("mode", ""))
            cid       = t["condition_id"]
            if tier_name == "JACKPOT":
                res = predict_jackpot(token, cid, hs, as_, jersey)
                debug_jersey_error(match, t, res)
                print(f"  {tag} [JACKPOT] {home} {hs}-{as_} {away} jersey={jersey} -> {'OK' if res.get('success') else res}")
            elif tier_name == "WINNER":
                res = predict_winner(token, cid, outcome)
                print(f"  {tag} [WINNER] {home} {hs}-{as_} {away} outcome={outcome} -> {'OK' if res.get('success') else res}")
            else:
                res = predict(token, cid, hs, as_)
                print(f"  {tag} [{tier_name}] {home} {hs}-{as_} {away} -> {'OK' if res.get('success') else res}")


# ===================== POLLING =====================
async def polling_loop(tokens_per_acc, scores_queue):
    poll_token = tokens_per_acc[0][1]
    seen_ids   = set()

    print("📋 Snapshot match yang udah ada (di-skip)...")
    try:
        for m in get_matches(poll_token):
            seen_ids.add(m["match_id"])
            print(f"  skip: {m['home']['code']} vs {m['away']['code']}")
    except Exception as e:
        print(f"  [!] Gagal snapshot: {e}")

    print(f"\n🔄 Polling tiap {POLL_INTERVAL} detik... (Ctrl+C buat stop)\n")

    while True:
        try:
            matches = get_matches(poll_token)
            for m in matches:
                mid = m["match_id"]
                if mid in seen_ids:
                    continue
                seen_ids.add(mid)
                print(f"\n🆕 Match baru: {m['home']['code']} vs {m['away']['code']}")
                await do_snipe(m, tokens_per_acc, scores_queue)

            now_wib = (datetime.now(timezone.utc) + timedelta(hours=7)).strftime("%H:%M:%S")
            print(f"[{now_wib}] polling...", end="\r")
        except Exception as e:
            print(f"\n[!] Error polling: {e}")

        await asyncio.sleep(POLL_INTERVAL)


# ===================== MAIN =====================
async def main():
    if not SESSIONS:
        print("sessions.txt kosong.")
        return

    scores_queue = load_snipe_scores()
    if scores_queue:
        print(f"📋 {len(scores_queue)} skor dimuat dari {SCORES_FILE}:")
        for i, (hs, as_, j) in enumerate(scores_queue, 1):
            print(f"  Match {i}: {hs}-{as_} jersey={j}")
    else:
        print("⚠️  Ga ada skor di file, semua match bakal pakai random.")

    total          = len(SESSIONS)
    tokens_per_acc = []
    print(f"\n⏳ Login {total} akun...")
    for idx, s in enumerate(SESSIONS, 1):
        try:
            at, uid, tag, _ = await get_token(s, idx, total)
            tokens_per_acc.append((tag, at))
            print(f"  {tag} ready")
        except Exception as e:
            print(f"  [Akun {idx}] gagal: {e}")

    if not tokens_per_acc:
        print("Semua akun gagal login.")
        return

    print(f"\n✅ {len(tokens_per_acc)} akun siap.")
    await polling_loop(tokens_per_acc, scores_queue)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[!] Dihentiin.")
