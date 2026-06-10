"""Database layer for CareerGuru — Neon Postgres + bcrypt auth."""
import os
import re

import bcrypt
import psycopg2
from psycopg2.extras import RealDictCursor

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _connect():
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set. Add it to your .env file or Streamlit secrets.")
    return psycopg2.connect(url)


def init_db():
    """Create the users table if it doesn't exist. Safe to call on every startup."""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id          SERIAL PRIMARY KEY,
                email       TEXT UNIQUE NOT NULL,
                password    TEXT NOT NULL,
                full_name   TEXT,
                created_at  TIMESTAMPTZ DEFAULT now()
            );
            """
        )
        conn.commit()


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _check_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_user(email: str, password: str, full_name: str = ""):
    """Register a new user. Returns (ok, message_or_user)."""
    email = (email or "").strip().lower()
    if not _EMAIL_RE.match(email):
        return False, "Please enter a valid email address."
    if len(password or "") < 6:
        return False, "Password must be at least 6 characters."

    try:
        with _connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "INSERT INTO users (email, password, full_name) VALUES (%s, %s, %s) "
                "RETURNING id, email, full_name, created_at;",
                (email, _hash_password(password), (full_name or "").strip()),
            )
            user = cur.fetchone()
            conn.commit()
            return True, dict(user)
    except psycopg2.errors.UniqueViolation:
        return False, "An account with this email already exists."
    except Exception as e:  # noqa: BLE001
        return False, f"Could not create account: {e}"


def verify_user(email: str, password: str):
    """Validate login credentials. Returns (ok, message_or_user)."""
    email = (email or "").strip().lower()
    if not email or not password:
        return False, "Please enter your email and password."

    try:
        with _connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT id, email, password, full_name, created_at FROM users WHERE email = %s;",
                (email,),
            )
            row = cur.fetchone()
    except Exception as e:  # noqa: BLE001
        return False, f"Login failed: {e}"

    if not row or not _check_password(password, row["password"]):
        return False, "Invalid email or password."

    user = {k: row[k] for k in ("id", "email", "full_name", "created_at")}
    return True, user
