import json
import os
import urllib.request
import urllib.error

JSONBIN_BIN_ID = os.environ.get("JSONBIN_BIN_ID")
JSONBIN_API_KEY = os.environ.get("JSONBIN_API_KEY")

# Fallback на локальный файл если переменные не заданы
LOCAL_FILE = "data.json"


def _use_jsonbin() -> bool:
    return bool(JSONBIN_BIN_ID and JSONBIN_API_KEY)


def load_data() -> dict:
    if _use_jsonbin():
        try:
            url = f"https://api.jsonbin.io/v3/b/{JSONBIN_BIN_ID}/latest"
            req = urllib.request.Request(url, headers={
                "X-Master-Key": JSONBIN_API_KEY,
                "X-Bin-Meta": "false",
            })
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode())
        except Exception as e:
            print(f"[JSONBIN] load error: {e}")
            return {"days": {}, "members": [], "bot_messages": {}}
    else:
        if not os.path.exists(LOCAL_FILE):
            return {"days": {}, "members": [], "bot_messages": {}}
        try:
            with open(LOCAL_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {"days": {}, "members": [], "bot_messages": {}}


def save_data(data: dict):
    if _use_jsonbin():
        try:
            url = f"https://api.jsonbin.io/v3/b/{JSONBIN_BIN_ID}"
            body = json.dumps(data, ensure_ascii=False).encode()
            req = urllib.request.Request(url, data=body, method="PUT", headers={
                "Content-Type": "application/json",
                "X-Master-Key": JSONBIN_API_KEY,
            })
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp.read()
        except Exception as e:
            print(f"[JSONBIN] save error: {e}")
    else:
        with open(LOCAL_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)