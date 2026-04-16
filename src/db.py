from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Generator

import psycopg2
import psycopg2.extras


@contextmanager
def _get_conn() -> Generator[psycopg2.extensions.connection, None, None]:
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _cursor(conn: psycopg2.extensions.connection) -> psycopg2.extensions.cursor:
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def init_db() -> None:
    with _get_conn() as conn:
        cur = _cursor(conn)
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                password_salt TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS auth_sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS route_sessions (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                profile TEXT NOT NULL,
                route_name TEXT,
                target_mode TEXT NOT NULL,
                target_value DOUBLE PRECISION NOT NULL,
                start_lat DOUBLE PRECISION NOT NULL,
                start_lon DOUBLE PRECISION NOT NULL,
                distance_km DOUBLE PRECISION NOT NULL,
                duration_min DOUBLE PRECISION NOT NULL,
                steps INTEGER NOT NULL,
                route_geojson TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS walk_sessions (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                route_session_id INTEGER,
                route_geojson TEXT,
                started_at TIMESTAMP NOT NULL,
                ended_at TIMESTAMP NOT NULL,
                elapsed_seconds INTEGER NOT NULL,
                distance_km DOUBLE PRECISION NOT NULL,
                steps INTEGER NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (route_session_id) REFERENCES route_sessions(id) ON DELETE SET NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS favorite_routes (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                route_session_id INTEGER NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, route_session_id),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (route_session_id) REFERENCES route_sessions(id) ON DELETE CASCADE
            )
            """
        )


def create_user(email: str, password_hash: str, password_salt: str) -> dict[str, Any]:
    with _get_conn() as conn:
        cur = _cursor(conn)
        cur.execute(
            """
            INSERT INTO users (email, password_hash, password_salt)
            VALUES (%s, %s, %s)
            RETURNING id, email, created_at
            """,
            (email.lower().strip(), password_hash, password_salt),
        )
        row = cur.fetchone()
    return dict(row)


def get_user_by_email(email: str) -> dict[str, Any] | None:
    with _get_conn() as conn:
        cur = _cursor(conn)
        cur.execute(
            """
            SELECT id, email, password_hash, password_salt, created_at
            FROM users
            WHERE email = %s
            """,
            (email.lower().strip(),),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def update_user_password(email: str, password_hash: str, password_salt: str) -> bool:
    with _get_conn() as conn:
        cur = _cursor(conn)
        cur.execute(
            """
            UPDATE users
            SET password_hash = %s, password_salt = %s
            WHERE email = %s
            """,
            (password_hash, password_salt, email.lower().strip()),
        )
        return cur.rowcount > 0


def get_user_by_id(user_id: int) -> dict[str, Any] | None:
    with _get_conn() as conn:
        cur = _cursor(conn)
        cur.execute(
            "SELECT id, email, created_at FROM users WHERE id = %s",
            (user_id,),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def create_session(token: str, user_id: int) -> None:
    with _get_conn() as conn:
        cur = _cursor(conn)
        cur.execute(
            "INSERT INTO auth_sessions (token, user_id) VALUES (%s, %s)",
            (token, user_id),
        )


def delete_session(token: str) -> None:
    with _get_conn() as conn:
        cur = _cursor(conn)
        cur.execute("DELETE FROM auth_sessions WHERE token = %s", (token,))


def get_user_by_session(token: str) -> dict[str, Any] | None:
    with _get_conn() as conn:
        cur = _cursor(conn)
        cur.execute(
            """
            SELECT u.id, u.email, u.created_at
            FROM auth_sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.token = %s
            """,
            (token,),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def create_route_session(
    *,
    user_id: int,
    profile: str,
    route_name: str | None,
    target_mode: str,
    target_value: float,
    start_lat: float,
    start_lon: float,
    distance_km: float,
    duration_min: float,
    steps: int,
    route_geojson: str,
) -> int:
    with _get_conn() as conn:
        cur = _cursor(conn)
        cur.execute(
            """
            INSERT INTO route_sessions (
                user_id, profile, route_name, target_mode, target_value,
                start_lat, start_lon, distance_km, duration_min, steps, route_geojson
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                user_id, profile, route_name, target_mode, target_value,
                start_lat, start_lon, distance_km, duration_min, steps, route_geojson,
            ),
        )
        route_id = int(cur.fetchone()["id"])
        if not route_name or not route_name.strip():
            cur.execute(
                "UPDATE route_sessions SET route_name = %s WHERE id = %s",
                (f"Route {route_id}", route_id),
            )
        return route_id


