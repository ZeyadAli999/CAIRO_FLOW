# CairoFlow Deployment Guide

This guide documents the safe ways to run CairoFlow locally, in Docker,
and on Render. The original dataset in `data/raw/` remains unchanged; the
SQLite database is seeded from those files on first run.

## Local Setup

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

## Local Run

```powershell
.\.venv\Scripts\python.exe app.py
```

Open:

```text
http://127.0.0.1:8050
```

## Test Command

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests
```

Current verified result:

```text
151 passed
```

## Production Start Command

CairoFlow exposes the Flask WSGI server as `server` for production
process managers:

```bash
gunicorn app:server
```

For hosted environments that provide a `PORT` variable, bind explicitly:

```bash
gunicorn app:server --bind 0.0.0.0:$PORT
```

## Health Check

When the app is running:

```powershell
curl -s http://127.0.0.1:8050/healthz | python -m json.tool
```

The endpoint reports app health details such as callbacks, assets, and
test status.

## Docker Build

```powershell
docker build -t cairoflow .
```

## Docker Run

```powershell
docker run --rm -p 8050:8050 cairoflow
```

Then open:

```text
http://127.0.0.1:8050
```

## Render Deployment

1. Push the project to GitHub.
2. In Render, create a new Web Service from the GitHub repository.
3. Render can use `render.yaml` automatically.
4. Confirm the build command:

```bash
pip install -r requirements.txt
```

5. Confirm the start command:

```bash
gunicorn app:server --bind 0.0.0.0:$PORT
```

6. Confirm the health check path:

```text
/healthz
```

7. After deployment succeeds, add the live URL to `README.md` and
   `docs/submission_notes.md`.

## Notes

- Do not commit local virtual environments, caches, temporary folders, or
  generated `data/cairo.db` into the Docker image.
- The Docker image uses the existing `requirements.txt`.
- The app still runs locally through `app.py`; production uses
  `gunicorn app:server`.
