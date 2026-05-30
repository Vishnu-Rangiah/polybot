from __future__ import annotations

import argparse
import shlex

import modal

DEFAULT_APP_NAME = "polybot-codex-smoke"
DEFAULT_SECRET_NAME = "openai-secret"
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
) -> None:
    app = modal.App.lookup(app_name, create_if_missing=True)
    sandbox = modal.Sandbox.create(
        "sleep",
        "infinity",
        app=app,
        image=build_image(),
        timeout=timeout_seconds,
        secrets=[modal.Secret.from_name(secret_name)],
    )

    try:
        print("[smoke] Running direct shell hello world...", flush=True)
        direct = sandbox.exec("sh", "-lc", "echo hello-world-from-modal")
        print(direct.stdout.read(), end="")
        direct.wait()

        print("[smoke] Checking Codex version...", flush=True)
        version = sandbox.exec("sh", "-lc", "codex --version")
        print(version.stdout.read(), end="")
        version.wait()

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
                # We are already isolated inside the Modal sandbox, so bypass
                # Codex's own bubblewrap sandbox (which can't set up a nested
                # network namespace in a container -> "RTM_NEWADDR" failure).
                "--dangerously-bypass-approvals-and-sandbox",
                "--skip-git-repo-check",
                "--model",
                shlex.quote(codex_model),
                "-c",
                "model_reasoning_effort=low",
                shlex.quote(prompt),
            ]
        )
        # Codex v0.135 no longer reads OPENAI_API_KEY directly for `exec`; it needs
        # a login that writes auth.json first. Pipe the key via --with-api-key.
        # Redirect stdin from /dev/null so any interactive setup/auth prompt gets
        # EOF immediately and fails fast instead of blocking forever on a key press.
        codex = sandbox.exec(
            "sh",
            "-lc",
            "printenv OPENAI_API_KEY | codex login --with-api-key >/dev/null 2>&1 "
            "|| { echo '[smoke] codex login failed' >&2; exit 1; }; "
            f"{codex_command} < /dev/null 2>&1; "
            "code=$?; echo \"[smoke] codex_exit_code=${code}\"; exit $code",
        )
        # Stream line-by-line so progress is visible instead of buffering until EOF.
        print("[smoke] Codex combined output:", flush=True)
        for line in codex.stdout:
            print(line, end="", flush=True)
        codex.wait()

        print("[smoke] Completed.")
    finally:
        print("[smoke] Terminating sandbox...", flush=True)
        sandbox.terminate()


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke test Codex inside a Modal sandbox.")
    parser.add_argument("--app-name", default=DEFAULT_APP_NAME)
    parser.add_argument("--secret-name", default=DEFAULT_SECRET_NAME)
    parser.add_argument("--timeout-seconds", type=int, default=600)
    parser.add_argument("--codex-timeout-seconds", type=int, default=600)
    parser.add_argument("--codex-model", default=DEFAULT_CODEX_MODEL)
    args = parser.parse_args()

    run_smoke(
        app_name=args.app_name,
        secret_name=args.secret_name,
        timeout_seconds=args.timeout_seconds,
        codex_timeout_seconds=args.codex_timeout_seconds,
        codex_model=args.codex_model,
    )


if __name__ == "__main__":
    main()