def list_route_sessions(user_id: int, limit: int = 50) -> list[dict[str, Any]]:
    with _get_conn() as conn:
        cur = _cursor(conn)
        cur.execute(
            """
            SELECT
                rs.id,
                rs.profile,
                rs.route_name,
                rs.target_mode,
                rs.target_value,
                rs.start_lat,
                rs.start_lon,
                rs.distance_km,
                rs.duration_min,
                rs.steps,
                rs.route_geojson,
                rs.created_at,
                CASE WHEN fr.id IS NULL THEN 0 ELSE 1 END AS is_favorite
            FROM route_sessions rs
            LEFT JOIN favorite_routes fr
              ON fr.route_session_id = rs.id
             AND fr.user_id = rs.user_id
            WHERE rs.user_id = %s
            ORDER BY rs.created_at DESC, rs.id DESC
            LIMIT %s
            """,
            (user_id, limit),
        )
        rows = cur.fetchall()
    return [dict(row) for row in rows]


def add_favorite_route(user_id: int, route_session_id: int) -> None:
    with _get_conn() as conn:
        cur = _cursor(conn)
        cur.execute(
            """
            INSERT INTO favorite_routes (user_id, route_session_id)
            VALUES (%s, %s)
            ON CONFLICT DO NOTHING
            """,
            (user_id, route_session_id),
        )


def remove_favorite_route(user_id: int, route_session_id: int) -> None:
    with _get_conn() as conn:
        cur = _cursor(conn)
        cur.execute(
            "DELETE FROM favorite_routes WHERE user_id = %s AND route_session_id = %s",
            (user_id, route_session_id),
        )


def list_favorite_routes(user_id: int, limit: int = 50) -> list[dict[str, Any]]:
    with _get_conn() as conn:
        cur = _cursor(conn)
        cur.execute(
            """
            SELECT
                rs.id,
                rs.profile,
                rs.route_name,
                rs.target_mode,
                rs.target_value,
                rs.start_lat,
                rs.start_lon,
                rs.distance_km,
                rs.duration_min,
                rs.steps,
                rs.route_geojson,
                rs.created_at,
                1 AS is_favorite
            FROM favorite_routes fr
            JOIN route_sessions rs ON rs.id = fr.route_session_id
            WHERE fr.user_id = %s
            ORDER BY fr.created_at DESC, fr.id DESC
            LIMIT %s
            """,
            (user_id, limit),
        )
        rows = cur.fetchall()
    return [dict(row) for row in rows]


def get_route_owner(route_session_id: int) -> int | None:
    with _get_conn() as conn:
        cur = _cursor(conn)
        cur.execute(
            "SELECT user_id FROM route_sessions WHERE id = %s",
            (route_session_id,),
        )
        row = cur.fetchone()
    if not row:
        return None
    return int(row["user_id"])


def get_route_geojson(user_id: int, route_session_id: int) -> str | None:
    with _get_conn() as conn:
        cur = _cursor(conn)
        cur.execute(
            "SELECT route_geojson FROM route_sessions WHERE id = %s AND user_id = %s",
            (route_session_id, user_id),
        )
        row = cur.fetchone()
    if not row:
        return None
    return str(row["route_geojson"]) if row["route_geojson"] is not None else None


def update_route_name(user_id: int, route_session_id: int, route_name: str | None) -> bool:
    with _get_conn() as conn:
        cur = _cursor(conn)
        cur.execute(
            """
            UPDATE route_sessions
            SET route_name = %s
            WHERE id = %s AND user_id = %s
            """,
            (route_name.strip() if route_name else None, route_session_id, user_id),
        )
        return cur.rowcount > 0


