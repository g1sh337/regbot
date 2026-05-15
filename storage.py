import json
import os

DATA_FILE = "data.json"


def load_data() -> dict:
    """Загружает данные из файла."""
    if not os.path.exists(DATA_FILE):
        return {"days": {}, "members": []}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {"days": {}, "members": []}


def save_data(data: dict):
    """Сохраняет данные в файл."""
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
