from __future__ import annotations

import json
import os
from pathlib import Path
from datetime import UTC, datetime, timedelta

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import requests

from src.auth_service import hash_password, new_session_token, verify_password
from src.db import (
    add_favorite_route,
    create_walk_session,
    delete_walk_session,
    delete_route_session,
    create_route_session,
    create_session,
    create_user,
    delete_session,
    get_walk_session,
    get_route_geojson,
    get_route_owner,
    get_user_by_email,
    get_user_by_session,
    init_db,
    list_favorite_routes,
    list_walk_sessions,
    list_walk_sessions_in_range,
    list_route_sessions_in_range,
    list_route_sessions,
    remove_favorite_route,
    update_route_name,
    update_user_password,
)
from src.route_service import build_round_trip

load_dotenv()

app = FastAPI(title="OSM Route Optimizer")
WEB_DIR = Path(__file__).resolve().parent.parent / "web"
app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")
SESSION_COOKIE_NAME = "route_auth"


@app.on_event("startup")
def startup_init_db() -> None:
    init_db()


class RouteRequest(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    target_mode: str = Field(default="minutes")
    target_value: float = Field(gt=0)
    variation_seed: int = Field(default=0)


class AuthRequest(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=6)


class RouteNameRequest(BaseModel):
    route_name: str | None = Field(default=None, max_length=100)


class WalkSessionRequest(BaseModel):
    route_session_id: int | None = Field(default=None)
    elapsed_seconds: int = Field(gt=0)
    distance_km: float = Field(ge=0)
    steps: int = Field(ge=0)


class SaveRouteRequest(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    target_mode: str = Field(default="minutes")
    target_value: float = Field(gt=0)
    route_name: str | None = Field(default=None, max_length=100)
    distance_km: float = Field(ge=0)
    duration_min: float = Field(ge=0)
    steps: int = Field(ge=0)
    route_geojson: dict


def _calc_pct_change(current: float, previous: float) -> float | None:
    if previous == 0:
        return None
    return round(((current - previous) / previous) * 100.0, 1)


def _aggregate_sessions(rows: list[dict]) -> dict:
    totals = {
        "distance_km": round(sum(float(r["distance_km"]) for r in rows), 2),
        "steps": int(sum(int(r["steps"]) for r in rows)),
        "duration_min": round(sum(float(r["duration_min"]) for r in rows), 1),
        "sessions": len(rows),
    }

    if totals["sessions"] == 0:
        avg_per_session = {
            "distance_km": 0.0,
            "steps": 0.0,
            "duration_min": 0.0,
        }
    else:
        avg_per_session = {
            "distance_km": round(totals["distance_km"] / totals["sessions"], 2),
            "steps": round(totals["steps"] / totals["sessions"], 1),
            "duration_min": round(totals["duration_min"] / totals["sessions"], 1),
        }

    by_profile: dict[str, dict] = {}
    for profile in ("foot-walking",):
        p_rows = [r for r in rows if r["profile"] == profile]
        p_total_sessions = len(p_rows)
        if p_total_sessions == 0:
            by_profile[profile] = {
                "sessions": 0,
                "avg_per_session": {
                    "distance_km": 0.0,
                    "steps": 0.0,
                    "duration_min": 0.0,
                },
            }
            continue

        p_dist = sum(float(r["distance_km"]) for r in p_rows)
        p_steps = sum(int(r["steps"]) for r in p_rows)
        p_dur = sum(float(r["duration_min"]) for r in p_rows)

        by_profile[profile] = {
            "sessions": p_total_sessions,
            "avg_per_session": {
                "distance_km": round(p_dist / p_total_sessions, 2),
                "steps": round(p_steps / p_total_sessions, 1),
                "duration_min": round(p_dur / p_total_sessions, 1),
            },
        }

    return {
        "totals": totals,
        "avg_per_session": avg_per_session,
        "by_profile": by_profile,
    }


def _period_bounds(period: str) -> tuple[datetime, datetime, datetime, datetime]:
    now = datetime.now(UTC)
    if period == "daily":
        current_start = datetime(now.year, now.month, now.day, tzinfo=UTC)
        current_end = current_start + timedelta(days=1)
        previous_start = current_start - timedelta(days=1)
        previous_end = current_start
    elif period == "weekly":
        current_end = now
        current_start = now - timedelta(days=7)
        previous_end = current_start
        previous_start = previous_end - timedelta(days=7)
    elif period == "monthly":
        current_end = now
        current_start = now - timedelta(days=30)
        previous_end = current_start
        previous_start = previous_end - timedelta(days=30)
    else:
        raise ValueError("period must be daily, weekly, or monthly")

    return current_start, current_end, previous_start, previous_end


def _shift_month_start(base_start: datetime, months_back: int) -> datetime:
    year = base_start.year
    month = base_start.month - months_back
    while month <= 0:
        year -= 1
        month += 12
    return datetime(year, month, 1, tzinfo=UTC)


def _walk_period_bounds(period: str, offset: int = 0) -> tuple[datetime, datetime, str]:
    now = datetime.now(UTC)

    if period == "daily":
        start = datetime(now.year, now.month, now.day, tzinfo=UTC) - timedelta(days=offset)
        end = start + timedelta(days=1)
        label = f"Day: {start.strftime('%d/%m/%Y')}"
        return start, end, label

    if period == "weekly":
        monday = now - timedelta(days=now.weekday())
        start = datetime(monday.year, monday.month, monday.day, tzinfo=UTC) - timedelta(days=7 * offset)
        end = start + timedelta(days=7)
        week_end_inclusive = end - timedelta(days=1)
        label = f"Week: {start.strftime('%d/%m/%Y')} - {week_end_inclusive.strftime('%d/%m/%Y')}"
        return start, end, label

    if period == "monthly":
        current_month_start = datetime(now.year, now.month, 1, tzinfo=UTC)
        start = _shift_month_start(current_month_start, offset)
        if start.month == 12:
            end = datetime(start.year + 1, 1, 1, tzinfo=UTC)
        else:
            end = datetime(start.year, start.month + 1, 1, tzinfo=UTC)
        month_end_inclusive = end - timedelta(days=1)
        label = f"Month: {start.strftime('%d/%m/%Y')} - {month_end_inclusive.strftime('%d/%m/%Y')}"
        return start, end, label

    raise ValueError("period must be daily, weekly, or monthly")


def _series_bucket_starts(period: str, offset: int) -> list[datetime]:
    now = datetime.now(UTC)

    if period == "daily":
        selected_start = datetime(now.year, now.month, now.day, tzinfo=UTC) - timedelta(days=offset)
        return [selected_start - timedelta(days=step) for step in range(13, -1, -1)]

    if period == "weekly":
        monday = now - timedelta(days=now.weekday())
        selected_start = datetime(monday.year, monday.month, monday.day, tzinfo=UTC) - timedelta(days=7 * offset)
        return [selected_start - timedelta(days=7 * step) for step in range(11, -1, -1)]

    if period == "monthly":
        selected_start = _shift_month_start(datetime(now.year, now.month, 1, tzinfo=UTC), offset)
        return [_shift_month_start(selected_start, step) for step in range(11, -1, -1)]

    raise ValueError("period must be daily, weekly, or monthly")


def _series_bucket_end(period: str, start: datetime) -> datetime:
    if period == "daily":
        return start + timedelta(days=1)
    if period == "weekly":
        return start + timedelta(days=7)
    if start.month == 12:
        return datetime(start.year + 1, 1, 1, tzinfo=UTC)
    return datetime(start.year, start.month + 1, 1, tzinfo=UTC)


def _series_bucket_label(period: str, start: datetime, end: datetime) -> str:
    if period == "daily":
        return start.strftime("%d/%m")
    if period == "weekly":
        return f"{start.strftime('%d/%m')} - {(end - timedelta(days=1)).strftime('%d/%m')}"
    return start.strftime("%m/%Y")


def _walk_period_stats(user_id: int, period: str, offset: int = 0) -> dict:
    start, end, label = _walk_period_bounds(period, offset=offset)
    rows = list_walk_sessions_in_range(
        user_id,
        start.strftime("%Y-%m-%d %H:%M:%S"),
        end.strftime("%Y-%m-%d %H:%M:%S"),
    )

    total_distance = round(sum(float(r["distance_km"]) for r in rows), 2)
    total_elapsed = int(sum(int(r["elapsed_seconds"]) for r in rows))
    total_steps = int(sum(int(r["steps"]) for r in rows))
    sessions = len(rows)

    if sessions > 0:
        avg_distance = round(total_distance / sessions, 2)
        avg_elapsed = int(round(total_elapsed / sessions))
        avg_steps = int(round(total_steps / sessions))
    else:
        avg_distance = 0.0
        avg_elapsed = 0
        avg_steps = 0

    return {
        "label": label,
        "totals": {
            "distance_km": total_distance,
            "elapsed_seconds": total_elapsed,
            "steps": total_steps,
            "sessions": sessions,
        },
        "avg_per_session": {
            "distance_km": avg_distance,
            "elapsed_seconds": avg_elapsed,
            "steps": avg_steps,
        },
        "bounds": {
            "start": start.isoformat(),
            "end": end.isoformat(),
        },
    }


def _walk_period_series(user_id: int, period: str) -> list[dict]:
    bucket_starts = _series_bucket_starts(period, offset=0)
    bucket_ends = [_series_bucket_end(period, s) for s in bucket_starts]

    series_start_sql = bucket_starts[0].strftime("%Y-%m-%d %H:%M:%S")
    series_end_sql = bucket_ends[-1].strftime("%Y-%m-%d %H:%M:%S")
    rows = list_walk_sessions_in_range(user_id, series_start_sql, series_end_sql)

    out: list[dict] = []
    for i, start in enumerate(bucket_starts):
        end = bucket_ends[i]
        bucket_rows = []
        for row in rows:
            ended = datetime.strptime(str(row["ended_at"]), "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
            if start <= ended < end:
                bucket_rows.append(row)

        if not bucket_rows:
            continue

        out.append(
            {
                "label": _series_bucket_label(period, start, end),
                "distance_km": round(sum(float(r["distance_km"]) for r in bucket_rows), 2),
                "elapsed_seconds": int(sum(int(r["elapsed_seconds"]) for r in bucket_rows)),
                "steps": int(sum(int(r["steps"]) for r in bucket_rows)),
                "sessions": len(bucket_rows),
            }
        )

    return out


def _walk_period_series_with_offset(user_id: int, period: str, offset: int = 0) -> list[dict]:
    bucket_starts = _series_bucket_starts(period, offset=offset)
    bucket_ends = [_series_bucket_end(period, s) for s in bucket_starts]

    series_start_sql = bucket_starts[0].strftime("%Y-%m-%d %H:%M:%S")
    series_end_sql = bucket_ends[-1].strftime("%Y-%m-%d %H:%M:%S")
    rows = list_walk_sessions_in_range(user_id, series_start_sql, series_end_sql)

    out: list[dict] = []
    for i, start in enumerate(bucket_starts):
        end = bucket_ends[i]
        bucket_rows = []
        for row in rows:
            ended = datetime.strptime(str(row["ended_at"]), "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
            if start <= ended < end:
                bucket_rows.append(row)

        if not bucket_rows:
            continue

        out.append(
            {
                "label": _series_bucket_label(period, start, end),
                "distance_km": round(sum(float(r["distance_km"]) for r in bucket_rows), 2),
                "elapsed_seconds": int(sum(int(r["elapsed_seconds"]) for r in bucket_rows)),
                "steps": int(sum(int(r["steps"]) for r in bucket_rows)),
                "sessions": len(bucket_rows),
            }
        )

    return out


def _get_current_user(request: Request) -> dict | None:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None
    return get_user_by_session(token)


def _require_user(request: Request) -> dict:
    user = _get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/auth/register")
def register(payload: AuthRequest, response: Response) -> dict:
    existing = get_user_by_email(payload.email)
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    password_hash, password_salt = hash_password(payload.password)
    user = create_user(payload.email, password_hash, password_salt)

    token = new_session_token()
    create_session(token, int(user["id"]))
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=60 * 60 * 24 * 30,
    )
    return {"user": user}


@app.post("/api/auth/login")
def login(payload: AuthRequest, response: Response) -> dict:
    user = get_user_by_email(payload.email)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not verify_password(payload.password, user["password_hash"], user["password_salt"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = new_session_token()
    create_session(token, int(user["id"]))
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=60 * 60 * 24 * 30,
    )
    return {
        "user": {
            "id": user["id"],
            "email": user["email"],
            "created_at": user["created_at"],
        }
    }


@app.post("/api/auth/reset-password")
def reset_password(payload: AuthRequest) -> dict[str, bool]:
    user = get_user_by_email(payload.email)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    password_hash, password_salt = hash_password(payload.password)
    updated = update_user_password(payload.email, password_hash, password_salt)
    if not updated:
        raise HTTPException(status_code=500, detail="Could not reset password")

    return {"ok": True}


@app.post("/api/auth/logout")
def logout(request: Request, response: Response) -> dict[str, bool]:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        delete_session(token)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return {"ok": True}


@app.get("/api/auth/me")
def me(request: Request) -> dict:
    user = _get_current_user(request)
    if not user:
        return {"authenticated": False}
    return {"authenticated": True, "user": user}


@app.get("/api/me/routes")
def my_routes(request: Request) -> dict:
    user = _require_user(request)
    rows = list_route_sessions(int(user["id"]), limit=50)

    for row in rows:
        row["route_geojson"] = json.loads(row["route_geojson"])

    return {"routes": rows}


@app.get("/api/me/favorites")
def my_favorites(request: Request) -> dict:
    user = _require_user(request)
    rows = list_favorite_routes(int(user["id"]), limit=50)
    for row in rows:
        row["route_geojson"] = json.loads(row["route_geojson"])
    return {"routes": rows}


@app.post("/api/me/routes/{route_id}/favorite")
def favorite_route(route_id: int, request: Request) -> dict[str, bool]:
    user = _require_user(request)
    owner_id = get_route_owner(route_id)
    if owner_id is None:
        raise HTTPException(status_code=404, detail="Route not found")
    if owner_id != int(user["id"]):
        raise HTTPException(status_code=403, detail="Cannot favorite another user's route")

    add_favorite_route(int(user["id"]), route_id)
    return {"ok": True}


@app.delete("/api/me/routes/{route_id}/favorite")
def unfavorite_route(route_id: int, request: Request) -> dict[str, bool]:
    user = _require_user(request)
    owner_id = get_route_owner(route_id)
    if owner_id is None:
        raise HTTPException(status_code=404, detail="Route not found")
    if owner_id != int(user["id"]):
        raise HTTPException(status_code=403, detail="Cannot unfavorite another user's route")

    remove_favorite_route(int(user["id"]), route_id)
    return {"ok": True}


@app.patch("/api/me/routes/{route_id}/name")
def rename_route(route_id: int, payload: RouteNameRequest, request: Request) -> dict[str, bool]:
    user = _require_user(request)
    owner_id = get_route_owner(route_id)
    if owner_id is None:
        raise HTTPException(status_code=404, detail="Route not found")
    if owner_id != int(user["id"]):
        raise HTTPException(status_code=403, detail="Cannot rename another user's route")

    clean_name = payload.route_name.strip() if payload.route_name else None
    updated = update_route_name(int(user["id"]), route_id, clean_name)
    if not updated:
        raise HTTPException(status_code=500, detail="Could not update route name")
    return {"ok": True}


@app.delete("/api/me/routes/{route_id}")
def delete_route(route_id: int, request: Request) -> dict[str, bool]:
    user = _require_user(request)
    owner_id = get_route_owner(route_id)
    if owner_id is None:
        raise HTTPException(status_code=404, detail="Route not found")
    if owner_id != int(user["id"]):
        raise HTTPException(status_code=403, detail="Cannot delete another user's route")

    deleted = delete_route_session(int(user["id"]), route_id)
    if not deleted:
        raise HTTPException(status_code=500, detail="Could not delete route")
    return {"ok": True}


@app.post("/api/me/walk-sessions")
def create_my_walk_session(payload: WalkSessionRequest, request: Request) -> dict[str, int]:
    user = _require_user(request)
    user_id = int(user["id"])

    route_id = payload.route_session_id
    route_geojson: str | None = None
    if route_id is not None:
        owner_id = get_route_owner(route_id)
        if owner_id is None:
            raise HTTPException(status_code=404, detail="Route not found")
        if owner_id != user_id:
            raise HTTPException(status_code=403, detail="Cannot attach session to another user's route")
        route_geojson = get_route_geojson(user_id, route_id)

    ended_at = datetime.now(UTC)
    started_at = ended_at - timedelta(seconds=payload.elapsed_seconds)

    started_at_sql = started_at.strftime("%Y-%m-%d %H:%M:%S")
    ended_at_sql = ended_at.strftime("%Y-%m-%d %H:%M:%S")

    session_id = create_walk_session(
        user_id=user_id,
        route_session_id=route_id,
        route_geojson=route_geojson,
        started_at=started_at_sql,
        ended_at=ended_at_sql,
        elapsed_seconds=int(payload.elapsed_seconds),
        distance_km=float(payload.distance_km),
        steps=int(payload.steps),
    )
    return {"id": session_id}


@app.get("/api/me/walk-analytics")
def walk_analytics(request: Request, period: str = "weekly", offset: int = 0) -> dict:
    user = _require_user(request)

    if offset < 0:
        raise HTTPException(status_code=400, detail="offset must be >= 0")

    try:
        c_start, c_end, period_label = _walk_period_bounds(period, offset)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    c_start_sql = c_start.strftime("%Y-%m-%d %H:%M:%S")
    c_end_sql = c_end.strftime("%Y-%m-%d %H:%M:%S")
    rows = list_walk_sessions_in_range(int(user["id"]), c_start_sql, c_end_sql)

    totals = {
        "distance_km": round(sum(float(r["distance_km"]) for r in rows), 2),
        "elapsed_seconds": int(sum(int(r["elapsed_seconds"]) for r in rows)),
        "steps": int(sum(int(r["steps"]) for r in rows)),
        "sessions": len(rows),
    }

    bucket_starts = _series_bucket_starts(period, offset)
    bucket_ends = [_series_bucket_end(period, s) for s in bucket_starts]
    series_start_sql = bucket_starts[0].strftime("%Y-%m-%d %H:%M:%S")
    series_end_sql = bucket_ends[-1].strftime("%Y-%m-%d %H:%M:%S")
    series_rows = list_walk_sessions_in_range(int(user["id"]), series_start_sql, series_end_sql)

    series: list[dict] = []
    for i, start in enumerate(bucket_starts):
        end = bucket_ends[i]
        bucket_rows = []
        for row in series_rows:
            ended = datetime.strptime(str(row["ended_at"]), "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
            if start <= ended < end:
                bucket_rows.append(row)

        if not bucket_rows:
            continue

        series.append(
            {
                "label": _series_bucket_label(period, start, end),
                "distance_km": round(sum(float(r["distance_km"]) for r in bucket_rows), 2),
                "elapsed_seconds": int(sum(int(r["elapsed_seconds"]) for r in bucket_rows)),
                "steps": int(sum(int(r["steps"]) for r in bucket_rows)),
            }
        )

    return {
        "period": period,
        "offset": offset,
        "period_label": period_label,
        "totals": totals,
        "sessions": rows,
        "series": series,
        "bounds": {
            "current_start": c_start.isoformat(),
            "current_end": c_end.isoformat(),
        },
    }


@app.get("/api/me/walk-analytics-overview")
def walk_analytics_overview(
    request: Request,
    day_offset: int = 0,
    week_offset: int = 0,
    month_offset: int = 0,
) -> dict:
    user = _require_user(request)
    user_id = int(user["id"])

    if day_offset < 0 or week_offset < 0 or month_offset < 0:
        raise HTTPException(status_code=400, detail="offsets must be >= 0")

    return {
        "day": {
            **_walk_period_stats(user_id, "daily", day_offset),
            "series": _walk_period_series_with_offset(user_id, "daily", day_offset),
            "offset": day_offset,
        },
        "week": {
            **_walk_period_stats(user_id, "weekly", week_offset),
            "series": _walk_period_series_with_offset(user_id, "weekly", week_offset),
            "offset": week_offset,
        },
        "month": {
            **_walk_period_stats(user_id, "monthly", month_offset),
            "series": _walk_period_series_with_offset(user_id, "monthly", month_offset),
            "offset": month_offset,
        },
    }


@app.get("/api/me/walk-sessions")
def my_walk_sessions(request: Request) -> dict:
    user = _require_user(request)
    rows = list_walk_sessions(int(user["id"]), limit=300)
    return {"sessions": rows}


@app.get("/api/me/walk-sessions/{walk_session_id}")
def my_walk_session_detail(walk_session_id: int, request: Request) -> dict:
    user = _require_user(request)
    row = get_walk_session(int(user["id"]), walk_session_id)
    if not row:
        raise HTTPException(status_code=404, detail="Walk session not found")

    if row.get("route_geojson"):
        row["route_geojson"] = json.loads(str(row["route_geojson"]))
    else:
        row["route_geojson"] = None

    return {"session": row}


@app.delete("/api/me/walk-sessions/{walk_session_id}")
def delete_my_walk_session(walk_session_id: int, request: Request) -> dict[str, bool]:
    user = _require_user(request)
    deleted = delete_walk_session(int(user["id"]), walk_session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Walk session not found")
    return {"ok": True}


@app.get("/api/me/metrics")
def my_metrics(request: Request, period: str = "weekly") -> dict:
    user = _require_user(request)

    try:
        c_start, c_end, p_start, p_end = _period_bounds(period)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # SQLite CURRENT_TIMESTAMP uses "YYYY-MM-DD HH:MM:SS". Keep query bounds in the same format.
    c_start_sql = c_start.strftime("%Y-%m-%d %H:%M:%S")
    c_end_sql = c_end.strftime("%Y-%m-%d %H:%M:%S")
    p_start_sql = p_start.strftime("%Y-%m-%d %H:%M:%S")
    p_end_sql = p_end.strftime("%Y-%m-%d %H:%M:%S")

    current_rows = list_route_sessions_in_range(int(user["id"]), c_start_sql, c_end_sql)
    previous_rows = list_route_sessions_in_range(int(user["id"]), p_start_sql, p_end_sql)

    current = _aggregate_sessions(current_rows)
    previous = _aggregate_sessions(previous_rows)

    totals_change_pct = {
        "distance_km": _calc_pct_change(current["totals"]["distance_km"], previous["totals"]["distance_km"]),
        "steps": _calc_pct_change(float(current["totals"]["steps"]), float(previous["totals"]["steps"])),
        "duration_min": _calc_pct_change(current["totals"]["duration_min"], previous["totals"]["duration_min"]),
    }

    profile_avg_change_pct: dict[str, dict[str, float | None]] = {}
    for profile in ("foot-walking",):
        profile_avg_change_pct[profile] = {}
        for key in ("distance_km", "steps", "duration_min"):
            profile_avg_change_pct[profile][key] = _calc_pct_change(
                float(current["by_profile"][profile]["avg_per_session"][key]),
                float(previous["by_profile"][profile]["avg_per_session"][key]),
            )

    return {
        "period": period,
        "current": current,
        "previous": previous,
        "totals_change_pct": totals_change_pct,
        "profile_avg_change_pct": profile_avg_change_pct,
        "bounds": {
            "current_start": c_start.isoformat(),
            "current_end": c_end.isoformat(),
            "previous_start": p_start.isoformat(),
            "previous_end": p_end.isoformat(),
        },
    }


@app.post("/api/route")
def route(payload: RouteRequest) -> dict:
    try:
        result = build_round_trip(
            lat=payload.lat,
            lon=payload.lon,
            target_mode=payload.target_mode,
            target_value=payload.target_value,
            variation_seed=payload.variation_seed,
        )

        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except requests.HTTPError as exc:
        detail = "OpenRouteService request failed"
        if exc.response is not None and exc.response.text:
            detail = exc.response.text[:500]
        raise HTTPException(status_code=502, detail=detail)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {exc}")


@app.post("/api/me/routes/save")
def save_route(payload: SaveRouteRequest, request: Request) -> dict[str, int]:
    user = _require_user(request)

    route_id = create_route_session(
        user_id=int(user["id"]),
        profile="foot-walking",
        route_name=payload.route_name.strip() if payload.route_name else None,
        target_mode=payload.target_mode,
        target_value=payload.target_value,
        start_lat=payload.lat,
        start_lon=payload.lon,
        distance_km=float(payload.distance_km),
        duration_min=float(payload.duration_min),
        steps=int(payload.steps),
        route_geojson=json.dumps(payload.route_geojson),
    )
    return {"id": route_id}
