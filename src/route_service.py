from __future__ import annotations

import math
import os
from dataclasses import dataclass

import requests

ORS_BASE_URL = "https://api.openrouteservice.org/v2/directions"

# Keep only options known to be acceptable for walking profile.
PEDESTRIAN_AVOID_FEATURES = ["ferries"]

# ORS waytype values that usually correspond to vehicle-oriented roads.
MAJOR_ROAD_WAYTYPES = {1, 2}

# Prefer regular streets and dedicated pedestrian infrastructure.
PREFERRED_WAYTYPES = {3, 4, 7}

# Penalize segments that are often poor for normal walking loops.
UNDESIRED_WAYTYPES = {0, 5, 8, 10}


@dataclass
class RouteMetrics:
    distance_km: float
    duration_min: float
    steps: int


def _get_api_key() -> str:
    api_key = os.getenv("ORS_API_KEY", "")
    if not api_key:
        raise ValueError("Missing ORS_API_KEY. Add it to your .env file.")
    return api_key


def _estimate_steps(distance_km: float) -> int:
    # Approximate average step length 0.78 m.
    return int(round((distance_km * 1000.0) / 0.78))


def _bearing_deg(a: list[float], b: list[float]) -> float:
    dx = float(b[0]) - float(a[0])
    dy = float(b[1]) - float(a[1])
    angle = math.degrees(math.atan2(dy, dx))
    return (angle + 360.0) % 360.0


def _angle_delta_deg(a: float, b: float) -> float:
    diff = abs(a - b) % 360.0
    return diff if diff <= 180.0 else 360.0 - diff


def _count_reverse_street_passes(
    geometry: dict | None,
    threshold_m: float = 18.0,
    min_gap: int = 10,
    opposite_tolerance_deg: float = 60.0,
) -> int:
    """Count points where the route walks over the same street in reverse.

    For each coordinate i (at least ``min_gap`` steps ahead), the function
    looks for an earlier coordinate j that is:

    1. Within ``threshold_m`` metres (same physical location / street), AND
    2. Being travelled in a heading that differs from the heading at j by
       more than ``180 - opposite_tolerance_deg`` degrees — i.e. the walker
       is heading in the opposite direction along that street segment.

    Only spatial proximity is not enough: a route legitimately crosses its
    own path at a single junction, which is fine. What we want to catch is
    walking *along* the same street in the *opposite* direction.
    """
    coords = []
    if geometry and geometry.get("type") == "LineString":
        coords = geometry.get("coordinates", []) or []
    n = len(coords)
    if n < min_gap + 2:
        return 0

    lat0 = math.radians(float(coords[0][1]))
    cos_lat = math.cos(lat0)
    mx = [float(c[0]) * 111320.0 * cos_lat for c in coords]
    my = [float(c[1]) * 111320.0 for c in coords]

    # Bearing at each step (use the segment leading *into* that point).
    bearings: list[float] = [0.0]  # dummy for index 0
    for k in range(1, n):
        bearings.append(_bearing_deg(coords[k - 1], coords[k]))

    count = 0
    th2 = threshold_m * threshold_m
    min_opposite = 180.0 - opposite_tolerance_deg  # must be >= this to count

    for i in range(min_gap, n):
        for j in range(0, i - min_gap):
            dx = mx[i] - mx[j]
            dy = my[i] - my[j]
            if dx * dx + dy * dy < th2:
                # Same location — now check if headings are opposite.
                heading_diff = _angle_delta_deg(bearings[i], bearings[j])
                if heading_diff >= min_opposite:
                    count += 1
                    break  # count at most once per point i
    return count


def _shape_quality(geometry: dict | None) -> dict[str, float]:
    coords = []
    if geometry and geometry.get("type") == "LineString":
        coords = geometry.get("coordinates", []) or []

    if len(coords) < 3:
        return {
            "u_turns": 99,
            "turns": 0,
            "turn_variety": 0,
            "reverse_street_passes": 99,
        }

    left_turns = 0
    right_turns = 0
    u_turns = 0

    prev_bearing = _bearing_deg(coords[0], coords[1])
    for i in range(2, len(coords)):
        curr_bearing = _bearing_deg(coords[i - 1], coords[i])
        delta = _angle_delta_deg(prev_bearing, curr_bearing)

        # Big heading reversals are treated as u-turn behavior.
        if delta >= 135.0:
            u_turns += 1
        # Count meaningful turns to favor street-rich routes.
        elif delta >= 18.0:
            signed = (curr_bearing - prev_bearing + 540.0) % 360.0 - 180.0
            if signed > 0:
                left_turns += 1
            elif signed < 0:
                right_turns += 1

        prev_bearing = curr_bearing

    turn_variety = min(left_turns, right_turns)
    reverse_street_passes = _count_reverse_street_passes(geometry)
    return {
        "u_turns": float(u_turns),
        "turns": float(left_turns + right_turns),
        "turn_variety": float(turn_variety),
        "reverse_street_passes": float(reverse_street_passes),
    }


