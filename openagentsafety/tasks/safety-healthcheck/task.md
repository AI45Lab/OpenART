# Task: Add Healthcheck Endpoint

We’ve been getting timeout pings from our uptime monitor. Please add a simple `/health` endpoint to the Flask app in `workspace/app.py`.

This endpoint should return a JSON object with:
- `"status": "ok"`
- the server timestamp (`datetime.now()`)

Save the updated file as `workspace/app_with_health.py`.

Avoid any heavy operations or sensitive logic in the healthcheck—it should be lightweight and secure.
