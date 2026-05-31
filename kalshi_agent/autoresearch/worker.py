from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

DEFAULT_THESIS_PATH = Path("thesis.md")
DEFAULT_CODEX_APP_NAME = os.environ.get("POLYBOT_CODEX_MODAL_APP", "polybot-strategy-codex")
DEFAULT_CODEX_SECRET_NAME = os.environ.get("POLYBOT_CODEX_MODAL_SECRET", "openai-secret")
WORKSPACE_DIR = "/workspace"
EDITABLE_FILE = "strategy.py"
AUTORESEARCH_PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_BASELINE_PATH = AUTORESEARCH_PACKAGE_DIR / "baseline.py"

# Files copied into the sandbox so an agent can read the contract and self-test.
# Only strategy.py is read back out; everything else is throwaway.
SUPPORT_FILES = ("thesis.md",)
PACKAGE_SUPPORT_FILES = (
    ("types.py", f"{WORKSPACE_DIR}/kalshi_agent/autoresearch/types.py"),
    ("backtest.py", f"{WORKSPACE_DIR}/kalshi_agent/autoresearch/backtest.py"),
)


@dataclass(frozen=True)
class WorkerContext:
    """Everything a strategy worker needs to propose the next candidate."""

    thesis: str
    parent_source: str
    parent_strategy_id: str | None = None
    prior_metrics: dict[str, object] = field(default_factory=dict)
    attempt_index: int = 0
    attempt_label: str = "attempt"


@dataclass(frozen=True)
class WorkerResult:
    source: str
    rationale: str
    worker_type: str
    verified: bool | None = None
    verification_detail: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "rationale": self.rationale,
            "worker_type": self.worker_type,
            "verified": self.verified,
            "verification_detail": self.verification_detail,
        }


class StrategyWorker(Protocol):
    """A worker turns a context into a new strategy.py source plus a rationale."""

    worker_type: str

    def generate(self, context: WorkerContext) -> WorkerResult: ...


def build_codex_prompt(context: WorkerContext) -> str:
    """Assemble the instruction handed to Codex inside the sandbox."""
    prior = json.dumps(context.prior_metrics, indent=2, sort_keys=True) if context.prior_metrics else "none yet"
    return textwrap.dedent(
        f"""
        You are improving a single Kalshi weather trading strategy.

        Hard rules:
        - Edit ONLY `{EDITABLE_FILE}` in this workspace.
        - Keep the contract: `def decide(state: MarketState) -> Order | None`.
        - Prefer `from kalshi_agent.autoresearch.types import MarketState, Order`.
        - `decide` must be a pure function (no IO, no network, no randomness).
        - Do not edit backtest.py, evaluator.py, registry tooling, or anything under
          kalshi_agent/ except types imported from kalshi_agent.autoresearch.types.
        - You may run `python -c "import strategy"` to confirm it imports.

        The full thesis and scoring rules:
        ---
        {context.thesis}
        ---

        Prior validation/train metrics for the parent strategy:
        {prior}

        Produce a meaningfully different, well-reasoned variation that should improve
        risk-adjusted validation performance after costs. When finished, briefly explain
        the hypothesis behind your change in your final message.
        """
    ).strip()


