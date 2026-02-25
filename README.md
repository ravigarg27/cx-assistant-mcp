# CX Assistant MCP Server

Query Cisco CX Assistant (production and stage) directly from Cursor using natural language. No API keys, no curl, no JavaScript — just type your question.

## Prerequisites

- Python 3.11 or higher (`python --version` to check)
- [Cursor](https://cursor.sh) editor
- **Mac only:** [Google Chrome](https://www.google.com/chrome/) installed — required for Cisco Duo device trust during login

## Setup (one time per machine)

### 1. Get the project

Copy the `cx-assistant-mcp` folder to your machine, for example:

**Windows:** `C:\Users\<your-name>\Projects\cx-assistant-mcp`

**Mac:** `/Users/<your-name>/Projects/cx-assistant-mcp`

### 2. Install dependencies

Open a terminal in the project folder and run:

**Windows:**
```bash
python -m venv venv
venv\Scripts\pip install -r requirements.txt
venv\Scripts\python -m playwright install chromium
```

**Mac:**
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

> **Mac note:** Login uses your real installed Chrome (required for Cisco Duo device trust). If Chrome is not installed, it falls back to bundled Chromium, which may fail Duo authentication. Install [Google Chrome](https://www.google.com/chrome/) if login fails.

### 3. Configure Cursor

Open this file (create it if it doesn't exist):

**Windows:** `C:\Users\<your-name>\AppData\Roaming\Cursor\User\mcp.json`

**Mac:** `~/.cursor/mcp.json`

Add this configuration (replace `<your-name>` with your username):

**Windows:**
```json
{
  "mcpServers": {
    "cx-assistant": {
      "command": "C:/Users/<your-name>/Projects/cx-assistant-mcp/venv/Scripts/python.exe",
      "args": ["C:/Users/<your-name>/Projects/cx-assistant-mcp/server.py"]
    }
  }
}
```

**Mac:**
```json
{
  "mcpServers": {
    "cx-assistant": {
      "command": "/Users/<your-name>/Projects/cx-assistant-mcp/venv/bin/python",
      "args": ["/Users/<your-name>/Projects/cx-assistant-mcp/server.py"]
    }
  }
}
```

Restart Cursor. Go to **Settings → Features → MCP** — you should see `cx-assistant` listed with 5 tools.

### 4. Login

In Cursor chat, type:
```
Login to CX Assistant production
```

A browser window opens. Complete your Cisco Duo login. The window closes automatically. You're ready.

---

## Using the Tools

### Ask a free-form question (stage)
```
Ask stage: What are the adoption barriers for United Nations CAV BU 104461?
```

### Ask using pre-built questions (production)
```
Ask production structured: What is the renewal risk for deal D-72595030?
```

### Ask a free-form question (production)
```
Ask production open: Summarize my top 10 at-risk renewals
```

### Re-authenticate (when session expires)
```
Login to CX Assistant stage
```

---

## Available Tools

| Tool | Environment | Question type | Best for |
|------|-------------|---------------|----------|
| `ask_production_structured` | Production | 116 pre-built | Known question types with deal IDs, customer names |
| `ask_production_open` | Production | Free-form | Ad-hoc questions, exploration |
| `ask_stage_structured` | Stage | 116 pre-built | Testing pre-built questions against stage data |
| `ask_stage_open` | Stage | Free-form | Testing new questions, exploring stage data |
| `login` | Both | — | Authenticate or re-authenticate |

---

## Tips

- **Use CAV BU IDs** for consistent results: `United Nations CAV BU 104461` is more reliable than just `United Nations`
- **Deal IDs** should be in format `D-XXXXX` (e.g. `D-72595030`)
- **Session cookies expire** — if you get an authentication error, run `Login to CX Assistant production` again
- **Stage vs Production**: Use stage for testing and exploration; use production for real customer data
- **Browser selection**: On Mac, login uses real Chrome (for Duo device trust) with bundled Chromium as fallback. On Windows, real Edge is tried first, then bundled Chromium. Both production and stage use the same browser logic.

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| MCP not showing in Cursor | Check `mcp.json` path and restart Cursor |
| "Not authenticated" error | Run `Login to CX Assistant production` |
| Browser doesn't open | Run `playwright install chromium` in the project folder |
| "Could not find matching question" | Use `ask_*_open` for free-form questions instead |
| Login browser doesn't close | Complete Duo login — browser closes automatically after redirect |
| Duo login fails on Mac | Install [Google Chrome](https://www.google.com/chrome/) — bundled Chromium lacks device trust support |
