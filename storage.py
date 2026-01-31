import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Tuple

ISO_FMT = "%Y-%m-%dT%H:%M:%S.%fZ"


def utcnow_iso() -> str:
    return datetime.utcnow().strftime(ISO_FMT)


def parse_iso(s: str) -> datetime:
    return datetime.strptime(s, ISO_FMT)


@dataclass(frozen=True)
class PendingChallenge:
    challenged_id: int
    challenger_id: int
    created_at: str  # ISO string


@dataclass(frozen=True)
class ActiveBattle:
    user_a: int
    user_b: int
    accepted_at: str  # ISO string


class DataStore:
    def __init__(self, db_path: str = "bot_state.sqlite3"):
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.db_path)
        con.execute("PRAGMA journal_mode=WAL;")
        con.execute("PRAGMA foreign_keys=ON;")
        return con

    def _init_db(self) -> None:
        con = self._connect()
        try:
            con.execute("""
                CREATE TABLE IF NOT EXISTS points (
                    user_id INTEGER PRIMARY KEY,
                    points  INTEGER NOT NULL
                )
            """)
            con.execute("""
                CREATE TABLE IF NOT EXISTS pending (
                    challenged_id INTEGER PRIMARY KEY,
                    challenger_id INTEGER NOT NULL,
                    created_at    TEXT NOT NULL
                )
            """)
            con.execute("""
                CREATE TABLE IF NOT EXISTS active (
                    battle_id   TEXT PRIMARY KEY,
                    user_a      INTEGER NOT NULL,
                    user_b      INTEGER NOT NULL,
                    accepted_at TEXT NOT NULL
                )
            """)
            con.execute("""
                CREATE TABLE IF NOT EXISTS completed (
                    user_id INTEGER PRIMARY KEY
                )
            """)
            # 🔹 NEW: flags table (for startup image, etc.)
            con.execute("""
                CREATE TABLE IF NOT EXISTS flags (
                    key   TEXT PRIMARY KEY,
                    value INTEGER NOT NULL
                )
            """)
            con.commit()
        finally:
            con.close()

    # ---------- flags ----------
    def get_flag(self, key: str) -> bool:
        con = self._connect()
        try:
            row = con.execute(
                "SELECT value FROM flags WHERE key=?",
                (key,)
            ).fetchone()
            return bool(row[0]) if row else False
        finally:
            con.close()

    def set_flag(self, key: str, value: bool) -> None:
        con = self._connect()
        try:
            con.execute(
                "INSERT OR REPLACE INTO flags(key, value) VALUES(?, ?)",
                (key, int(value))
            )
            con.commit()
        finally:
            con.close()

    # ---------- points ----------
    def get_points(self, user_id: int) -> int:
        con = self._connect()
        try:
            row = con.execute(
                "SELECT points FROM points WHERE user_id=?",
                (user_id,)
            ).fetchone()
            return int(row[0]) if row else 0
        finally:
            con.close()

    def add_points(self, user_id: int, amount: int) -> int:
        con = self._connect()
        try:
            cur = con.execute(
                "SELECT points FROM points WHERE user_id=?",
                (user_id,)
            )
            row = cur.fetchone()
            if row:
                new_val = int(row[0]) + amount
                con.execute(
                    "UPDATE points SET points=? WHERE user_id=?",
                    (new_val, user_id)
                )
            else:
                new_val = amount
                con.execute(
                    "INSERT INTO points(user_id, points) VALUES(?,?)",
                    (user_id, new_val)
                )
            con.commit()
            return new_val
        finally:
            con.close()

    def set_points(self, user_id: int, points: int) -> None:
        con = self._connect()
        try:
            con.execute(
                "INSERT INTO points(user_id, points) VALUES(?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET points=excluded.points",
                (user_id, points),
            )
            con.commit()
        finally:
            con.close()

    def clear_points(self) -> None:
        con = self._connect()
        try:
            con.execute("DELETE FROM points")
            con.commit()
        finally:
            con.close()

    def top_points(self, limit: int = 10) -> List[Tuple[int, int]]:
        con = self._connect()
        try:
            rows = con.execute(
                "SELECT user_id, points FROM points ORDER BY points DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [(int(r[0]), int(r[1])) for r in rows]
        finally:
            con.close()

    # ---------- completed ----------
    def mark_completed(self, user_id: int) -> None:
        con = self._connect()
        try:
            con.execute(
                "INSERT OR IGNORE INTO completed(user_id) VALUES(?)",
                (user_id,)
            )
            con.commit()
        finally:
            con.close()

    def clear_completed(self) -> None:
        con = self._connect()
        try:
            con.execute("DELETE FROM completed")
            con.commit()
        finally:
            con.close()

    def list_completed(self) -> List[int]:
        con = self._connect()
        try:
            rows = con.execute("SELECT user_id FROM completed").fetchall()
            return [int(r[0]) for r in rows]
        finally:
            con.close()

    # ---------- pending ----------
    def add_pending(self, challenged_id: int, challenger_id: int, created_at: Optional[str] = None) -> None:
        con = self._connect()
        try:
            con.execute(
                "INSERT OR REPLACE INTO pending(challenged_id, challenger_id, created_at) VALUES(?,?,?)",
                (challenged_id, challenger_id, created_at or utcnow_iso()),
            )
            con.commit()
        finally:
            con.close()

    def remove_pending(self, challenged_id: int) -> None:
        con = self._connect()
        try:
            con.execute("DELETE FROM pending WHERE challenged_id=?", (challenged_id,))
            con.commit()
        finally:
            con.close()

    def get_pending(self, challenged_id: int) -> Optional[PendingChallenge]:
        con = self._connect()
        try:
            row = con.execute(
                "SELECT challenged_id, challenger_id, created_at FROM pending WHERE challenged_id=?",
                (challenged_id,),
            ).fetchone()
            if not row:
                return None
            return PendingChallenge(int(row[0]), int(row[1]), str(row[2]))
        finally:
            con.close()

    def list_pending(self) -> List[PendingChallenge]:
        con = self._connect()
        try:
            rows = con.execute(
                "SELECT challenged_id, challenger_id, created_at FROM pending ORDER BY created_at ASC"
            ).fetchall()
            return [PendingChallenge(int(r[0]), int(r[1]), str(r[2])) for r in rows]
        finally:
            con.close()

    def clear_pending(self) -> None:
        con = self._connect()
        try:
            con.execute("DELETE FROM pending")
            con.commit()
        finally:
            con.close()

    # ---------- active ----------
    def _battle_id(self, a: int, b: int) -> str:
        x, y = (a, b) if a < b else (b, a)
        return f"{x}:{y}"

    def add_active(self, user_a: int, user_b: int, accepted_at: Optional[str] = None) -> None:
        bid = self._battle_id(user_a, user_b)
        con = self._connect()
        try:
            con.execute(
                "INSERT OR REPLACE INTO active(battle_id, user_a, user_b, accepted_at) VALUES(?,?,?,?)",
                (bid, user_a, user_b, accepted_at or utcnow_iso()),
            )
            con.commit()
        finally:
            con.close()

    def remove_active(self, user_a: int, user_b: int) -> None:
        bid = self._battle_id(user_a, user_b)
        con = self._connect()
        try:
            con.execute("DELETE FROM active WHERE battle_id=?", (bid,))
            con.commit()
        finally:
            con.close()

    def get_active(self, user_a: int, user_b: int) -> Optional[ActiveBattle]:
        bid = self._battle_id(user_a, user_b)
        con = self._connect()
        try:
            row = con.execute(
                "SELECT user_a, user_b, accepted_at FROM active WHERE battle_id=?",
                (bid,),
            ).fetchone()
            if not row:
                return None
            return ActiveBattle(int(row[0]), int(row[1]), str(row[2]))
        finally:
            con.close()

    def list_active(self) -> List[ActiveBattle]:
        con = self._connect()
        try:
            rows = con.execute(
                "SELECT user_a, user_b, accepted_at FROM active ORDER BY accepted_at ASC"
            ).fetchall()
            return [ActiveBattle(int(r[0]), int(r[1]), str(r[2])) for r in rows]
        finally:
            con.close()

    def clear_active(self) -> None:
        con = self._connect()
        try:
            con.execute("DELETE FROM active")
            con.commit()
        finally:
            con.close()