"""Compatibility shim — use `polybot read` or `kalshi_agent.read_cli`."""

from kalshi_agent.read_cli import main


if __name__ == "__main__":
    raise SystemExit(main())
