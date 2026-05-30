from __future__ import annotations

import argparse
import sys

import modal

DEFAULT_APP_NAME = "polybot-codex-smoke"
DEFAULT_SECRET_NAME = "openai-secret"


def build_image() -> modal.Image:
    return (
        modal.Image.debian_slim(python_version="3.11")
        .apt_install("nodejs", "npm")
        .run_commands("npm install -g @openai/codex")
    )


def run_smoke(*, secret_name: str, timeout_seconds: int, model: str | None = None) -> int:
    app = modal.App.lookup(DEFAULT_APP_NAME, create_if_missing=True)

    print("[smoke] Creating Modal sandbox...", file=sys.stderr, flush=True)
    sandbox = modal.Sandbox.create(
        "sleep",
        "infinity",
        app=app,
        image=build_image(),
        timeout=timeout_seconds,
        secrets=[modal.Secret.from_name(secret_name)],
        block_network=False,
    )

    try:
        print("[smoke] Checking node/npm/codex availability...", file=sys.stderr, flush=True)
        version = sandbox.exec("sh", "-lc", "node --version && npm --version && which codex && codex --version")
        print(version.stdout.read(), flush=True)
        version.wait()

        prompt = "Print exactly HELLO_FROM_CODEX and nothing else."
        command = ["codex", "exec", "--sandbox", "workspace-write", "--skip-git-repo-check"]
        if model:
            command += ["--model", model]
        command.append(prompt)

        print("[smoke] Running Codex hello-world prompt...", file=sys.stderr, flush=True)
        process = sandbox.exec(*command)
        stdout = process.stdout.read()
        stderr = process.stderr.read()
        process.wait()

        print("---- codex stdout ----")
        print(stdout)
        print("---- codex stderr ----")
        print(stderr)
        return 0
    finally:
        print("[smoke] Terminating Modal sandbox...", file=sys.stderr, flush=True)
        sandbox.terminate()


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke test Codex CLI inside a Modal Sandbox.")
    parser.add_argument("--secret-name", default=DEFAULT_SECRET_NAME)
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--model", default=None)
    args = parser.parse_args()

    raise SystemExit(
        run_smoke(
            secret_name=args.secret_name,
            timeout_seconds=args.timeout_seconds,
            model=args.model,
        )
    )


if __name__ == "__main__":
    main()
