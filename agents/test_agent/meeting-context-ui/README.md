# Meeting Context UI (local dev only)

Two single-file, dependency-free pages matching the "Pre-Meeting Agent
1.pdf" UI mockup (2026-10-30): `dashboard.html` (landing page — past decks +
"Prepare for new meeting") and `index.html` (the Meeting Context form).
Like `chat-ui/`, these are throwaway testing aids, not a product frontend —
they exist to drive and visually check `context_api.py` end to end. The
third mockup screen (deck review/chat with Agent/Changes/Audit tabs) is not
built — it needs a real generated deck, which needs agents that don't exist
yet (Data Analyst, Slide Generator, Builder).

This UI only talks to the plain REST endpoints under `/api/*`
(`context_api.py`). It never calls `/invocations` and cannot trigger a
Portkey/model call — see `context_api.py`'s module docstring.

## Run it

1. Start the agent app (same as `chat-ui/`):
   ```
   uvicorn app:app --host 0.0.0.0 --port 8081
   ```
   Note: this requires `ai-foundry-platform-sdk` to actually be installed,
   which (as of this writing) needs the private GitLab PyPI index configured
   — see the `test-agent-local-dev-setup` memory note. If you just want to
   exercise the Meeting Context API/UI without that dependency, run the
   router standalone instead:
   ```
   pip install fastapi "uvicorn[standard]"
   python -c "
   from fastapi import FastAPI
   from context_api import router
   app = FastAPI()
   app.include_router(router, prefix='/api')
   import uvicorn
   uvicorn.run(app, host='0.0.0.0', port=8081)
   "
   ```
   Either way, nothing in this path imports the agent/model code.

2. Open `meeting-context-ui/dashboard.html` directly, or serve the folder:
   ```
   python3 -m http.server 5501 --directory meeting-context-ui
   ```
   then visit `http://localhost:5501/dashboard.html`. "Prepare for new
   meeting" links to `index.html`; the form's back arrow links back.

3. The "API base" field (top of `index.html`) defaults to
   `http://localhost:8081/api` and is saved in `localStorage`, which
   `dashboard.html` also reads.

## What it covers

- `dashboard.html`: `GET /decks` — static mock "previous presentations"
  (`decks_mock_data.py`), matching the mockup's example cards exactly.
- `index.html`: Customer / Season dropdowns and focus-product suggestions
  are DB-backed questions (per the user) — served by `data_access.py`, which
  runs the `sql_registry.py` templates either for real against Databricks
  (`databricks_executor.py`, if `DATABRICKS_SERVER_HOSTNAME`/`_HTTP_PATH`/
  `_TOKEN` are set in `.env`) or against the local `dbx-data` sample
  otherwise (NOT the real warehouse — see `data_access.py`'s docstring on
  why the counts won't match without real credentials). Every list response
  includes a `data_source` field (`"databricks"` or `"local-sample-csv"`) so
  the UI always shows which one is actually active. Meeting type stays
  static (`mock_data.py`), per the user. Focus-product suggestions re-fetch
  scoped to the selected customer.
- Live "N of 7 required fields ready" indicator, backed by `readiness.py`'s
  deterministic check (not an LLM judgment — see that module's docstring).
- Auto-saving draft (debounced) + Confirm & Next, calling
  `POST /meeting-context/draft`, `PUT .../draft`, and `POST .../confirm`.

Steps 2-6 of the wizard past Meeting Context are not implemented —
"Confirm & Next" just reports that step 2 isn't built yet.
