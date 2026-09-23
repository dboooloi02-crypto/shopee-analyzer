"""
license.py — SELEKT 授權管理模組 v4
────────────────────────────────────────────────────────────
密鑰格式: SELEKT-TTTTTTTT-XXXXX-XXXXX-XXXXX-XXXXX  (6 段)
  TTTTTTTT : 8 位 hex，過期 Unix timestamp（00000000 = 永久）
  XXXXX×4  : HMAC-SHA256(secret, install_id:expire_ts) 前 20 hex

v4 變更（開源發佈版）：
  密鑰不再硬編碼於原始碼。改從環境變數 SELEKT_LICENSE_SECRET 讀取。
  - 未設置該變數 → 授權模組自動停用，所有 API 直接放行，
    開源使用者可零配置運行。
  - 需要啟用授權 → export SELEKT_LICENSE_SECRET="<你的密鑰>"
  - 生成密鑰   → python -c "import secrets;print(secrets.token_urlsafe(32))"

v3.2：
  試用期計時基準從 license.json 的 installed_at 欄位改為
  install_id 檔案本身。install_id 檔格式為三行：
    <uuid>
    <installed_at hex>
    <HMAC-SHA256(secret, uuid:ts_hex)>
  任何對 installed_at 的篡改（改值、刪檔）都會導致簽名驗證失敗，
  系統視為 trial_expired。
────────────────────────────────────────────────────────────
"""
import hashlib
import hmac
import json
import os
import time
import uuid
from pathlib import Path

LICENSE_DIR  = Path.home() / ".selekt"
LICENSE_FILE = LICENSE_DIR / "license.json"
TRIAL_DAYS   = 3

ENV_SECRET = "SELEKT_LICENSE_SECRET"

_raw_secret      = os.environ.get(ENV_SECRET)
LICENSE_ENABLED  = bool(_raw_secret)
_SECRET: bytes   = _raw_secret.encode() if _raw_secret else b""


def _require_secret(action: str) -> bytes:
    """授權模組未啟用時，任何需要密鑰的操作都直接報錯，而不是靜默失敗。"""
    if not LICENSE_ENABLED:
        raise RuntimeError(
            f"{action} 需要授權模組已啟用，但環境變數 {ENV_SECRET} 未設置。\n"
            f"  設置方式: export {ENV_SECRET}=\"<你的密鑰>\"\n"
            f"  生成密鑰: python -c \"import secrets;print(secrets.token_urlsafe(32))\""
        )
    return _SECRET


# ── install_id 檔（帶時間戳簽名）────────────────────────────────────────────

def _id_file() -> Path:
    return LICENSE_DIR / "install_id"


def _make_id_record(install_id: str, installed_at: float) -> str:
    ts_hex = format(int(installed_at), '016x')
    sig = hmac.new(_SECRET,
                   f"{install_id}:{ts_hex}".encode(),
                   hashlib.sha256).hexdigest()
    return f"{install_id}\n{ts_hex}\n{sig}"