def delete_route_session(user_id: int, route_session_id: int) -> bool:
    with _get_conn() as conn:
        cur = _cursor(conn)
        cur.execute(
            "DELETE FROM route_sessions WHERE id = %s AND user_id = %s",
            (route_session_id, user_id),
        )
        return cur.rowcount > 0


def create_walk_session(
    *,
    user_id: int,
    route_session_id: int | None,
    route_geojson: str | None,
    started_at: str,
    ended_at: str,
    elapsed_seconds: int,
    distance_km: float,
    steps: int,
) -> int:
    with _get_conn() as conn:
        cur = _cursor(conn)
        cur.execute(
            """
            INSERT INTO walk_sessions (
                user_id, route_session_id, route_geojson,
                started_at, ended_at, elapsed_seconds, distance_km, steps
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (user_id, route_session_id, route_geojson, started_at, ended_at, elapsed_seconds, distance_km, steps),
        )
        return int(cur.fetchone()["id"])


def list_walk_sessions_in_range(user_id: int, start_iso: str, end_iso: str) -> list[dict[str, Any]]:
    with _get_conn() as conn:
        cur = _cursor(conn)
        cur.execute(
            """
            SELECT
                ws.id,
                ws.route_session_id,
                rs.route_name,
                ws.started_at,
                ws.ended_at,
                ws.elapsed_seconds,
                ws.distance_km,
                ws.steps
            FROM walk_sessions ws
            LEFT JOIN route_sessions rs ON rs.id = ws.route_session_id
            WHERE ws.user_id = %s
              AND ws.ended_at >= %s::timestamptz
              AND ws.ended_at < %s::timestamptz
            ORDER BY ws.ended_at DESC, ws.id DESC
            """,
            (user_id, start_iso, end_iso),
        )
        rows = cur.fetchall()
    return [dict(row) for row in rows]


def list_walk_sessions(user_id: int, limit: int = 200) -> list[dict[str, Any]]:
    with _get_conn() as conn:
        cur = _cursor(conn)
        cur.execute(
            """
            SELECT
                ws.id,
                ws.route_session_id,
                rs.route_name,
                ws.started_at,
                ws.ended_at,
                ws.elapsed_seconds,
                ws.distance_km,
                ws.steps
            FROM walk_sessions ws
            LEFT JOIN route_sessions rs ON rs.id = ws.route_session_id
            WHERE ws.user_id = %s
            ORDER BY ws.ended_at DESC, ws.id DESC
            LIMIT %s
            """,
            (user_id, limit),
        )
        rows = cur.fetchall()
    return [dict(row) for row in rows]


def get_walk_session(user_id: int, walk_session_id: int) -> dict[str, Any] | None:
    with _get_conn() as conn:
        cur = _cursor(conn)
        cur.execute(
            """
            SELECT
                ws.id,
                ws.route_session_id,
                rs.route_name,
                COALESCE(ws.route_geojson, rs.route_geojson) AS route_geojson,
                ws.started_at,
                ws.ended_at,
                ws.elapsed_seconds,
                ws.distance_km,
                ws.steps
            FROM walk_sessions ws
            LEFT JOIN route_sessions rs ON rs.id = ws.route_session_id
            WHERE ws.user_id = %s AND ws.id = %s
            """,
            (user_id, walk_session_id),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def delete_walk_session(user_id: int, walk_session_id: int) -> bool:
    with _get_conn() as conn:
        cur = _cursor(conn)
        cur.execute(
            "DELETE FROM walk_sessions WHERE user_id = %s AND id = %s",
            (user_id, walk_session_id),
        )
        return cur.rowcount > 0


def list_route_sessions_in_range(user_id: int, start_iso: str, end_iso: str) -> list[dict[str, Any]]:
    with _get_conn() as conn:
        cur = _cursor(conn)
        cur.execute(
            """
            SELECT
                id,
                profile,
                distance_km,
                duration_min,
                steps,
                created_at
            FROM route_sessions
            WHERE user_id = %s
              AND created_at >= %s::timestamptz
              AND created_at < %s::timestamptz
            ORDER BY created_at ASC
            """,
            (user_id, start_iso, end_iso),
        )
        rows = cur.fetchall()
    return [dict(row) for row in rows]
