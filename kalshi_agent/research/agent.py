from __future__ import annotations

import argparse
import json
from typing import Any

from kalshi_agent.research.core import append_ledger_entry, research_market

INSTRUCTIONS = """
You are a Kalshi weather-market research coordinator.
You may call tools to fetch market data and public weather evidence.
You must not place trades.
You must not access private keys.
You must label all outputs as paper research.
If resolution rules are ambiguous, mark NO_TRADE or WATCHLIST_ONLY.
Summarize the strongest watchlist candidates and explain the main risks.
""".strip()


def _import_agents_sdk() -> tuple[Any, Any, Any]:
    try:
        from agents import Agent, Runner, function_tool
    except ImportError as exc:
        raise RuntimeError(
            "OpenAI Agents SDK is not installed. Run `uv sync` after installing project dependencies."
        ) from exc
    return Agent, Runner, function_tool


def research_market_payload(ticker: str, *, run_type: str = "agent_weather_research") -> dict:
    result = research_market(ticker)
    append_ledger_entry(result, run_type=run_type)
    return result


def research_many_markets_payload(tickers: list[str], *, use_modal: bool = True) -> list[dict]:
    if use_modal:
        from kalshi_agent.research.modal_app import research_many_markets

        results = research_many_markets(tickers)
        for result in results:
            append_ledger_entry(result, run_type="agent_modal_weather_research")
        return results

    return [research_market_payload(ticker) for ticker in tickers]


def build_agent(*, model: str | None = None, use_modal: bool = True) -> Any:
    Agent, _Runner, function_tool = _import_agents_sdk()

    @function_tool
    def research_market_tool(ticker: str) -> dict:
        """Research one Kalshi weather market and return a paper-trade memo."""
        return research_market_payload(ticker)

    @function_tool
    def research_many_markets_tool(tickers: list[str]) -> list[dict]:
        """Research multiple Kalshi weather markets in parallel when Modal is enabled."""
        return research_many_markets_payload(tickers, use_modal=use_modal)

    kwargs: dict[str, Any] = {}
    if model:
        kwargs["model"] = model

    return Agent(
        name="Kalshi Weather Research Coordinator",
        instructions=INSTRUCTIONS,
        tools=[research_market_tool, research_many_markets_tool],
        **kwargs,
    )


def run_agent(prompt: str, *, model: str | None = None, use_modal: bool = True) -> str:
    _Agent, Runner, _function_tool = _import_agents_sdk()
    agent = build_agent(model=model, use_modal=use_modal)
    result = Runner.run_sync(agent, prompt)
    return str(result.final_output)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the paper-only Kalshi weather research agent.")
    parser.add_argument("prompt", help="Research request for the agent.")
    parser.add_argument("--model", default=None, help="Optional OpenAI model name for the Agents SDK.")
    parser.add_argument(
        "--local",
        action="store_true",
        help="Run multi-market research sequentially instead of using Modal.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the final agent output as a JSON string payload.",
    )
    args = parser.parse_args()

    output = run_agent(args.prompt, model=args.model, use_modal=not args.local)
    if args.json:
        print(json.dumps({"final_output": output}, indent=2, sort_keys=True))
    else:
        print(output)


if __name__ == "__main__":
    main()
