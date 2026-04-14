"""SQLite-based conversation history store."""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class Conversation:
    id: str
    title: str
    provider: str
    model: str
    created_at: str
    updated_at: str


@dataclass
class Message:
    id: str
    conversation_id: str
    role: str
    content: str | None
    tool_calls: str | None  # JSON
    created_at: str


class HistoryStore:
    """SQLite-backed conversation history."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    title TEXT,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT REFERENCES conversations(id) ON DELETE CASCADE,
                    role TEXT NOT NULL,
                    content TEXT,
                    tool_calls TEXT,
                    tool_call_id TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                );
            """)

    def create_conversation(self, provider: str, model: str, title: str = "New Chat") -> str:
        conv_id = str(uuid.uuid4())
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO conversations (id, title, provider, model) VALUES (?, ?, ?, ?)",
                (conv_id, title, provider, model),
            )
        return conv_id

    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str | None = None,
        tool_calls: list[dict] | None = None,
        tool_call_id: str | None = None,
    ) -> str:
        msg_id = str(uuid.uuid4())
        tool_calls_json = json.dumps(tool_calls) if tool_calls else None
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO messages (id, conversation_id, role, content, tool_calls, tool_call_id) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (msg_id, conversation_id, role, content, tool_calls_json, tool_call_id),
            )
            conn.execute(
                "UPDATE conversations SET updated_at = datetime('now') WHERE id = ?",
                (conversation_id,),
            )
        return msg_id

    def list_conversations(self, limit: int = 50) -> list[Conversation]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT id, title, provider, model, created_at, updated_at "
                "FROM conversations ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [Conversation(*row) for row in rows]

    def get_messages(self, conversation_id: str) -> list[Message]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT id, conversation_id, role, content, tool_calls, created_at "
                "FROM messages WHERE conversation_id = ? ORDER BY created_at",
                (conversation_id,),
            ).fetchall()
        return [Message(*row) for row in rows]

    def delete_conversation(self, conversation_id: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
            conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
