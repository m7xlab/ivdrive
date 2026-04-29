# Chrome DevTools MCP — QA Agent Setup & Usage Guide

This document tells you (the agent) how to install Chrome DevTools MCP, connect it to a local development server, authenticate against the app, and run a structured QA pass that catches real runtime issues — including the React errors that static analysis misses.

---

## 1. What this is and why we need it

Chrome DevTools MCP is an official Model Context Protocol server from Google that gives an AI agent control over a live Chrome browser. It is built on top of Puppeteer and the Chrome DevTools Protocol, and exposes ~29 tools covering navigation, clicking, form filling, console inspection, network monitoring, performance tracing, and screenshots.

**Why we use it for QA**: tools like Lighthouse, ESLint, or "React Doctor" perform static or post-build checks. They cannot see runtime errors that only surface when JavaScript actually executes in a real browser — hydration mismatches, hook-rule violations, undefined property access, failed network calls, broken event handlers. This MCP gives the QA agent eyes on the actual rendered application.

---

## 2. Prerequisites

Before installing, confirm the host machine has:

- **Node.js 22.12.0 or newer** (required by `chrome-devtools-mcp`)
- **Google Chrome** (current stable channel) — Chromium-based forks are not officially supported
- **The dev server is runnable** on a known localhost port (e.g. `http://localhost:3000`)
- Claude Code, Cursor, or another MCP-capable agent client installed

---

## 3. Installation

### 3.1 Recommended: install for Claude Code

From a terminal on the developer's machine:

```bash
claude mcp add chrome-devtools --scope user npx chrome-devtools-mcp@latest
```

This registers the server globally for your user. Restart Claude Code after installing.

### 3.2 Alternative: manual config

If your client uses a JSON config file (Cursor, generic MCP clients, etc.), add:

```json
{
  "mcpServers": {
    "chrome-devtools": {
      "command": "npx",
      "args": ["chrome-devtools-mcp@latest"]
    }
  }
}
```

### 3.3 Verify the install

In a fresh chat, ask the agent:

> List the available chrome-devtools MCP tools.

You should see tools like `navigate_page`, `click`, `fill`, `take_snapshot`, `list_console_messages`, `list_network_requests`, `performance_start_trace`. If they're missing, the MCP server didn't load — restart the client.

---

## 4. Recommended startup flags

For a dev/QA workflow, edit the args list to pass these flags:

```json
{
  "mcpServers": {
    "chrome-devtools": {
      "command": "npx",
      "args": [
        "chrome-devtools-mcp@latest",
        "--isolated",
        "--no-usage-statistics"
      ]
    }
  }
}
```

| Flag | Why |
|------|-----|
| `--isolated` | Each session uses a fresh temp profile. Avoids the "browser is already running" error when a prior Chrome instance still holds the default profile dir. |
| `--no-usage-statistics` | Disables telemetry to Google. Use if your org requires it. |
| `--browser-url=http://127.0.0.1:9222` | Connect to an already-running Chrome instance instead of letting the MCP launch its own. Use this when you need a persistent profile (see §5). |
| `--headless` | Run Chrome with no visible window. Use for CI; avoid for local dev so you can watch the agent work. |

---

## 5. Handling authentication

Most real apps require login. There are two clean approaches.

### 5.1 Persistent profile (recommended for local dev)

Start Chrome yourself with remote debugging on a dedicated profile, log in once manually, then point the MCP at it. The login persists across sessions.

**macOS:**
```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --user-data-dir="$HOME/.chrome-debug-profile"
```

**Linux:**
```bash
google-chrome \
  --remote-debugging-port=9222 \
  --user-data-dir="$HOME/.chrome-debug-profile"
```

**Windows (PowerShell):**
```powershell
& "C:\Program Files\Google\Chrome\Application\chrome.exe" `
  --remote-debugging-port=9222 `
  --user-data-dir="$env:USERPROFILE\.chrome-debug-profile"
```

Then in your MCP config use:

```json
"args": ["chrome-devtools-mcp@latest", "--browser-url=http://127.0.0.1:9222"]
```

Log into your app **once** in that Chrome window. The session cookie stays on disk in `.chrome-debug-profile`. Every future agent run reuses it — no re-login required.

> **Security note**: anything inside that Chrome window is reachable by the agent. Do not browse personal accounts in this profile. Use it only for QA against your dev environments.
>
> Chrome 136+ blocks remote debugging on the default profile, so the dedicated `--user-data-dir` is mandatory.

### 5.2 Scripted login

If you want the agent to test the login flow itself, give it test credentials via env vars and let it drive the form. This is slower but exercises the auth path. Example prompt to the agent:

> Navigate to http://localhost:3000/login. Fill the email field with $TEST_EMAIL and password field with $TEST_PASSWORD. Click the submit button. Wait for navigation. Verify console is clean.

For local dev, **5.1 is preferred** — you're testing the app, not the login.

---

## 6. The core QA tool set

The agent should know these tools by name and purpose. Prefer `take_snapshot` (text accessibility tree) over `take_screenshot` whenever possible — it's faster, cheaper, and lets you reference elements by `uid`.

**Navigation & lifecycle**
- `new_page` — open a URL in a new tab
- `navigate_page` — go to URL, back, forward, or reload in the current tab
- `list_pages`, `select_page`, `close_page` — manage tabs
- `wait_for` — wait for text/element/condition before continuing

**Interaction**
- `click` — click an element by `uid` from the latest snapshot
- `fill`, `fill_form` — type into inputs
- `hover`, `drag`, `press_key`, `upload_file`, `handle_dialog`

