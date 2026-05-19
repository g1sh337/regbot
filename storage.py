import json
import os
import gspread
from google.oauth2.service_account import Credentials

SHEET_ID = os.environ.get("GOOGLE_SHEET_ID")
GOOGLE_CREDENTIALS = os.environ.get("GOOGLE_CREDENTIALS")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

_client = None
_sheet = None


def _get_sheet():
    global _client, _sheet
    if _sheet is not None:
        return _sheet
    try:
        creds_dict = json.loads(GOOGLE_CREDENTIALS)
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        _client = gspread.authorize(creds)
        spreadsheet = _client.open_by_key(SHEET_ID)

        # Получаем или создаём лист data
        try:
            _sheet = spreadsheet.worksheet("data")
        except gspread.WorksheetNotFound:
            _sheet = spreadsheet.add_worksheet(title="data", rows=10, cols=2)
            _sheet.update([["key", "value"]], "A1:B1")

        return _sheet
    except Exception as e:
        print(f"[SHEETS] connect error: {e}")
        return None


def load_data() -> dict:
    sheet = _get_sheet()
    if not sheet:
        return _load_local()

    try:
        records = sheet.get_all_records()
        for row in records:
            if row.get("key") == "data":
                return json.loads(row["value"])
        return {"days": {}, "members": [], "bot_messages": {}}
    except Exception as e:
        print(f"[SHEETS] load error: {e}")
        return _load_local()


def save_data(data: dict):
    sheet = _get_sheet()
    if not sheet:
        _save_local(data)
        return

    try:
        value = json.dumps(data, ensure_ascii=False)
        records = sheet.get_all_records()
        for i, row in enumerate(records, start=2):
            if row.get("key") == "data":
                sheet.update([[value]], f"B{i}")
                return
        # Если строки нет — добавляем
        sheet.append_row(["data", value])
    except Exception as e:
        print(f"[SHEETS] save error: {e}")
        _save_local(data)


# Fallback на локальный файл
LOCAL_FILE = "data.json"

def _load_local() -> dict:
    if not os.path.exists(LOCAL_FILE):
        return {"days": {}, "members": [], "bot_messages": {}}
    try:
        with open(LOCAL_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"days": {}, "members": [], "bot_messages": {}}

def _save_local(data: dict):
    with open(LOCAL_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)