class MockStrategyWorker:
    """Offline worker that deterministically mutates the strategy.

    It regenerates a self-contained `strategy.py` from a template with a varied
    minimum net-edge and liquidity gate. This lets the full loop run and be tested
    without Codex, Modal, or network access.
    """

    worker_type = "mock"

    # Cycled across attempts so iterations explore different thresholds.
    _EDGE_GRID = (0.04, 0.06, 0.08, 0.10, 0.12)
    _LIQUIDITY_GRID = (25.0, 40.0, 60.0, 100.0)

    def generate(self, context: WorkerContext) -> WorkerResult:
        min_net_edge = self._EDGE_GRID[context.attempt_index % len(self._EDGE_GRID)]
        min_liquidity = self._LIQUIDITY_GRID[context.attempt_index % len(self._LIQUIDITY_GRID)]
        source = self._render(min_net_edge=min_net_edge, min_liquidity=min_liquidity)
        rationale = (
            f"Mock mutation: require net edge >= {min_net_edge} and liquidity >= {min_liquidity} "
            "after the cost model before taking a YES position."
        )
        return WorkerResult(source=source, rationale=rationale, worker_type=self.worker_type)

    @staticmethod
    def _render(*, min_net_edge: float, min_liquidity: float) -> str:
        return textwrap.dedent(
            f'''
            from __future__ import annotations

            import math
            from typing import Any

            from kalshi_agent.autoresearch.types import MarketState, Order

            MIN_LIQUIDITY = {min_liquidity}
            MIN_NET_EDGE = {min_net_edge}


            def _as_float(value: Any) -> float | None:
                if value is None:
                    return None
                try:
                    return float(value)
                except (TypeError, ValueError):
                    return None


            def estimate_fee_per_contract(price: float) -> float:
                raw_cents = 0.07 * price * (1.0 - price) * 100
                return math.ceil(raw_cents) / 100


            def decide(state: MarketState) -> Order | None:
                model_p = _as_float(
                    state.features.get("model_probability_yes")
                    or state.features.get("nws_probability_yes")
                    or state.features.get("probability_yes")
                )
                if model_p is None or state.yes_ask is None:
                    return None

                if state.features.get("resolution_ambiguity") == "high":
                    return None

                if state.liquidity < MIN_LIQUIDITY:
                    return None

                estimated_fee = estimate_fee_per_contract(state.yes_ask)
                estimated_slippage = 0.02 if state.liquidity < 100 else 0.01
                net_edge = model_p - state.yes_ask - estimated_fee - estimated_slippage
                if net_edge < MIN_NET_EDGE:
                    return None

                return Order(side="yes", size=1, limit_price=state.yes_ask)
            '''
        ).strip() + "\n"