**Inspection (the important ones for QA)**
- `take_snapshot` — accessibility-tree text dump with element `uid`s
- `take_screenshot` — visual capture (use sparingly)
- `list_console_messages` — **critical**: every `console.error`, warning, unhandled rejection
- `list_network_requests` — all requests, status codes, timings
- `get_network_request` — full request/response body for one request
- `evaluate_script` — run arbitrary JS in the page

**Performance**
- `performance_start_trace` / `performance_stop_trace` — record a trace
- `performance_analyze_insight` — get LCP, CLS, TBT, etc. from the trace

**Emulation**
- `resize_page` — test responsive breakpoints
- `emulate` — mobile devices, throttled CPU/network

---

## 7. The QA workflow

Follow this loop for every page or flow you test. Do not skip the console check — that's where the React errors live.

```
1. navigate_page → target URL
2. wait_for → page-specific ready signal (text, element, network idle)
3. take_snapshot → grab the a11y tree
4. list_console_messages → FAIL if any error/warning
5. list_network_requests → FAIL on any 4xx/5xx (excluding allow-listed URLs)
6. interact (click/fill/etc.) using uids from the snapshot
7. After each interaction: re-run steps 4 and 5
8. Record findings in a structured report
```

### Pass/fail criteria

A page passes only if **all** of these hold:

- No `error`-level console messages
- No `warning`-level messages from React (hydration, key warnings, hook warnings, deprecated lifecycle)
- No unhandled promise rejections
- No 4xx or 5xx network responses (except those explicitly expected and documented)
- All visible interactive elements (buttons, links, form inputs) reachable in the snapshot
- Critical user actions (submit, navigate, etc.) do not throw and produce the expected DOM change

---

## 8. Routes and flows to cover

Adapt this checklist to your app. Every route should run the workflow in §7.

- [ ] Public landing page
- [ ] Login flow (or session restored via persistent profile)
- [ ] Authenticated home / dashboard
- [ ] Each primary feature route (list, detail, create, edit, delete)
- [ ] Error states: 404 page, forced 500, offline behavior
- [ ] Forms: empty submit, invalid input, valid submit
- [ ] Mobile viewport via `resize_page` to 375×812 — repeat the dashboard + one form
- [ ] One performance trace on the heaviest route — record LCP and TBT

---

## 9. Reporting format

After the run, write a report to `qa-report.md` in the project root. Use this structure:

```markdown
# QA Report — <ISO date>

## Summary
- Routes tested: N
- Passed: N
- Failed: N
- Critical issues: N

## Failures

### <Route or flow name>
- **Severity**: critical | high | medium | low
- **Type**: console-error | network-error | broken-interaction | visual | performance
- **Evidence**:
  - Console: `<exact message + stack>`
  - Network: `<method> <url> → <status>`
  - Snapshot excerpt: `<relevant uid + text>`
- **Reproduction**:
  1. Navigate to /…
  2. Click …
  3. Observe …
- **Suggested area**: `<file or component name if inferable from stack>`

## Passed routes
- /
- /dashboard
- …

## Performance
- Route: /<heaviest>
- LCP: Xms
- TBT: Xms
- CLS: X
```

The dev agents read this file and act on it. **The QA agent does not fix bugs** — separating roles keeps the QA agent honest and prevents it from rationalizing problems away.

---

## 10. Quick-start prompts

Copy-paste these into the agent to verify the setup works.

**Smoke test** (no app needed):
> Using chrome-devtools MCP, navigate to https://example.com, take a snapshot, and list console messages.

**Localhost smoke test**:
> Using chrome-devtools MCP, navigate to http://localhost:3000. Wait for the page to be interactive. Take a snapshot. List all console messages and network requests. Report anything that is not a 200/304 or that logs an error.

**Full QA pass**:
> Run the QA workflow defined in CHROME_DEVTOOLS_MCP_QA_GUIDE.md §7 against routes /, /login, /dashboard, /settings on http://localhost:3000. Use the persistent Chrome profile — the user is already logged in. Write findings to qa-report.md using the format in §9. Do not modify any source files.

---

## 11. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `The browser is already running` | Two Chrome instances sharing one profile dir | Add `--isolated` to MCP args, or kill the stray Chrome |
| `Missing X server` (Linux) | Wayland without X | Run with `xvfb-run`, or start Chrome yourself with `--ozone-platform=wayland` and use `--browser-url` |
| MCP launches its own Chrome instead of using yours | `--browser-url` not set | Add `--browser-url=http://127.0.0.1:9222` to the args |
| Tools not visible in agent | MCP server didn't load | Restart the client; check `claude mcp list` |
| `take_snapshot` returns empty | Page hasn't finished loading | Add a `wait_for` step before snapshotting |
| Auth lost between runs | Using `--isolated` defeats persistent profile | Drop `--isolated` and use `--browser-url` against your own Chrome |

---

## 12. Operating principles for the QA agent

- **Console is law.** A clean Lighthouse score with a console error is still a failure.
- **Snapshots before screenshots.** Text is faster, cheaper, and gives you `uid`s for clicks.
- **Re-check after every interaction.** Errors often appear after a click, not on first paint.
- **Don't fix; report.** The QA role is investigative. Bug-fixing is a different agent's job.
- **Bound your run.** Cap the number of routes per session. If something is deeply broken, stop and report rather than thrashing.
- **Treat warnings as failures by default.** React warnings about keys, hooks, hydration, and deprecated APIs are real bugs — let the dev agent decide if they're acceptable, not the QA agent.