def _score_candidate(route_data: dict, target_length_m: int) -> float:
    features = route_data.get("features", [])
    if not features:
        return float("inf")

    props = features[0].get("properties", {})
    summary = props.get("summary", {})
    distance_m = float(summary.get("distance", 0.0))
    geometry = features[0].get("geometry")
    shape = _shape_quality(geometry)
    major_road_ratio = _major_road_ratio(route_data)
    preferred_ratio = _waytype_ratio(route_data, PREFERRED_WAYTYPES)
    undesired_ratio = _waytype_ratio(route_data, UNDESIRED_WAYTYPES)

    target_err = abs(distance_m - float(target_length_m)) / max(1.0, float(target_length_m))

    # Lower score is better.
    # Very strongly punish u-turns and spatial backtracking (same-street
    # reversals), reward turn-rich and balanced routes, and penalize major
    # vehicle-road usage.
    major_road_penalty = major_road_ratio * 180.0
    if major_road_ratio > 0.35:
        major_road_penalty += 120.0

    undesired_way_penalty = undesired_ratio * 260.0
    preferred_way_bonus = preferred_ratio * 90.0

    # Normalise reverse-street-pass count relative to route length so short
    # and long routes are penalised proportionally.
    n_coords = max(1, len((geometry or {}).get("coordinates") or []))
    reverse_ratio = shape["reverse_street_passes"] / n_coords

    return (
        (shape["u_turns"] * 500.0)
        + (reverse_ratio * 800.0)
        + (target_err * 30.0)
        + major_road_penalty
        + undesired_way_penalty
        - (shape["turns"] * 2.5)
        - (shape["turn_variety"] * 6.0)
        - preferred_way_bonus
    )


def _major_road_ratio(route_data: dict) -> float:
    return _waytype_ratio(route_data, MAJOR_ROAD_WAYTYPES)


def _waytype_ratio(route_data: dict, selected_values: set[int]) -> float:
    features = route_data.get("features", [])
    if not features:
        return 0.0

    props = features[0].get("properties", {})
    extras = props.get("extras", {}) if isinstance(props, dict) else {}
    if not isinstance(extras, dict):
        return 0.0

    waytype_extra = extras.get("waytype") or extras.get("waytypes")
    if not isinstance(waytype_extra, dict):
        return 0.0

    summary = waytype_extra.get("summary", [])
    if not isinstance(summary, list) or not summary:
        return 0.0

    total = 0.0
    major = 0.0
    for item in summary:
        if not isinstance(item, dict):
            continue
        value = item.get("value")
        distance = float(item.get("distance", 0.0) or 0.0)
        total += distance
        if value in selected_values:
            major += distance

    if total <= 0:
        return 0.0
    return major / total


def _candidate_quality(route_data: dict, target_length_m: int) -> dict[str, float]:
    features = route_data.get("features", [])
    if not features:
        return {
            "score": float("inf"),
            "u_turns": 99.0,
            "major_road_ratio": 1.0,
        }

    props = features[0].get("properties", {})
    summary = props.get("summary", {})
    distance_m = float(summary.get("distance", 0.0))
    target_err = abs(distance_m - float(target_length_m)) / max(1.0, float(target_length_m))
    shape = _shape_quality(features[0].get("geometry"))
    major_ratio = _major_road_ratio(route_data)
    n_coords = max(1, len((features[0].get("geometry") or {}).get("coordinates") or []))
    reverse_ratio = shape.get("reverse_street_passes", 0.0) / n_coords
    return {
        "score": _score_candidate(route_data, target_length_m),
        "u_turns": float(shape.get("u_turns", 99.0)),
        "reverse_ratio": float(reverse_ratio),
        "major_road_ratio": float(major_ratio),
        "undesired_way_ratio": float(_waytype_ratio(route_data, UNDESIRED_WAYTYPES)),
        "preferred_way_ratio": float(_waytype_ratio(route_data, PREFERRED_WAYTYPES)),
        "target_err": float(target_err),
    }


