import json
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

# Сколько дней хранится "память" о лайке/скипе.
# После этого срока анкета снова может быть показана в поиске.
SKIP_EXPIRE_DAYS = 7  # скипнул — через 7 дней можно снова увидеть
LIKE_EXPIRE_DAYS = 30  # лайкнул (без взаимности) — через 30 дней снова увидит


# Насколько лет в плюс/минус показывать анкеты при поиске.
# 1 = показывать людей на 1 год младше и на 1 год старше.
AGE_RANGE = 1

def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: str):
        self.path = path
        self.init_db()

    def connect(self):
        conn = sqlite3.connect(self.path, timeout=20)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=10000")
        return conn

    def init_db(self):
        with self.connect() as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL UNIQUE,
                username TEXT,
                name TEXT,
                gender TEXT,
                age INTEGER,
                faculty TEXT,
                dormitory TEXT,
                description TEXT,
                photo_1 TEXT,
                photo_2 TEXT,
                photo_3 TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                profile_completed INTEGER NOT NULL DEFAULT 0,
                banned_until TEXT,
                ban_reason TEXT,
                is_hidden INTEGER NOT NULL DEFAULT 0,
                moderation_note TEXT
            );

            CREATE TABLE IF NOT EXISTS user_states (
                telegram_id INTEGER PRIMARY KEY,
                state TEXT NOT NULL,
                data_json TEXT NOT NULL DEFAULT '{}',
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS likes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_user_id INTEGER NOT NULL,
                to_user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(from_user_id,to_user_id),
                FOREIGN KEY(from_user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(to_user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS skips (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_user_id INTEGER NOT NULL,
                to_user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(from_user_id,to_user_id),
                FOREIGN KEY(from_user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(to_user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reporter_user_id INTEGER NOT NULL,
                reported_user_id INTEGER NOT NULL,
                cause TEXT NOT NULL,
                profile_snapshot TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                admin_comment TEXT,
                created_at TEXT NOT NULL,
                resolved_at TEXT,
                FOREIGN KEY(reporter_user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(reported_user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS ban_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                admin_telegram_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                days INTEGER,
                reason TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS admin_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_telegram_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                target_user_id INTEGER,
                details TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS support_tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                category TEXT NOT NULL,
                message TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                admin_id INTEGER,
                admin_reply TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
            );

            CREATE INDEX IF NOT EXISTS idx_users_completed ON users(profile_completed);
            CREATE INDEX IF NOT EXISTS idx_users_gender ON users(gender);
            CREATE INDEX IF NOT EXISTS idx_reports_status ON reports(status);
            CREATE INDEX IF NOT EXISTS idx_tickets_status ON support_tickets(status);
            CREATE INDEX IF NOT EXISTS idx_bans_user ON ban_history(user_id);
            """)

    # Users
    def upsert_telegram_user(self, telegram_id: int, username: str | None):
        n = now_utc()
        with self.connect() as c:
            c.execute("""
                INSERT INTO users(telegram_id,username,created_at,updated_at)
                VALUES(?,?,?,?)
                ON CONFLICT(telegram_id) DO UPDATE SET
                    username=excluded.username,
                    updated_at=excluded.updated_at
            """, (telegram_id, username, n, n))

    def get_user(self, telegram_id: int):
        with self.connect() as c:
            return c.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,)).fetchone()

    def get_user_by_id(self, user_id: int):
        with self.connect() as c:
            return c.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()

    def save_profile(self, telegram_id: int, data: dict[str, Any]):
        n = now_utc()
        with self.connect() as c:
            c.execute("""
                INSERT INTO users(
                    telegram_id,username,name,gender,age,faculty,dormitory,
                    description,photo_1,photo_2,photo_3,created_at,updated_at,profile_completed
                )
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,1)
                ON CONFLICT(telegram_id) DO UPDATE SET
                    username=excluded.username,
                    name=excluded.name,
                    gender=excluded.gender,
                    age=excluded.age,
                    faculty=excluded.faculty,
                    dormitory=excluded.dormitory,
                    description=excluded.description,
                    photo_1=excluded.photo_1,
                    photo_2=excluded.photo_2,
                    photo_3=excluded.photo_3,
                    updated_at=excluded.updated_at,
                    profile_completed=1
            """, (
                telegram_id, data.get("username"), data["name"], data["gender"],
                data["age"], data["faculty"], data["dormitory"], data["description"],
                data["photo_1"], data.get("photo_2"), data.get("photo_3"), n, n
            ))

    def is_banned(self, telegram_id: int) -> bool:
        u = self.get_user(telegram_id)
        if not u or not u["banned_until"]:
            return False
        try:
            return datetime.now(timezone.utc) < datetime.fromisoformat(u["banned_until"])
        except ValueError:
            return False

    def ban_user(self, user_id: int, days: int, reason: str, admin_id: int):
        days = max(1, min(7, int(days)))
        until = datetime.now(timezone.utc) + timedelta(days=days)
        with self.connect() as c:
            c.execute("""
                UPDATE users
                SET banned_until=?,ban_reason=?,is_hidden=1,updated_at=?
                WHERE id=?
            """, (until.isoformat(timespec="seconds"), reason[:500], now_utc(), user_id))
            c.execute("""
                INSERT INTO ban_history(user_id,admin_telegram_id,action,days,reason,created_at)
                VALUES(?,?,?,?,?,?)
            """, (user_id, admin_id, "ban", days, reason[:500], now_utc()))
            c.execute("""
                INSERT INTO admin_audit(admin_telegram_id,action,target_user_id,details,created_at)
                VALUES(?,?,?,?,?)
            """, (admin_id, "ban", user_id, f"days={days}; reason={reason[:300]}", now_utc()))

    def unban_user(self, user_id: int, admin_id: int):
        with self.connect() as c:
            c.execute("""
                UPDATE users
                SET banned_until=NULL,ban_reason=NULL,updated_at=?
                WHERE id=?
            """, (now_utc(), user_id))
            c.execute("""
                INSERT INTO ban_history(user_id,admin_telegram_id,action,created_at)
                VALUES(?,?,?,?)
            """, (user_id, admin_id, "unban", now_utc()))
            c.execute("""
                INSERT INTO admin_audit(admin_telegram_id,action,target_user_id,created_at)
                VALUES(?,?,?,?)
            """, (admin_id, "unban", user_id, now_utc()))

    def toggle_hidden(self, user_id: int, admin_id: int) -> bool:
        with self.connect() as c:
            row = c.execute("SELECT is_hidden FROM users WHERE id=?", (user_id,)).fetchone()
            if not row:
                return False
            value = 0 if row["is_hidden"] else 1
            c.execute("UPDATE users SET is_hidden=?,updated_at=? WHERE id=?", (value, now_utc(), user_id))
            c.execute("""
                INSERT INTO admin_audit(admin_telegram_id,action,target_user_id,details,created_at)
                VALUES(?,?,?,?,?)
            """, (admin_id, "toggle_hidden", user_id, f"hidden={value}", now_utc()))
            return bool(value)

    def search_users(self, query: str, limit=20):
        query = query.strip()
        if query.startswith("@"):
            query = query[1:]
        p = f"%{query}%"
        with self.connect() as c:
            return c.execute("""
                SELECT * FROM users
                WHERE username LIKE ? OR name LIKE ? OR CAST(telegram_id AS TEXT) LIKE ?
                ORDER BY updated_at DESC LIMIT ?
            """, (p, p, p, limit)).fetchall()

    def delete_user(self, telegram_id: int):
        with self.connect() as c:
            row = c.execute("SELECT id FROM users WHERE telegram_id=?", (telegram_id,)).fetchone()
            if not row:
                return False
            uid = row["id"]
            c.execute("DELETE FROM support_tickets WHERE user_id=?", (uid,))
            c.execute("DELETE FROM user_states WHERE telegram_id=?", (telegram_id,))
            c.execute("DELETE FROM users WHERE id=?", (uid,))
            return True

    # State
    def set_state(self, telegram_id: int, state: str, data=None):
        with self.connect() as c:
            c.execute("""
                INSERT INTO user_states(telegram_id,state,data_json,updated_at)
                VALUES(?,?,?,?)
                ON CONFLICT(telegram_id) DO UPDATE SET
                    state=excluded.state,data_json=excluded.data_json,updated_at=excluded.updated_at
            """, (telegram_id, state, json.dumps(data or {}, ensure_ascii=False), now_utc()))

    def get_state(self, telegram_id: int):
        with self.connect() as c:
            row = c.execute("SELECT * FROM user_states WHERE telegram_id=?", (telegram_id,)).fetchone()
            if not row:
                return "idle", {}
            try:
                return row["state"], json.loads(row["data_json"])
            except json.JSONDecodeError:
                return row["state"], {}

    def clear_state(self, telegram_id: int):
        with self.connect() as c:
            c.execute("DELETE FROM user_states WHERE telegram_id=?", (telegram_id,))

    # Ratings
    def get_candidates(self, viewer_id: int, gender_filter: str | None, limit=20, age_range=None):
        """
        Возвращает список анкет-кандидатов.
        age_range — на сколько лет в плюс/минус искать.
          None      → использовать AGE_RANGE по умолчанию
          0         → только ровесники
          любое N   → ±N лет
          -1        → не фильтровать по возрасту вообще (для фолбэка)
        """
        # Определяем диапазон
        if age_range is None:
            age_range = AGE_RANGE

        # Узнаём возраст зрителя (нужен для фильтра)
        viewer = self.get_user_by_id(viewer_id)
        viewer_age = viewer["age"] if viewer and viewer["age"] else None

        extra = []
        gender_sql = ""
        if gender_filter in ("male", "female"):
            gender_sql = "AND u.gender=?"
            extra.append(gender_filter)

        age_sql = ""
        if age_range >= 0 and viewer_age:
            age_sql = "AND u.age BETWEEN ? AND ?"
            extra.extend([viewer_age - age_range, viewer_age + age_range])

        # Считаем, с какого момента лайк/скип ещё считается "свежим"
        now = datetime.now(timezone.utc)
        skip_cutoff = (now - timedelta(days=SKIP_EXPIRE_DAYS)).isoformat(timespec="seconds")
        like_cutoff = (now - timedelta(days=LIKE_EXPIRE_DAYS)).isoformat(timespec="seconds")

        with self.connect() as c:
            return c.execute(f"""
                SELECT u.*,
                       COALESCE((
                           SELECT COUNT(*) FROM reports r
                           WHERE r.reported_user_id=u.id AND r.status='open'
                       ), 0) AS report_count
                FROM users u
                WHERE u.id != ?
                  AND u.profile_completed=1
                  AND u.is_hidden=0
                  AND (u.banned_until IS NULL OR u.banned_until<=?)
                  AND u.id NOT IN (
                      SELECT to_user_id FROM likes
                      WHERE from_user_id=? AND created_at > ?
                      UNION
                      SELECT to_user_id FROM skips
                      WHERE from_user_id=? AND created_at > ?
                  )
                  {gender_sql}
                  {age_sql}
                ORDER BY report_count ASC, RANDOM()
                LIMIT ?
            """, (
                viewer_id,
                now_utc(),
                viewer_id, like_cutoff,
                viewer_id, skip_cutoff,
                *extra,
                limit,
            )).fetchall()

    def incoming_likes(self, user_id: int, gender_filter: str | None = None, limit=30):
        gender_sql = ""
        params = [user_id, user_id, user_id, now_utc()]
        if gender_filter in ("male", "female"):
            gender_sql = "AND u.gender=?"
            params.append(gender_filter)
        params.append(limit)
        with self.connect() as c:
            return c.execute(f"""
                SELECT u.* FROM likes l
                JOIN users u ON u.id=l.from_user_id
                WHERE l.to_user_id=?
                  AND l.from_user_id != ?
                  AND NOT EXISTS (
                      SELECT 1 FROM likes back
                      WHERE back.from_user_id=? AND back.to_user_id=l.from_user_id
                  )
                  AND u.profile_completed=1
                  AND u.is_hidden=0
                  AND (u.banned_until IS NULL OR u.banned_until<=?)
                  {gender_sql}
                ORDER BY l.created_at ASC
                LIMIT ?
            """, tuple(params)).fetchall()

    def incoming_likes_count(self, user_id: int, gender_filter: str | None = None) -> int:
        gender_sql = ""
        params = [user_id, user_id, user_id, now_utc()]
        if gender_filter in ("male", "female"):
            gender_sql = "AND u.gender=?"
            params.append(gender_filter)
        with self.connect() as c:
            return c.execute(f"""
                SELECT COUNT(*) FROM likes l
                JOIN users u ON u.id=l.from_user_id
                WHERE l.to_user_id=?
                  AND l.from_user_id != ?
                  AND NOT EXISTS (
                      SELECT 1 FROM likes back
                      WHERE back.from_user_id=? AND back.to_user_id=l.from_user_id
                  )
                  AND u.profile_completed=1
                  AND u.is_hidden=0
                  AND (u.banned_until IS NULL OR u.banned_until<=?)
                  {gender_sql}
            """, tuple(params)).fetchone()[0]

    def add_like(self, from_id: int, to_id: int) -> bool:
        with self.connect() as c:
            cur = c.execute(
                "INSERT OR IGNORE INTO likes(from_user_id,to_user_id,created_at) VALUES(?,?,?)",
                (from_id, to_id, now_utc()),
            )
            if cur.rowcount == 0:
                # Лайк уже был — обновим дату, чтобы он снова "считался свежим"
                c.execute(
                    "UPDATE likes SET created_at=? WHERE from_user_id=? AND to_user_id=?",
                    (now_utc(), from_id, to_id),
                )
                # Повторный лайк не считается новым — не шлём уведомление
                return False
            return c.execute(
                "SELECT 1 FROM likes WHERE from_user_id=? AND to_user_id=?",
                (to_id, from_id),
            ).fetchone() is not None

    def add_skip(self, from_id: int, to_id: int):
        with self.connect() as c:
            c.execute(
                "INSERT OR IGNORE INTO skips(from_user_id,to_user_id,created_at) VALUES(?,?,?)",
                (from_id, to_id, now_utc()),
            )

    # Reports
    def create_report(self, reporter_id: int, reported_id: int, cause: str):
        target = self.get_user_by_id(reported_id)
        snapshot = json.dumps(dict(target) if target else {}, ensure_ascii=False, default=str)

        with self.connect() as c:
            old = c.execute("""
                SELECT id FROM reports
                WHERE reporter_user_id=? AND reported_user_id=? AND status='open'
            """, (reporter_id, reported_id)).fetchone()
            if old:
                return old["id"], False

            cur = c.execute("""
                INSERT INTO reports(
                    reporter_user_id,reported_user_id,cause,profile_snapshot,created_at
                ) VALUES(?,?,?,?,?)
            """, (reporter_id, reported_id, cause[:2000], snapshot, now_utc()))

            count = c.execute("""
                SELECT COUNT(DISTINCT reporter_user_id) FROM reports
                WHERE reported_user_id=? AND status='open'
            """, (reported_id,)).fetchone()[0]

            if count >= 3:
                c.execute("""
                    UPDATE users SET is_hidden=1,
                    moderation_note=?,updated_at=? WHERE id=?
                """, ("Автоматически скрыто после 3+ уникальных жалоб", now_utc(), reported_id))

            return cur.lastrowid, True

    def open_reports(self, limit=30):
        with self.connect() as c:
            return c.execute("""
                SELECT r.*,u.name AS reported_name,u.username AS reported_username
                FROM reports r JOIN users u ON u.id=r.reported_user_id
                WHERE r.status='open' ORDER BY r.created_at LIMIT ?
            """, (limit,)).fetchall()

    def get_report(self, report_id):
        with self.connect() as c:
            return c.execute("""
                SELECT r.*,u.name AS reported_name,u.username AS reported_username,
                       u.telegram_id AS reported_telegram_id
                FROM reports r JOIN users u ON u.id=r.reported_user_id
                WHERE r.id=?
            """, (report_id,)).fetchone()

    def close_report(self, report_id, admin_id, comment=""):
        with self.connect() as c:
            c.execute("""
                UPDATE reports SET status='closed',admin_comment=?,resolved_at=?
                WHERE id=?
            """, (comment[:1000], now_utc(), report_id))
            c.execute("""
                INSERT INTO admin_audit(admin_telegram_id,action,details,created_at)
                VALUES(?,?,?,?)
            """, (admin_id, "close_report", f"report_id={report_id}", now_utc()))

    # Tickets
    def has_open_ticket(self, user_id):
        if not user_id:
            return False
        with self.connect() as c:
            return c.execute(
                "SELECT 1 FROM support_tickets WHERE user_id=? AND status='open' LIMIT 1",
                (user_id,),
            ).fetchone() is not None

    def create_ticket(self, user_id, category, message):
        with self.connect() as c:
            cur = c.execute("""
                INSERT INTO support_tickets(user_id,category,message,created_at,updated_at)
                VALUES(?,?,?,?,?)
            """, (user_id, category, message[:5000], now_utc(), now_utc()))
            return cur.lastrowid

    def open_tickets(self, limit=30):
        with self.connect() as c:
            return c.execute("""
                SELECT t.*,u.telegram_id,u.username,u.name
                FROM support_tickets t LEFT JOIN users u ON u.id=t.user_id
                WHERE t.status='open' ORDER BY t.created_at LIMIT ?
            """, (limit,)).fetchall()

    def get_ticket(self, ticket_id):
        with self.connect() as c:
            return c.execute("""
                SELECT t.*,u.telegram_id,u.username,u.name
                FROM support_tickets t LEFT JOIN users u ON u.id=t.user_id
                WHERE t.id=?
            """, (ticket_id,)).fetchone()

    def close_ticket(self, ticket_id, admin_id, reply):
        with self.connect() as c:
            c.execute("""
                UPDATE support_tickets
                SET status='closed',admin_id=?,admin_reply=?,updated_at=?
                WHERE id=?
            """, (admin_id, reply[:5000], now_utc(), ticket_id))

    # Stats
    def stats(self):
        with self.connect() as c:
            return {
                "users": c.execute("SELECT COUNT(*) FROM users").fetchone()[0],
                "completed": c.execute(
                    "SELECT COUNT(*) FROM users WHERE profile_completed=1"
                ).fetchone()[0],
                "likes": c.execute("SELECT COUNT(*) FROM likes").fetchone()[0],
                "reports_open": c.execute(
                    "SELECT COUNT(*) FROM reports WHERE status='open'"
                ).fetchone()[0],
                "tickets_open": c.execute(
                    "SELECT COUNT(*) FROM support_tickets WHERE status='open'"
                ).fetchone()[0],
                "banned": c.execute("""
                    SELECT COUNT(*) FROM users
                    WHERE banned_until IS NOT NULL AND banned_until>?
                """, (now_utc(),)).fetchone()[0],
            }
