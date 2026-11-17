"""Saved history of everything the user generates (profiles, searches, interviews...).

Two backends with the same interface:
- FileHistory:    one JSON file per entry in a folder on the user's own computer
- SessionHistory: kept in the browser session only (used when the app is hosted, so one
                  visitor's resume is never written to a shared server disk)
Both support export/import of a single JSON backup file.
"""
import json
import os
import uuid
from datetime import datetime

KINDS = {
    "profile": "👤 Profile",
    "jobs": "💼 Job search",
    "salary": "💰 Salary benchmark",
    "resume": "📄 Tailored resume",
    "cover": "✉️ Cover letter",
    "guide": "📘 Interview prep guide",
    "interview": "🎤 Mock interview",
    "fit": "🎯 Fit score",
    "career": "🧭 Career plan",
    "branding": "🔗 LinkedIn & portal profile",
}


def _new_entry(kind: str, title: str, data, entry_id: str | None = None) -> dict:
    return {
        "id": entry_id or uuid.uuid4().hex[:12],
        "kind": kind,
        "title": title[:120],
        "ts": datetime.now().isoformat(timespec="seconds"),
        "data": data,
    }


class FileHistory:
    mode = "local"

    def __init__(self, folder: str):
        self.folder = folder
        os.makedirs(folder, exist_ok=True)

    def _path(self, entry_id: str) -> str:
        safe = "".join(c for c in entry_id if c.isalnum())
        return os.path.join(self.folder, f"{safe}.json")

    def save(self, kind, title, data, entry_id=None) -> dict:
        e = _new_entry(kind, title, data, entry_id)
        with open(self._path(e["id"]), "w", encoding="utf-8") as f:
            json.dump(e, f, ensure_ascii=False, indent=1)
        return e

    def list(self) -> list[dict]:
        out = []
        for name in os.listdir(self.folder):
            if name.endswith(".json"):
                try:
                    with open(os.path.join(self.folder, name), encoding="utf-8") as f:
                        out.append(json.load(f))
                except Exception:
                    continue  # skip corrupted files
        return sorted(out, key=lambda e: e.get("ts", ""), reverse=True)

    def delete(self, entry_id: str):
        try:
            os.remove(self._path(entry_id))
        except FileNotFoundError:
            pass

    def clear(self):
        for e in self.list():
            self.delete(e["id"])

    def export_bytes(self) -> bytes:
        return json.dumps(self.list(), ensure_ascii=False, indent=1).encode("utf-8")

    def import_bytes(self, raw: bytes) -> int:
        items = json.loads(raw.decode("utf-8"))
        n = 0
        for e in items if isinstance(items, list) else []:
            if isinstance(e, dict) and e.get("kind") in KINDS and "data" in e:
                with open(self._path(e.get("id") or uuid.uuid4().hex[:12]), "w", encoding="utf-8") as f:
                    json.dump(e, f, ensure_ascii=False, indent=1)
                n += 1
        return n


class SessionHistory:
    mode = "session"

    def __init__(self, store: list):
        self.store = store  # a list living in st.session_state

    def save(self, kind, title, data, entry_id=None) -> dict:
        e = _new_entry(kind, title, data, entry_id)
        self.store[:] = [x for x in self.store if x["id"] != e["id"]] + [e]
        return e

    def list(self) -> list[dict]:
        return sorted(self.store, key=lambda e: e.get("ts", ""), reverse=True)

    def delete(self, entry_id: str):
        self.store[:] = [x for x in self.store if x["id"] != entry_id]

    def clear(self):
        self.store.clear()

    def export_bytes(self) -> bytes:
        return json.dumps(self.list(), ensure_ascii=False, indent=1).encode("utf-8")

    def import_bytes(self, raw: bytes) -> int:
        items = json.loads(raw.decode("utf-8"))
        n = 0
        for e in items if isinstance(items, list) else []:
            if isinstance(e, dict) and e.get("kind") in KINDS and "data" in e:
                self.store[:] = [x for x in self.store if x["id"] != e.get("id")] + [e]
                n += 1
        return n