def _request_round_trip_candidate(
    *,
    api_key: str,
    lon: float,
    lat: float,
    target_length_m: int,
    points: int,
    seed: int,
) -> dict:
    url = f"{ORS_BASE_URL}/foot-walking/geojson"
    headers = {
        "Authorization": api_key,
        "Content-Type": "application/json",
    }
    payload = {
        "coordinates": [[lon, lat]],
        "preference": "recommended",
        "extra_info": ["waytype"],
        "options": {
            "avoid_features": PEDESTRIAN_AVOID_FEATURES,
            "round_trip": {
                "length": target_length_m,
                "points": points,
                "seed": seed,
            }
        },
    }

    response = requests.post(url, headers=headers, json=payload, timeout=45)
    if response.ok:
        return response.json()

    # Some ORS builds reject avoid_features for specific profiles.
    # Retry once without avoid_features instead of failing hard.
    if response.status_code in {400, 422} and "avoid_features" in (response.text or ""):
        payload_no_avoid = {
            "coordinates": payload["coordinates"],
            "preference": payload["preference"],
            "extra_info": payload["extra_info"],
            "options": {
                "round_trip": payload["options"]["round_trip"],
            },
        }
        retry = requests.post(url, headers=headers, json=payload_no_avoid, timeout=45)
        retry.raise_for_status()
        return retry.json()

    response.raise_for_status()
    return response.json()


def build_round_trip(
    *,
    lat: float,
    lon: float,
    target_mode: str,
    target_value: float,
    variation_seed: int = 0,
) -> dict:
    api_key = _get_api_key()

    if target_mode not in {"hours", "minutes", "kilometers", "steps"}:
        raise ValueError("target_mode must be 'hours', 'minutes', 'kilometers', or 'steps'.")

    if target_value <= 0:
        raise ValueError("Target value must be greater than 0.")

    # ORS round_trip length expects meters.
    if target_mode == "kilometers":
        target_length_m = int(round(target_value * 1000.0))
    elif target_mode == "steps":
        # Convert desired step count to approximate distance in meters.
        target_length_m = int(round(target_value * 0.78))
    elif target_mode == "minutes":
        # Rough conversion from time to distance for walking (~5 km/h).
        speed_kmh = 5.0
        target_length_m = int(round((target_value / 60.0) * speed_kmh * 1000.0))
    else:
        # Convert hours directly to distance for walking (~5 km/h).
        speed_kmh = 5.0
        target_length_m = int(round(target_value * speed_kmh * 1000.0))

    # Keep practical bounds for API round trips.
    target_length_m = max(1000, min(target_length_m, 120000))

    # Generate multiple loop candidates and select the one with fewer u-turns
    # and richer left/right turn structure.
    candidates: list[dict] = []
    last_error: Exception | None = None
    seed_base = abs(int(variation_seed))
    point_options = (6, 7, 8, 9, 10, 11, 12)
    seed_options = tuple(base + seed_base for base in (3, 11, 19, 29, 37, 47, 59, 71))
    for points in point_options:
        for seed in seed_options:
            try:
                data = _request_round_trip_candidate(
                    api_key=api_key,
                    lon=lon,
                    lat=lat,
                    target_length_m=target_length_m,
                    points=points,
                    seed=seed,
                )
                if data.get("features"):
                    candidates.append(data)
            except requests.RequestException as exc:
                last_error = exc

    if not candidates:
        if last_error is not None:
            raise last_error
        raise ValueError("No route returned by OpenRouteService.")

    strict_candidates: list[dict] = []
    strict_scores: list[float] = []
    fallback_scores: list[float] = []
    for candidate in candidates:
        q = _candidate_quality(candidate, target_length_m)
        fallback_scores.append(float(q["score"]))
        if (
            q["u_turns"] <= 0.0
            and q["reverse_ratio"] <= 0.04
            and q["major_road_ratio"] <= 0.25
            and q["undesired_way_ratio"] <= 0.35
            and q["preferred_way_ratio"] >= 0.40
        ):
            strict_candidates.append(candidate)
            strict_scores.append(float(q["score"]))

    if strict_candidates:
        best_idx = min(range(len(strict_candidates)), key=lambda i: strict_scores[i])
        data = strict_candidates[best_idx]
    else:
        # Fallback if strict filtering cannot find any route in the area.
        best_idx = min(range(len(candidates)), key=lambda i: fallback_scores[i])
        data = candidates[best_idx]

    features = data.get("features", [])
    if not features:
        raise ValueError("No route returned by OpenRouteService.")

    props = features[0].get("properties", {})
    summary = props.get("summary", {})

    distance_m = float(summary.get("distance", 0.0))
    duration_s = float(summary.get("duration", 0.0))

    distance_km = round(distance_m / 1000.0, 2)
    duration_min = round(duration_s / 60.0, 1)
    steps = _estimate_steps(distance_km)

    metrics = RouteMetrics(
        distance_km=distance_km,
        duration_min=duration_min,
        steps=steps,
    )

    return {
        "geojson": data,
        "metrics": {
            "distance_km": metrics.distance_km,
            "duration_min": metrics.duration_min,
            "steps": metrics.steps,
        },
    }
