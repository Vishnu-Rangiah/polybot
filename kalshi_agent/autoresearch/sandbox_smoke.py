"""Spin up a disposable Modal Sandbox and optionally run a tiny Codex prompt.

Use this to verify Modal auth, secrets, image build, and sandbox lifecycle
before running the full autoresearch loop.

Example (targets the polybot Modal app / workspace):

    export POLYBOT_CODEX_MODAL_APP=polybot
    export OPENAI_API_KEY=sk-...
    uv run modal secret create openai-secret OPENAI_API_KEY=$OPENAI_API_KEY --force
    uv run python -m kalshi_agent.autoresearch.sandbox_smoke --app-name polybot
"""

from __future__ import annotations

import argparse
import os
import shlex
import sys

import modal

DEFAULT_APP_NAME = os.environ.get("POLYBOT_CODEX_MODAL_APP", "polybot")
DEFAULT_SECRET_NAME = os.environ.get("POLYBOT_CODEX_MODAL_SECRET", "openai-secret")
DEFAULT_CODEX_MODEL = "gpt-5-mini"


def build_image() -> modal.Image:
    return (
        modal.Image.debian_slim(python_version="3.11")
        .apt_install("nodejs", "npm")
        .run_commands("npm install -g @openai/codex")
    )


def run_smoke(
    *,
    app_name: str,
    secret_name: str,
    timeout_seconds: int,
    codex_timeout_seconds: int,
    codex_model: str,
    run_codex: bool,
) -> int:
    print(f"[smoke] Modal app: {app_name}", flush=True)
    print(f"[smoke] Secret: {secret_name}", flush=True)
    print("[smoke] Looking up Modal app (create_if_missing=True)...", flush=True)
    app = modal.App.lookup(app_name, create_if_missing=True)

    print("[smoke] Creating Modal sandbox...", flush=True)
    sandbox = modal.Sandbox.create(
        "sleep",
        "infinity",
        app=app,
        image=build_image(),
        timeout=timeout_seconds,
        secrets=[modal.Secret.from_name(secret_name)],
    )
    print("[smoke] Sandbox is up. Watch it in the Modal UI under Apps -> your app -> Sandboxes.", flush=True)

    try:
        print("[smoke] Checking node/npm/codex...", flush=True)
        version = sandbox.exec("sh", "-lc", "node --version && npm --version && codex --version")
        print(version.stdout.read(), end="")
        version.wait()

        direct = sandbox.exec("sh", "-lc", "echo hello-world-from-modal-sandbox")
        print("[smoke] Direct shell:", direct.stdout.read().strip(), flush=True)
        direct.wait()

        if not run_codex:
            print("[smoke] Skipping Codex prompt (--skip-codex). Sandbox lifecycle OK.", flush=True)
            return 0

        print("[smoke] Running Codex hello-world prompt...", flush=True)
        prompt = (
            "Run exactly this shell command and then stop: "
            "python3 -c \"print('hello-world-from-codex')\""
        )
        codex_command = " ".join(
            [
                "timeout",
                f"{codex_timeout_seconds}s",
                "codex",
                "exec",
                "--dangerously-bypass-approvals-and-sandbox",
                "--skip-git-repo-check",
                "--model",
                shlex.quote(codex_model),
                "-c",
                "model_reasoning_effort=low",
                shlex.quote(prompt),
            ]
        )
        codex = sandbox.exec(
            "sh",
            "-lc",
            "printenv OPENAI_API_KEY | codex login --with-api-key >/dev/null 2>&1 "
            "|| { echo '[smoke] codex login failed' >&2; exit 1; }; "
            f"{codex_command} < /dev/null 2>&1; "
            "code=$?; echo \"[smoke] codex_exit_code=${code}\"; exit $code",
        )
        print("[smoke] Codex output:", flush=True)
        for line in codex.stdout:
            print(line, end="", flush=True)
        codex.wait()
        return 0
    finally:
        print("[smoke] Terminating sandbox...", flush=True)
        sandbox.terminate()


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke test a Modal Sandbox with optional Codex.")
    parser.add_argument("--app-name", default=DEFAULT_APP_NAME)
    parser.add_argument("--secret-name", default=DEFAULT_SECRET_NAME)
    parser.add_argument("--timeout-seconds", type=int, default=600)
    parser.add_argument("--codex-timeout-seconds", type=int, default=600)
    parser.add_argument("--codex-model", default=DEFAULT_CODEX_MODEL)
    parser.add_argument(
        "--skip-codex",
        action="store_true",
        help="Only prove sandbox spin-up; do not call OpenAI/Codex.",
    )
    args = parser.parse_args()

    raise SystemExit(
        run_smoke(
            app_name=args.app_name,
            secret_name=args.secret_name,
            timeout_seconds=args.timeout_seconds,
            codex_timeout_seconds=args.codex_timeout_seconds,
            codex_model=args.codex_model,
            run_codex=not args.skip_codex,
        )
    )


if __name__ == "__main__":
    main()
