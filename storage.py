import json
import os
 
DATA_FILE = "data.json"
 
 
def load_data() -> dict:
    if not os.path.exists(DATA_FILE):
        return {"days": {}, "members": [], "bot_messages": {}}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {"days": {}, "members": [], "bot_messages": {}}
 
 
def save_data(data: dict):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)