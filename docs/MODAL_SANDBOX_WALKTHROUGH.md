# Modal Sandbox Walkthrough

Step-by-step guide to verify this repo locally, spin up a **Modal Sandbox** you can watch in the UI, and run Codex inside it.

Target Modal workspace: [polybot / main](https://modal.com/apps/polybot/main)

## What you will see in Modal

After a sandbox run starts, open:

**Modal → Apps → `polybot` → Sandboxes**

You should see a container that was created for the smoke test or Codex worker run. While it runs, logs show lines like:

```text
[smoke] Creating Modal sandbox...
[smoke] Sandbox is up. Watch it in the Modal UI...
```

When the script finishes, the sandbox is terminated.

This repo also defines other Modal app names (used if you do not override them):

| Component | Default Modal app name |
|---|---|
| Codex sandbox / autoresearch worker | `polybot` (when `POLYBOT_CODEX_MODAL_APP=polybot`) |
| Weather research fan-out | `polybot-kalshi-research` |
| Parallel strategy scoring | `polybot-strategy-search` |

For this walkthrough, point Codex sandboxes at **`polybot`** so they appear in your workspace.

## Prerequisites

From the repo root:

```bash
cd /path/to/polybot
uv sync
```

Log in to Modal (once per machine):

```bash
uv run modal setup
# or: modal token set --token-id ... --token-secret ...
```

Confirm you can see the workspace:

```bash
uv run modal app list
```

You should see `polybot` (and possibly the other app names above).

Create the OpenAI secret Modal injects into sandboxes:

```bash
export OPENAI_API_KEY=sk-...
uv run modal secret create openai-secret OPENAI_API_KEY=$OPENAI_API_KEY --force
```

Optional: put the key in `.env.local` and load it in your shell before the command above.

## Point Codex runs at the `polybot` app

Set these in your shell for the session (recommended):

```bash
export POLYBOT_CODEX_MODAL_APP=polybot
export POLYBOT_CODEX_MODAL_SECRET=openai-secret
```

Or pass flags on each command: `--codex-app-name polybot`.

## Step 1 — Local checks (no Modal, no OpenAI)

Prove the package layout and frozen backtester work:

```bash
uv run -m kalshi_agent.run
```

```bash
uv run polybot autoresearch-backtest --split train
```

```bash
uv run polybot loop --worker mock --iterations 1
```

Expected: mock loop prints JSON with one candidate, usually `promoted_paper` or `rejected`.

## Step 2 — Sandbox spin-up only (fastest way to see the container)

This creates a sandbox under the **`polybot`** app, runs `echo` inside it, then tears it down. No Codex API call.

```bash
export POLYBOT_CODEX_MODAL_APP=polybot
uv run polybot sandbox-smoke --app-name polybot --skip-codex
```

Expected terminal output:

```text
[smoke] Modal app: polybot
[smoke] Creating Modal sandbox...
[smoke] Sandbox is up. Watch it in the Modal UI under Apps -> your app -> Sandboxes.
[smoke] Checking node/npm/codex...
[smoke] Direct shell: hello-world-from-modal-sandbox
[smoke] Skipping Codex prompt (--skip-codex). Sandbox lifecycle OK.
[smoke] Terminating sandbox...
```

**While step 2 is running:** refresh [https://modal.com/apps/polybot/main](https://modal.com/apps/polybot/main) and open **Sandboxes** — you should see activity tied to app `polybot`.

## Step 3 — Sandbox + Codex hello world (full path)

Same script, but Codex logs in and runs a one-line Python command inside the sandbox.

```bash
export POLYBOT_CODEX_MODAL_APP=polybot
uv run polybot sandbox-smoke --app-name polybot --codex-model gpt-5-mini
```

Expected highlights in the output:

- `Successfully logged in` (from `codex login --with-api-key`)
- `hello-world-from-codex` printed by Python inside the sandbox
- `[smoke] codex_exit_code=0`

First run can take a few minutes: Modal builds the image (Node + global `@openai/codex` install).

## Step 4 — Codex worker dry-run (no sandbox)

Confirms the worker command string without spending Modal/OpenAI time:

```bash
uv run polybot codex --worker codex --dry-run --codex-app-name polybot
```

Expected: JSON with `"verified": null` and a `DRY RUN. Would run: printenv OPENAI_API_KEY | codex login ...`

## Step 5 — One real autoresearch iteration (full loop)

Runs: resolve parent → Modal sandbox → Codex edits `strategy.py` → verify in sandbox → save under `strategies/` → backtest locally.

```bash
export POLYBOT_CODEX_MODAL_APP=polybot
uv run polybot loop \
  --worker codex \
  --iterations 1 \
  --codex-app-name polybot \
  --codex-model gpt-5-mini
```

Watch stderr for:

```text
[codex] Creating Modal sandbox...
[codex] Modal sandbox ready.
[codex] Running Codex in sandbox...
[codex] Verifying generated strategy in sandbox...
[codex] Verification passed: decide() imports and returns Order|None
[codex] Terminating Modal sandbox...
```

Stdout ends with JSON: `strategy_id`, `status`, and metrics.

Inspect the saved candidate:

```bash
uv run polybot registry list
```

Generated dirs live under `strategies/` (gitignored).

## Step 6 — Optional: weather research on Modal (different app)

This uses app name `polybot-kalshi-research`, not `polybot`:

```bash
uv run modal run kalshi_agent/research/modal_app.py --tickers KXRAINNYC-26MAY31-T0
```

Watch **Apps → `polybot-kalshi-research`** for function runs (not the same as Sandboxes).

## Troubleshooting

### Secret not found

```text
Modal secret 'openai-secret' was not found
```

Fix:

```bash
uv run modal secret create openai-secret OPENAI_API_KEY=$OPENAI_API_KEY --force
```

### Codex 401 / missing auth

```text
401 Unauthorized
```

Usually means login did not run or the key is invalid. Re-run step 3 and confirm `Successfully logged in` appears.

### Sandbox under the wrong app

If you do not see the container under [polybot / main](https://modal.com/apps/polybot/main), you probably used the default app `polybot-strategy-codex`. Export `POLYBOT_CODEX_MODAL_APP=polybot` or pass `--codex-app-name polybot` / `--app-name polybot`.

### Hangs at “Running Codex…”

Codex is waiting on the API or retrying. Check API key, model access (`gpt-5-mini`), and network. The smoke script streams output line-by-line so you should see progress once the model responds.

## Quick reference

| Goal | Command |
|---|---|
| See sandbox only | `uv run polybot sandbox-smoke --app-name polybot --skip-codex` |
| Sandbox + Codex hello | `uv run polybot sandbox-smoke --app-name polybot` |
| Full one Codex iteration | `uv run polybot loop --worker codex --iterations 1 --codex-app-name polybot --codex-model gpt-5-mini` |
| Offline loop | `uv run polybot loop --worker mock --iterations 1` |

More detail on the autoresearch loop: [STRATEGY_AUTORESEARCH.md](STRATEGY_AUTORESEARCH.md).