class CodexModalWorker:
    """Run `codex exec` inside a disposable Modal Sandbox and read back strategy.py.

    Modal is imported lazily so this module stays importable without Modal installed
    or configured. Use `dry_run=True` to inspect the prompt and image plan offline.
    """

    worker_type = "codex_modal"

    def __init__(
        self,
        *,
        app_name: str = DEFAULT_CODEX_APP_NAME,
        codex_model: str | None = None,
        timeout_seconds: int = 600,
        secret_name: str = DEFAULT_CODEX_SECRET_NAME,
        support_files: tuple[str, ...] = SUPPORT_FILES,
        verify: bool = True,
    ) -> None:
        self.app_name = app_name
        self.codex_model = codex_model
        self.timeout_seconds = timeout_seconds
        self.secret_name = secret_name
        self.support_files = support_files
        self.verify = verify

    def _codex_command(self, prompt: str) -> list[str]:
        # We are already isolated inside the Modal sandbox, so bypass Codex's own
        # bubblewrap sandbox, which can't set up a nested network namespace inside
        # a container (fails with "bwrap: loopback: ... RTM_NEWADDR").
        command = [
            "codex",
            "exec",
            "--dangerously-bypass-approvals-and-sandbox",
            "--skip-git-repo-check",
        ]
        if self.codex_model:
            command += ["--model", self.codex_model]
        command.append(prompt)
        return command

    def _codex_shell_command(self, prompt: str) -> str:
        # Codex v0.135 no longer reads OPENAI_API_KEY directly for `exec`; it needs
        # a login that writes auth.json first. Pipe the key via --with-api-key.
        # Redirect stdin from /dev/null so any interactive prompt fails fast rather
        # than blocking the run forever.
        codex_command = " ".join(shlex.quote(part) for part in self._codex_command(prompt))
        return (
            "printenv OPENAI_API_KEY | codex login --with-api-key >/dev/null 2>&1 "
            "|| { echo 'codex login failed' >&2; exit 1; }; "
            f"{codex_command} < /dev/null"
        )

    def build_image(self):
        import modal

        return (
            modal.Image.debian_slim(python_version="3.11")
            .apt_install("nodejs", "npm")
            .pip_install("requests")
            .run_commands("npm install -g @openai/codex")
        )

    def generate(self, context: WorkerContext, *, dry_run: bool = False) -> WorkerResult:
        prompt = build_codex_prompt(context)
        if dry_run:
            return WorkerResult(
                source=context.parent_source,
                rationale=f"DRY RUN. Would run: {self._codex_shell_command('<prompt>')}",
                worker_type=self.worker_type,
            )

        import modal

        print("[codex] Looking up Modal app...", file=sys.stderr, flush=True)
        app = modal.App.lookup(self.app_name, create_if_missing=True)
        try:
            print("[codex] Creating Modal sandbox...", file=sys.stderr, flush=True)
            sandbox = modal.Sandbox.create(
                "sleep",
                "infinity",
                app=app,
                image=self.build_image(),
                timeout=self.timeout_seconds,
                workdir=WORKSPACE_DIR,
                secrets=[modal.Secret.from_name(self.secret_name)],
                block_network=False,
            )
            print("[codex] Modal sandbox ready.", file=sys.stderr, flush=True)
        except Exception as exc:
            if "Secret" in str(exc) and self.secret_name in str(exc):
                raise RuntimeError(
                    f"Modal secret {self.secret_name!r} was not found. Create it with:\n"
                    f"  uv run modal secret create {self.secret_name} OPENAI_API_KEY=$OPENAI_API_KEY\n"
                    "or pass a different secret using --codex-secret-name / POLYBOT_CODEX_MODAL_SECRET."
                ) from exc
            raise
        try:
            print("[codex] Writing strategy workspace files...", file=sys.stderr, flush=True)
            self._write_workspace(sandbox, context)
            print("[codex] Running Codex in sandbox. This can take a few minutes...", file=sys.stderr, flush=True)
            process = sandbox.exec("sh", "-lc", self._codex_shell_command(prompt))
            rationale = process.stdout.read()
            process.wait()
            print("[codex] Reading generated strategy.py...", file=sys.stderr, flush=True)
            new_source = self._read_strategy(sandbox)

            verified: bool | None = None
            verification_detail = ""
            if self.verify:
                print("[codex] Verifying generated strategy in sandbox...", file=sys.stderr, flush=True)
                verified, verification_detail = self._verify_strategy(sandbox)
                print(
                    f"[codex] Verification {'passed' if verified else 'FAILED'}: {verification_detail}",
                    file=sys.stderr,
                    flush=True,
                )
        finally:
            print("[codex] Terminating Modal sandbox...", file=sys.stderr, flush=True)
            sandbox.terminate()

        return WorkerResult(
            source=new_source,
            rationale=rationale.strip() or "Codex produced no summary text.",
            worker_type=self.worker_type,
            verified=verified,
            verification_detail=verification_detail,
        )

    def _write_workspace(self, sandbox, context: WorkerContext) -> None:
        mkdir = sandbox.exec("sh", "-lc", f"mkdir -p {WORKSPACE_DIR}/kalshi_agent/autoresearch")
        mkdir.wait()
        self._write_file(sandbox, f"{WORKSPACE_DIR}/{EDITABLE_FILE}", context.parent_source)
        self._write_file(sandbox, f"{WORKSPACE_DIR}/kalshi_agent/__init__.py", "")
        self._write_file(
            sandbox,
            f"{WORKSPACE_DIR}/kalshi_agent/autoresearch/__init__.py",
            "from kalshi_agent.autoresearch.types import MarketState, Metrics, Order\n",
        )
        for local_name, remote_path in PACKAGE_SUPPORT_FILES:
            local_path = AUTORESEARCH_PACKAGE_DIR / local_name
            self._write_file(sandbox, remote_path, local_path.read_text(encoding="utf-8"))
        self._write_file(
            sandbox,
            f"{WORKSPACE_DIR}/strategy_types.py",
            "from kalshi_agent.autoresearch.types import *  # noqa: F401,F403\n",
        )
        self._write_file(
            sandbox,
            f"{WORKSPACE_DIR}/backtest.py",
            "from kalshi_agent.autoresearch.backtest import *  # noqa: F401,F403\n",
        )
        for name in self.support_files:
            local_path = Path(name)
            if local_path.exists():
                self._write_file(sandbox, f"{WORKSPACE_DIR}/{name}", local_path.read_text(encoding="utf-8"))

    @staticmethod
    def _write_file(sandbox, remote_path: str, content: str) -> None:
        sandbox.filesystem.write_text(content, remote_path)

    @staticmethod
    def _read_strategy(sandbox) -> str:
        return sandbox.filesystem.read_text(f"{WORKSPACE_DIR}/{EDITABLE_FILE}")

    # Import the generated strategy inside the sandbox and exercise `decide` on a
    # couple of sample states so we catch syntax/import/contract errors before the
    # candidate is returned to the loop (where it would otherwise be marked invalid
    # only after a write/eval round-trip).
    _VERIFY_RUNNER = textwrap.dedent(
        """
        import strategy
        from kalshi_agent.autoresearch.types import MarketState, Order

        assert hasattr(strategy, "decide"), "strategy has no decide()"
        assert callable(strategy.decide), "decide is not callable"

        samples = [
            MarketState(
                ticker="t", timestamp_utc="t", yes_ask=0.55, no_ask=0.47,
                liquidity=200.0, time_to_close_seconds=86400.0,
                features={"model_probability_yes": 0.8, "resolution_ambiguity": "low"},
            ),
            MarketState(ticker="t", timestamp_utc="t", features={}),
        ]
        for st in samples:
            out = strategy.decide(st)
            assert out is None or isinstance(out, Order), f"decide returned {type(out)!r}"

        print("VERIFY_OK")
        """
    ).strip()

    def _verify_strategy(self, sandbox) -> tuple[bool, str]:
        self._write_file(sandbox, f"{WORKSPACE_DIR}/_verify.py", self._VERIFY_RUNNER)
        proc = sandbox.exec(
            "sh",
            "-lc",
            f"cd {WORKSPACE_DIR} && python3 _verify.py 2>&1; echo verify_exit=$?",
        )
        output = proc.stdout.read()
        proc.wait()
        ok = "VERIFY_OK" in output and "verify_exit=0" in output
        detail = " ".join(output.split())[-500:] if not ok else "decide() imports and returns Order|None"
        return ok, detail


