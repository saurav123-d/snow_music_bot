from datetime import datetime
from bot_config import MONGO_URI
import sqlite3
import json
from pathlib import Path

try:
    from pymongo import MongoClient
except Exception:
    MongoClient = None

class Storage:
    def __init__(self, uri: str = None):
        use_uri = uri or MONGO_URI
        self.mongo_enabled = False
        self.sqlite_enabled = False
        self.enabled = False
        self.client = None
        self.db = None
        self.sqlite_conn = None
        self.sqlite_path = str(Path(__file__).parent / "biomaibot.db")
        if self.enabled:
            try:
                self.client = MongoClient(use_uri)
                self.db = None
                if self.client:
                    try:
                        self.db = self.client.get_default_database()
                    except Exception:
                        self.db = self.client.get_database("biomaibot")
                self.mongo_enabled = True if self.db is not None else False
            except Exception:
                self.client = None
                self.db = None
                self.mongo_enabled = False
        if not self.mongo_enabled:
            try:
                self.sqlite_conn = sqlite3.connect(self.sqlite_path, check_same_thread=False)
                cur = self.sqlite_conn.cursor()
                cur.execute("CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, type TEXT, chat_id INTEGER, user_id INTEGER, data TEXT, ts TEXT)")
                cur.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
                self.sqlite_conn.commit()
                self.sqlite_enabled = True
            except Exception:
                self.sqlite_conn = None
                self.sqlite_enabled = False
        self.enabled = self.mongo_enabled or self.sqlite_enabled
    
    def save_event(self, event_type: str, payload: dict):
        if not self.enabled:
            return
        chat_id = payload.get("chat_id")
        user_id = payload.get("user_id")
        ts = datetime.utcnow().isoformat()
        if self.mongo_enabled and self.db is not None:
            try:
                doc = {"type": event_type, "data": payload, "ts": datetime.utcnow()}
                self.db.events.insert_one(doc)
                return
            except Exception:
                pass
        if self.sqlite_enabled and self.sqlite_conn is not None:
            try:
                cur = self.sqlite_conn.cursor()
                cur.execute(
                    "INSERT INTO events (type, chat_id, user_id, data, ts) VALUES (?, ?, ?, ?, ?)",
                    (event_type, chat_id, user_id, json.dumps(payload, ensure_ascii=False), ts)
                )
                self.sqlite_conn.commit()
            except Exception:
                pass

    def load_state(self) -> dict:
        if not self.enabled:
            return {}
        if self.mongo_enabled and self.db is not None:
            try:
                doc = self.db.settings.find_one({"_id": "global"}) or {}
                doc.pop("_id", None)
                return doc
            except Exception:
                pass
        if self.sqlite_enabled and self.sqlite_conn is not None:
            try:
                cur = self.sqlite_conn.cursor()
                cur.execute("SELECT value FROM settings WHERE key=?", ("global",))
                row = cur.fetchone()
                if not row or not row[0]:
                    return {}
                return json.loads(row[0])
            except Exception:
                return {}
        return {}

    def update_state(self, fields: dict):
        if not self.enabled:
            return
        if self.mongo_enabled and self.db is not None:
            try:
                self.db.settings.update_one({"_id": "global"}, {"$set": fields}, upsert=True)
                return
            except Exception:
                pass
        if self.sqlite_enabled and self.sqlite_conn is not None:
            try:
                current = self.load_state()
                current.update(fields or {})
                cur = self.sqlite_conn.cursor()
                cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", ("global", json.dumps(current, ensure_ascii=False)))
                self.sqlite_conn.commit()
            except Exception:
                pass

    def count_distinct_chats(self) -> int:
        if not self.enabled:
            return 0
        if self.mongo_enabled and self.db is not None:
            try:
                return len(self.db.events.distinct("data.chat_id"))
            except Exception:
                pass
        if self.sqlite_enabled and self.sqlite_conn is not None:
            try:
                cur = self.sqlite_conn.cursor()
                cur.execute("SELECT COUNT(DISTINCT chat_id) FROM events")
                row = cur.fetchone()
                return int(row[0] or 0)
            except Exception:
                return 0
        return 0

    def count_distinct_users(self) -> int:
        if not self.enabled:
            return 0
        if self.mongo_enabled and self.db is not None:
            try:
                return len(self.db.events.distinct("data.user_id"))
            except Exception:
                pass
        if self.sqlite_enabled and self.sqlite_conn is not None:
            try:
                cur = self.sqlite_conn.cursor()
                cur.execute("SELECT COUNT(DISTINCT user_id) FROM events")
                row = cur.fetchone()
                return int(row[0] or 0)
            except Exception:
                return 0
        return 0

    def add_group(self, chat_id: int, title: str = None):
        if not self.enabled:
            return
        if self.mongo_enabled and self.db is not None:
            try:
                update = {"$addToSet": {"groups": chat_id}}
                if title:
                    update["$set"] = {f"group_titles.{chat_id}": title}
                self.db.settings.update_one({"_id": "global"}, update, upsert=True)
                return
            except Exception:
                pass
        if self.sqlite_enabled and self.sqlite_conn is not None:
            try:
                state = self.load_state()
                groups = state.get("groups") or []
                if chat_id not in groups:
                    groups.append(chat_id)
                if title:
                    titles = state.get("group_titles") or {}
                    titles[str(chat_id)] = title
                    state["group_titles"] = titles
                state["groups"] = groups
                self.update_state(state)
            except Exception:
                pass

    def count_groups(self) -> int:
        if not self.enabled:
            return 0
        if self.mongo_enabled and self.db is not None:
            try:
                doc = self.db.settings.find_one({"_id": "global"}, {"groups": 1}) or {}
                groups = doc.get("groups") or []
                if isinstance(groups, list):
                    return len(groups)
                return 0
            except Exception:
                return 0
        if self.sqlite_enabled and self.sqlite_conn is not None:
            try:
                state = self.load_state()
                groups = state.get("groups") or []
                return len(groups) if isinstance(groups, list) else 0
            except Exception:
                return 0
        return 0
