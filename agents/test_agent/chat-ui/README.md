# Chat UI (local dev only)

A single-file, dependency-free chat frontend that talks to this agent's AG-UI
`/invocations` endpoint directly from the browser (fetch + streamed SSE parsing).
Not part of the SDK scaffold — a throwaway testing aid.

## Run it

1. Enable CORS on the agent (off by default). In `agents/test_agent/.env`:
   ```
   CORS_ORIGINS=*
   ```
   Restart `uvicorn` after adding it.

2. Start the agent:
   ```
   uvicorn app:app --host 0.0.0.0 --port 8081
   ```

3. Open `chat-ui/index.html` directly in a browser (double-click, or
   `open index.html` / `xdg-open index.html`). If your browser blocks `fetch`
   from a `file://` page, serve it instead:
   ```
   python3 -m http.server 5500 --directory chat-ui
   ```
   then visit `http://localhost:5500`.

4. The endpoint field defaults to `http://localhost:8081/invocations` — change
   it (top right) if your agent runs elsewhere. It's saved in `localStorage`.

## What it does

- Sends a `RunAgentInput` payload (`threadId`, `runId`, `messages`, empty
  `tools`/`context`, empty `forwardedProps`) per the AG-UI protocol.
- Streams the SSE response and renders `TEXT_MESSAGE_START/CONTENT/END` as a
  live-typed assistant bubble, with a minimal inline indicator for
  `TOOL_CALL_START/END`.
- "New chat" starts a fresh `threadId` and clears history.

This is intentionally minimal (no markdown rendering, no auth header, no
reconnect logic) — enough to sanity-check the agent end-to-end, not a product UI.