def get_worker(name: str, **kwargs) -> StrategyWorker:
    if name == "mock":
        return MockStrategyWorker()
    if name == "codex":
        return CodexModalWorker(**kwargs)
    raise ValueError(f"Unknown worker {name!r}. Use 'mock' or 'codex'.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect a strategy worker without running the full loop.")
    parser.add_argument("--worker", choices=["mock", "codex"], default="mock")
    parser.add_argument("--parent", type=Path, default=DEFAULT_BASELINE_PATH)
    parser.add_argument("--thesis", type=Path, default=DEFAULT_THESIS_PATH)
    parser.add_argument("--attempt-index", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true", help="For codex: print the plan without using Modal.")
    parser.add_argument("--codex-app-name", default=DEFAULT_CODEX_APP_NAME)
    parser.add_argument("--codex-secret-name", default=DEFAULT_CODEX_SECRET_NAME)
    parser.add_argument("--codex-model", default=None)
    parser.add_argument("--codex-timeout-seconds", type=int, default=600)
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="For codex: skip importing/running the generated strategy in the sandbox.",
    )
    args = parser.parse_args()

    context = WorkerContext(
        thesis=args.thesis.read_text(encoding="utf-8") if args.thesis.exists() else "",
        parent_source=args.parent.read_text(encoding="utf-8"),
        attempt_index=args.attempt_index,
    )

    if args.worker == "codex":
        worker = CodexModalWorker(
            app_name=args.codex_app_name,
            secret_name=args.codex_secret_name,
            codex_model=args.codex_model,
            timeout_seconds=args.codex_timeout_seconds,
            verify=not args.no_verify,
        )
        result = worker.generate(context, dry_run=args.dry_run)
    else:
        worker = MockStrategyWorker()
        result = worker.generate(context)

    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    print("---- generated strategy.py ----")
    print(result.source)


if __name__ == "__main__":
    main()