def _parse_id_record(content: str) -> tuple[str, float | None]:
    """
    回傳 (install_id, installed_at)
    installed_at = None 表示舊格式，需遷移
    若簽名驗證失敗則 raise ValueError
    """
    lines = content.strip().split('\n')
    if len(lines) == 1:
        # 舊格式：純 uuid，無時間戳
        return lines[0].strip(), None
    if len(lines) != 3:
        raise ValueError("install_id 格式錯誤")
    iid, ts_hex, sig = [l.strip() for l in lines]
    expected = hmac.new(_SECRET,
                        f"{iid}:{ts_hex}".encode(),
                        hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        raise ValueError("install_id 簽名驗證失敗，檔案可能遭篡改")
    return iid, float(int(ts_hex, 16))


def _get_or_create_install() -> tuple[str, float]:
    """
    回傳 (install_id, installed_at)
    - 若 install_id 檔不存在：全新安裝，建立帶時間戳的格式
    - 若為舊格式（純uuid）：從 license.json 讀取 installed_at 遷移
    - 若簽名驗證失敗：視為試用到期（返回 installed_at=0 讓外層處理）
    """
    _require_secret("讀取安裝識別碼")
    LICENSE_DIR.mkdir(parents=True, exist_ok=True)
    f = _id_file()

    if not f.exists():
        # 全新安裝
        iid = str(uuid.uuid4())
        now = time.time()
        f.write_text(_make_id_record(iid, now), encoding="utf-8")
        return iid, now

    content = f.read_text(encoding="utf-8")
    try:
        iid, installed_at = _parse_id_record(content)
    except ValueError:
        # 簽名驗證失敗：篡改或檔案損壞，視為試用到期
        iid = content.strip().split('\n')[0].strip()
        return iid, 0.0   # 0.0 → elapsed 極大 → trial_expired

    if installed_at is None:
        # 舊格式遷移：從 license.json 讀取 installed_at
        installed_at = _migrate_installed_at(iid)
        f.write_text(_make_id_record(iid, installed_at), encoding="utf-8")

    return iid, installed_at


def _migrate_installed_at(iid: str) -> float:
    """從舊版 license.json 讀取 installed_at，找不到則視為當前時間一半（保守策略）"""
    if LICENSE_FILE.exists():
        try:
            data = json.loads(LICENSE_FILE.read_text(encoding="utf-8"))
            ts = data.get("installed_at")
            if ts and isinstance(ts, (int, float)) and ts > 0:
                return float(ts)
        except Exception:
            pass
    return time.time() - (TRIAL_DAYS / 2) * 86400


# ── 密鑰 HMAC（生成與驗簽共用）──────────────────────────────────────────────

def _hmac_sig(install_id: str, expire_ts: int) -> str:
    raw = hmac.new(_SECRET,
                   f"{install_id}:{expire_ts}".encode(),
                   hashlib.sha256).hexdigest()
    return "-".join(raw[i:i+5].upper() for i in range(0, 20, 5))


# ── 密鑰生成 ─────────────────────────────────────────────────────────────────

def generate_key(install_id: str, expire_days: int | None = None) -> str:
    """
    生成授權密鑰。需先設置 SELEKT_LICENSE_SECRET。
    expire_days = None → 永久授權（TTTTTTTT = 00000000）
    expire_days = N    → N 天後到期
    """
    _require_secret("生成授權密鑰")
    expire_ts  = 0 if expire_days is None else int(time.time()) + expire_days * 86400
    expire_ts  = expire_ts & 0xFFFFFFFF
    expire_hex = format(expire_ts, '08x').upper()
    sig        = _hmac_sig(install_id, expire_ts)
    return f"SELEKT-{expire_hex}-{sig}"


# ── 密鑰解析與驗簽 ───────────────────────────────────────────────────────────

def _validate_key(key: str, install_id: str) -> tuple[bool, int]:
    parts = key.strip().upper().split('-')

    # v2 格式：6 段
    if len(parts) == 6 and parts[0] == 'SELEKT' and len(parts[1]) == 8:
        try:
            expire_ts = int(parts[1], 16)
        except ValueError:
            return False, 0
        expected_sig = _hmac_sig(install_id, expire_ts)
        ok = key.strip().upper() == f"SELEKT-{parts[1]}-{expected_sig}"
        return ok, expire_ts

    # v1 向後兼容：5 段永久密鑰
    if len(parts) == 5 and parts[0] == 'SELEKT':
        old_raw = hmac.new(_SECRET, install_id.encode(), hashlib.sha256).hexdigest()
        old_sig = "-".join(old_raw[i:i+5].upper() for i in range(0, 20, 5))
        ok = key.strip().upper() == f"SELEKT-{old_sig}"
        return ok, 0

    return False, 0


# ── 授權資料 I/O ─────────────────────────────────────────────────────────────

def _load() -> dict:
    LICENSE_DIR.mkdir(parents=True, exist_ok=True)
    if LICENSE_FILE.exists():
        try:
            return json.loads(LICENSE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    # 初始化（不寫入 installed_at，時間戳由 install_id 檔管理）
    data = {"license_key": None, "licensed": False, "key_expire_ts": None}
    LICENSE_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    return data


def _save(data: dict):
    LICENSE_DIR.mkdir(parents=True, exist_ok=True)
    # 不持久化 installed_at，防止被單獨篡改
    safe = {k: v for k, v in data.items()
            if k in ("license_key", "licensed", "key_expire_ts")}
    LICENSE_FILE.write_text(json.dumps(safe, indent=2, ensure_ascii=False))


# ── 公開 API ─────────────────────────────────────────────────────────────────

def get_status() -> dict:
    """
    回傳授權狀態。
    status 可能值：
      unlicensed      — 授權模組未啟用（未設置 SELEKT_LICENSE_SECRET），全功能放行
      trial           — 試用中
      trial_expired   — 試用到期，需輸入密鑰
      licensed        — 已授權
      key_expired     — 密鑰已到期
    """
    if not LICENSE_ENABLED:
        return {
            "status":               "unlicensed",
            "enabled":              False,
            "install_id":           None,
            "trial_remaining_days": None,
            "expires_at":           None,
            "message":              f"授權模組未啟用（{ENV_SECRET} 未設置），功能不受限",
        }

    install_id, installed_at = _get_or_create_install()
    data = _load()
    now  = time.time()

    # 授權密鑰檢查（優先於試用期判斷）
    key = data.get("license_key")
    if key and data.get("licensed"):
        valid, exp_ts = _validate_key(key, install_id)
        if valid:
            if exp_ts != 0 and now > exp_ts:
                return {"status": "key_expired",
                        "enabled": True,
                        "install_id": install_id,
                        "trial_remaining_days": 0,
                        "expires_at": exp_ts,
                        "message": "授權密鑰已到期，請聯繫管理員更新密鑰"}
            return {"status": "licensed",
                    "enabled": True,
                    "install_id": install_id,
                    "trial_remaining_days": 0,
                    "expires_at": exp_ts if exp_ts else None,
                    "key_expire_ts": exp_ts}

    # 試用期判斷
    if installed_at == 0.0:
        return {"status": "trial_expired",
                "enabled": True,
                "install_id": install_id,
                "trial_remaining_days": 0,
                "expires_at": now,
                "message": "授權檔案驗證失敗，請輸入授權密鑰"}

    elapsed   = (now - installed_at) / 86400
    remaining = max(0.0, TRIAL_DAYS - elapsed)

    if elapsed > TRIAL_DAYS:
        return {"status": "trial_expired",
                "enabled": True,
                "install_id": install_id,
                "trial_remaining_days": 0,
                "expires_at": installed_at + TRIAL_DAYS * 86400,
                "message": f"{TRIAL_DAYS} 天試用期已結束"}

    return {"status": "trial",
            "enabled": True,
            "install_id": install_id,
            "trial_remaining_days": round(remaining, 2),
            "expires_at": installed_at + TRIAL_DAYS * 86400}


def activate(key: str) -> bool:
    if not LICENSE_ENABLED:
        return False
    install_id, _ = _get_or_create_install()
    data = _load()
    valid, exp_ts = _validate_key(key, install_id)
    if not valid:
        return False
    if exp_ts != 0 and time.time() > exp_ts:
        return False
    data.update({"licensed": True, "license_key": key.strip().upper(),
                 "key_expire_ts": exp_ts if exp_ts else None})
    _save(data)
    return True


def is_allowed() -> bool:
    """授權模組停用時一律放行。"""
    if not LICENSE_ENABLED:
        return True
    return get_status()["status"] in ("licensed", "trial")


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 2 and sys.argv[1] == "key":
        iid  = sys.argv[2] if len(sys.argv) > 2 else get_status()["install_id"]
        days = int(sys.argv[3]) if len(sys.argv) > 3 else None
        if not iid:
            print("用法: python license.py key <install_id> [有效天數]")
            sys.exit(1)
        print(generate_key(iid, days))
    else:
        s = get_status()
        print(f"狀態     : {s['status']}  (enabled={s['enabled']})")
        print(f"安裝 ID  : {s.get('install_id') or '—'}")
        print(f"剩餘試用 : {s.get('trial_remaining_days')}")
        print()
        print("用法: python license.py          查看狀態")
        print("      python license.py key <install_id> [天數]   生成密鑰")
