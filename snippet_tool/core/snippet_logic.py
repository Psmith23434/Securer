# COMPILE_TO_PYD
"""
Snippet storage and management logic.
Compile to .pyd before distribution.

Snippets are stored in a local SQLite database.
This module exposes a clean API used by the GUI.
"""
import sqlite3
import json
from pathlib import Path
from datetime import datetime
from typing import Optional

DB_PATH = Path.home() / ".snippet_tool" / "snippets.db"


def _get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    _init_schema(conn)
    return conn


def _init_schema(conn: sqlite3.Connection):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS snippets (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            title     TEXT NOT NULL DEFAULT '',
            content   TEXT NOT NULL DEFAULT '',
            tags      TEXT NOT NULL DEFAULT '[]',
            created   TEXT NOT NULL,
            updated   TEXT NOT NULL
        )
    """)
    conn.commit()


def get_all_snippets() -> list[dict]:
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM snippets ORDER BY updated DESC"
        ).fetchall()
        return [_row_to_dict(r) for r in rows]


def get_snippet(snippet_id: int) -> Optional[dict]:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM snippets WHERE id = ?", (snippet_id,)
        ).fetchone()
        return _row_to_dict(row) if row else None


def create_snippet(title: str, content: str, tags: list[str] = None) -> dict:
    now = datetime.utcnow().isoformat()
    tags_json = json.dumps(tags or [])
    with _get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO snippets (title, content, tags, created, updated) VALUES (?,?,?,?,?)",
            (title, content, tags_json, now, now)
        )
        conn.commit()
        return get_snippet(cur.lastrowid)


def update_snippet(snippet_id: int, title: str = None,
                   content: str = None, tags: list[str] = None) -> Optional[dict]:
    snippet = get_snippet(snippet_id)
    if not snippet:
        return None
    new_title = title if title is not None else snippet["title"]
    new_content = content if content is not None else snippet["content"]
    new_tags = json.dumps(tags if tags is not None else snippet["tags"])
    now = datetime.utcnow().isoformat()
    with _get_conn() as conn:
        conn.execute(
            "UPDATE snippets SET title=?, content=?, tags=?, updated=? WHERE id=?",
            (new_title, new_content, new_tags, now, snippet_id)
        )
        conn.commit()
    return get_snippet(snippet_id)


def delete_snippet(snippet_id: int) -> bool:
    with _get_conn() as conn:
        cur = conn.execute("DELETE FROM snippets WHERE id=?", (snippet_id,))
        conn.commit()
        return cur.rowcount > 0


def search_snippets(query: str) -> list[dict]:
    q = f"%{query}%"
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM snippets WHERE title LIKE ? OR content LIKE ? ORDER BY updated DESC",
            (q, q)
        ).fetchall()
        return [_row_to_dict(r) for r in rows]


def _row_to_dict(row) -> dict:
    d = dict(row)
    try:
        d["tags"] = json.loads(d.get("tags", "[]"))
    except (json.JSONDecodeError, TypeError):
        d["tags"] = []
    return d
