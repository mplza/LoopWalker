# Loop Walker

Build walking-only loop routes from a selected map point by target minutes, kilometers, or steps.

Includes account flow, route generation, saved history, and favorites.

## What this app does

- Uses OpenStreetMap tiles in Leaflet.
- Uses OpenRouteService (OSM-based routing) to generate loop routes.
- Uses walking mode only.
- Starts with a welcome page that asks the user to create an account or log in.
- After login, shows two tabs:
  - Generate Route: choose target type and value, and generate from the map
  - My Routes: view all previous routes and manage favorites
- Lets user choose:
  - target mode: minutes, kilometers, or steps
  - target value
- Returns route on the map plus estimated:
  - minutes
  - kilometers
  - steps
- Supports user accounts:
  - register/login/logout
  - automatic route history per user
  - load past routes back on the map
- Supports favorites and analytics:
  - mark/unmark saved routes as favorites
  - view favorite routes and replay them on the map
- See the live app hosted on Render here: https://loopwalker.onrender.com/

## Setup

1. Install dependencies:

```bash
python -m pip install -r requirements.txt
```

2. Create `.env` from template:

```bash
cp .env.example .env
```

3. Add your OpenRouteService API key:

```env
ORS_API_KEY=your_openrouteservice_api_key_here
```

Get a free API key: https://openrouteservice.org/dev/#/signup

4. Run the app:

```bash
python -m uvicorn src.app:app --reload
```

5. Open in browser:

```text
http://127.0.0.1:8000
```

The app creates a local SQLite database automatically at `data/app.db`.

## How to use

1. Click map to set start point.
2. Create account or log in.
3. In `Generate Route`, choose target type (minutes/kilometers/steps).
4. Enter target value and click `Generate route`.
5. Open `My Routes` to see saved routes and favorites.

## Notes

- Steps are estimates.
- Calories are not tracked.
- Route generation quality depends on OSM data and ORS API limits.

## API additions (Phase 1 + Phase 2)

- `POST /api/route`
- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/auth/me`
- `GET /api/me/routes`
- `GET /api/me/favorites`
- `POST /api/me/routes/{route_id}/favorite`
- `DELETE /api/me/routes/{route_id}/favorite`
- `GET /api/me/metrics?period=daily|weekly|monthly`
