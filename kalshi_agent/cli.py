"""Unified CLI for Polybot: research, autoresearch loop, Kalshi smoke tests."""

from __future__ import annotations

import importlib
import sys

_COMMANDS: dict[str, str] = {
    "run": "kalshi_agent.run",
    "research": "kalshi_agent.research.core",
    "agent": "kalshi_agent.research.agent",
    "backtest": "kalshi_agent.backtest",
    "loop": "kalshi_agent.autoresearch.loop",
    "autoresearch-backtest": "kalshi_agent.autoresearch.backtest",
    "evaluator": "kalshi_agent.autoresearch.evaluator",
    "registry": "kalshi_agent.autoresearch.registry",
    "codex": "kalshi_agent.autoresearch.worker",
    "smoke": "kalshi_agent.smoke",
    "sandbox-smoke": "kalshi_agent.autoresearch.sandbox_smoke",
    "read": "kalshi_agent.read_cli",
}


def _usage() -> str:
    lines = [
        "Usage: polybot <command> [args...]",
        "",
        "Commands:",
    ]
    for name in sorted(_COMMANDS):
        module = _COMMANDS[name]
        lines.append(f"  {name:<16}  ({module})")
    lines.extend(
        [
            "",
            "Examples:",
            "  polybot run",
            "  polybot research --ticker KXRAINNYC-26MAY31-T0",
            "  polybot backtest --tickers KXRAINNYC-26MAY28-T0",
            "  polybot loop --worker mock --iterations 1",
            "  polybot read",
            "",
            "Modal (package paths, not root shims):",
            "  uv run modal run kalshi_agent/research/modal_app.py --tickers TICKER",
            "  uv run modal run kalshi_agent/autoresearch/modal_app.py --strategy-ids ID",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(_usage())
        raise SystemExit(0 if argv and argv[0] in ("-h", "--help") else 1)

    command = argv[0]
    module_path = _COMMANDS.get(command)
    if module_path is None:
        print(f"Unknown command: {command}\n", file=sys.stderr)
        print(_usage(), file=sys.stderr)
        raise SystemExit(1)

    module = importlib.import_module(module_path)
    entry = getattr(module, "main", None)
    if entry is None:
        print(f"{module_path} has no main()", file=sys.stderr)
        raise SystemExit(1)

    sys.argv = [f"polybot {command}", *argv[1:]]
    entry()


if __name__ == "__main__":
    main()
