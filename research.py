from __future__ import annotations

import argparse
import json
import math
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests

# Public read endpoints (markets, orderbook) need no auth. This is the prod host
# verified end-to-end while building kalshi_agent/ (see docs/PIPELINE.md);
# external-api.kalshi.com also serves these reads, but we use the canonical host
# so the whole repo points at one base.
KALSHI_PUBLIC_BASE = "https://api.elections.kalshi.com/trade-api/v2"
NWS_BASE = "https://api.weather.gov"
NWS_USER_AGENT = "polybot-kalshi-hackathon (local research demo)"
DEFAULT_LEDGER_PATH = Path("ledger.jsonl")

KNOWN_LOCATIONS = {
    "NYC": {
        "label": "New York City",
        "lat": 40.7812,
        "lon": -73.9665,
        "station_hint": "Central Park",
    },
    "SFO": {
        "label": "San Francisco",
        "lat": 37.7749,
        "lon": -122.4194,
        "station_hint": "San Francisco area station",
    },
}


def _get_json(url: str, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> dict:
    response = requests.get(url, params=params, headers=headers, timeout=20)
    response.raise_for_status()
    return response.json()


def fetch_kalshi_market(ticker: str) -> dict:
    data = _get_json(f"{KALSHI_PUBLIC_BASE}/markets/{ticker}")
    return data["market"]


def fetch_kalshi_orderbook(ticker: str, depth: int = 5) -> dict:
    data = _get_json(f"{KALSHI_PUBLIC_BASE}/markets/{ticker}/orderbook", params={"depth": depth})
    return data.get("orderbook_fp") or data["orderbook"]


def _normalize_price(raw_price: str | int | float) -> float:
    price = float(raw_price)
    return price / 100 if price > 1 else price


def _best_bid(levels: list[list[str | int | float]]) -> tuple[float | None, float]:
    if not levels:
        return None, 0.0

    parsed = [(_normalize_price(price), float(quantity)) for price, quantity in levels]
    # Best bid is the HIGHEST price level, chosen by max() not by position. The
    # live API does not guarantee level ordering (verified: they arrive
    # ascending), so indexing [0] — as the original DESIGN.md sketch did — would
    # pick the *worst* bid and derive a wrong ask.
    price, quantity = max(parsed, key=lambda level: level[0])
    return round(price, 4), quantity


def normalize_orderbook(orderbook: dict) -> dict:
    # Key names differ across Kalshi feeds (verified live): the REST orderbook
    # uses `yes_dollars`, the WS snapshot uses `yes_dollars_fp`, and an older
    # shape used bare `yes`. Accept all so this survives whichever we get.
    yes_levels = orderbook.get("yes_dollars") or orderbook.get("yes_dollars_fp") or orderbook.get("yes") or []
    no_levels = orderbook.get("no_dollars") or orderbook.get("no_dollars_fp") or orderbook.get("no") or []
    yes_bid, yes_qty = _best_bid(yes_levels)
    no_bid, no_qty = _best_bid(no_levels)

    yes_ask = None if no_bid is None else round(1.0 - no_bid, 4)
    no_ask = None if yes_bid is None else round(1.0 - yes_bid, 4)

    return {
        "yes_bid": yes_bid,
        "yes_ask": yes_ask,
        "no_bid": no_bid,
        "no_ask": no_ask,
        "liquidity": yes_qty + no_qty,
    }


def infer_location(market: dict) -> str | None:
    text = " ".join(
        str(market.get(key, ""))
        for key in ("ticker", "event_ticker", "series_ticker", "title", "subtitle")
    ).lower()

    if "nyc" in text or "new york" in text or "kxrainnyc" in text or "kxhighny" in text:
        return "NYC"
    if "sfo" in text or "san francisco" in text or "kxhightsfo" in text:
        return "SFO"
    return None


def parse_weather_rule(market: dict) -> dict:
    text = " ".join(
        str(market.get(key, ""))
        for key in ("ticker", "event_ticker", "series_ticker", "title", "subtitle")
    ).lower()
    location = infer_location(market)

    # Learning from the live API: the market object carries the AUTHORITATIVE
    # settlement rule in `rules_primary` / `rules_secondary` (e.g. "precipitation
    # recorded at Central Park ... strictly greater than 0 ... resolves to Yes",
    # plus the NWS station URL used for determination). The title alone is not
    # enough to settle on — so when these are present we surface them verbatim and
    # lower the ambiguity we'd otherwise have to assume from the title text.
    rules_primary = market.get("rules_primary") or None
    rules_secondary = market.get("rules_secondary") or None
    has_rules = bool(rules_primary)

    if "rain" in text or "precip" in text:
        return {
            "market_family": "weather_rain",
            "summary": "Resolves based on whether measurable rain occurs for the stated city/date.",
            "location": location,
            "metric": "precipitation",
            "threshold": "measurable rain; exact threshold must be checked in Kalshi rules",
            "rules_primary": rules_primary,
            "rules_secondary": rules_secondary,
            # The official rule pins the station + threshold, so we trust it over
            # a title guess; only fall back to "medium" when no rule text exists.
            "ambiguity_score": "low" if has_rules else "medium",
            "unresolved_questions": []
            if has_rules
            else [
                "Which station or official report controls settlement?",
                "What minimum precipitation amount counts as rain?",
            ],
        }

    if "temperature" in text or "highest" in text or "high" in text:
        lower, upper = parse_temperature_bucket(market)
        bucket_clear = lower is not None and upper is not None
        return {
            "market_family": "weather_high_temp",
            "summary": "Resolves based on the official daily high temperature for the stated city/date.",
            "location": location,
            "metric": "daily_high_temperature_f",
            "threshold": f"{lower}-{upper}F" if bucket_clear else "temperature bucket unclear",
            "bucket_lower_f": lower,
            "bucket_upper_f": upper,
            "rules_primary": rules_primary,
            "rules_secondary": rules_secondary,
            # Need both a clear bucket AND the official rule to call it low-risk.
            "ambiguity_score": "low" if (bucket_clear and has_rules) else "medium" if bucket_clear else "high",
            "unresolved_questions": []
            if (bucket_clear and has_rules)
            else [
                "Which station determines the final high temperature?",
                "How are bucket boundaries handled?",
            ],
        }

    return {
        "market_family": "unsupported",
        "summary": "Unsupported or unclear weather market.",
        "location": location,
        "metric": None,
        "threshold": None,
        "rules_primary": rules_primary,
        "rules_secondary": rules_secondary,
        "ambiguity_score": "high",
        "unresolved_questions": ["Market does not match the initial weather parser patterns."],
    }


def parse_temperature_bucket(market: dict) -> tuple[int | None, int | None]:
    text = " ".join(str(market.get(key, "")) for key in ("title", "subtitle", "yes_sub_title", "ticker"))

    range_match = re.search(r"(\d{2,3})\s*(?:-|to|–|—)\s*(\d{2,3})", text, flags=re.IGNORECASE)
    if range_match:
        return int(range_match.group(1)), int(range_match.group(2))

    above_match = re.search(r"(?:above|over|greater than|at least)\s*(\d{2,3})", text, flags=re.IGNORECASE)
    if above_match:
        lower = int(above_match.group(1))
        return lower, 150

    below_match = re.search(r"(?:below|under|less than)\s*(\d{2,3})", text, flags=re.IGNORECASE)
    if below_match:
        upper = int(below_match.group(1))
        return -100, upper

    return None, None


def fetch_nws_hourly_forecast(location: dict) -> list[dict]:
    headers = {"User-Agent": NWS_USER_AGENT, "Accept": "application/geo+json"}
    point = _get_json(f"{NWS_BASE}/points/{location['lat']},{location['lon']}", headers=headers)
    hourly_url = point["properties"]["forecastHourly"]
    hourly = _get_json(hourly_url, headers=headers)
    return hourly["properties"]["periods"]


def estimate_rain_probability(hourly_periods: list[dict], hours_ahead: int = 18) -> dict:
    pops: list[float] = []
    for period in hourly_periods[:hours_ahead]:
        value = period.get("probabilityOfPrecipitation", {}).get("value")
        if value is not None:
            pops.append(max(0.0, min(1.0, value / 100.0)))

    if not pops:
        # No signal -> abstain, don't guess. A real 0.5 here would flow into the
        # edge calc and could trigger a trade on nothing; None makes decide()
        # return NO_TRADE instead. (Same discipline as kalshi_agent/weather.py.)
        return {
            "probability_yes": None,
            "confidence": "low",
            "notes": ["NWS hourly precipitation probabilities were unavailable; abstaining."],
        }

    max_pop = max(pops)
    avg_pop = sum(pops) / len(pops)
    probability = 0.65 * max_pop + 0.35 * avg_pop

    return {
        "probability_yes": round(probability, 3),
        "confidence": "medium",
        "notes": [
            f"Max hourly precipitation probability: {max_pop:.0%}",
            f"Average hourly precipitation probability: {avg_pop:.0%}",
            "Heuristic treats weather hours as correlated.",
        ],
    }


def estimate_high_temp_probability(hourly_periods: list[dict], lower_f: int | None, upper_f: int | None) -> dict:
    temps = [period.get("temperature") for period in hourly_periods[:24] if period.get("temperature") is not None]
    if not temps:
        # No signal -> abstain (None), not a 0.5 guess. See estimate_rain_probability.
        return {
            "probability_yes": None,
            "confidence": "low",
            "notes": ["NWS hourly temperatures were unavailable; abstaining."],
        }

    forecast_high = max(temps)
    if lower_f is None or upper_f is None:
        # We have a forecast high but no usable bucket to score it against, so
        # there is no signal to act on -> abstain rather than guess 0.5.
        return {
            "probability_yes": None,
            "confidence": "low",
            "notes": [f"NWS forecast high is {forecast_high}F, but the temperature bucket was unclear; abstaining."],
        }

    if lower_f <= forecast_high <= upper_f:
        probability = 0.45
    else:
        distance = min(abs(forecast_high - lower_f), abs(forecast_high - upper_f))
        probability = 0.25 if distance <= 1 else 0.12 if distance <= 2 else 0.05

    return {
        "probability_yes": probability,
        "confidence": "medium" if probability >= 0.25 else "low",
        "notes": [f"NWS forecast high from hourly periods is {forecast_high}F."],
    }


def estimate_probability(rule: dict, hourly_periods: list[dict]) -> dict:
    if rule["market_family"] == "weather_rain":
        return estimate_rain_probability(hourly_periods)
    if rule["market_family"] == "weather_high_temp":
        return estimate_high_temp_probability(
            hourly_periods,
            rule.get("bucket_lower_f"),
            rule.get("bucket_upper_f"),
        )
    return {
        "probability_yes": None,
        "confidence": "low",
        "notes": ["Unsupported market family; no model signal, abstaining."],
    }


def estimate_fee_per_contract(price: float) -> float:
    raw_cents = 0.07 * price * (1.0 - price) * 100
    return math.ceil(raw_cents) / 100


def decide(
    model_p: float | None,
    market_data: dict,
    ambiguity_score: str,
    *,
    market_status: str = "active",
) -> dict:
    yes_ask = market_data.get("yes_ask")
    liquidity = market_data.get("liquidity", 0.0)

    # Only "active" markets are tradeable; "closed"/"settled"/etc. mean the book
    # is gone or the outcome is decided. Verified: the live API reports status
    # "active" (the `status=open` list filter maps to it).
    if market_status != "active":
        return {
            "action": "NO_TRADE",
            "reason": f"Market is not active (status={market_status!r}).",
            "raw_edge": None,
            "net_edge": None,
        }

    # No model probability means we have no signal -> abstain, never guess.
    if model_p is None:
        return {
            "action": "NO_TRADE",
            "reason": "No usable weather signal; abstaining rather than guessing.",
            "raw_edge": None,
            "net_edge": None,
        }

    if yes_ask is None:
        return {
            "action": "NO_TRADE",
            "reason": "No inferred YES ask is available from the orderbook.",
            "raw_edge": None,
            "net_edge": None,
        }

    estimated_fee = estimate_fee_per_contract(yes_ask)
    estimated_slippage = 0.02 if liquidity < 100 else 0.01
    raw_edge = model_p - yes_ask
    net_edge = raw_edge - estimated_fee - estimated_slippage

    if ambiguity_score == "high":
        action = "NO_TRADE"
        reason = "Resolution rule is too ambiguous for the MVP parser."
    elif liquidity < 25:
        action = "WATCHLIST_ONLY"
        reason = "Visible top-level liquidity is too low."
    elif net_edge >= 0.06:
        action = "PAPER_BUY_YES"
        reason = "Model probability clears market ask after estimated costs."
    else:
        action = "NO_TRADE"
        reason = "Edge is below threshold after estimated costs."

    return {
        "action": action,
        "market_yes_ask": yes_ask,
        "raw_edge": round(raw_edge, 4),
        "estimated_fee": estimated_fee,
        "estimated_slippage": estimated_slippage,
        "net_edge": round(net_edge, 4),
        "reason": reason,
    }


def research_market(ticker: str) -> dict:
    normalized_ticker = ticker.upper()
    now = datetime.now(UTC)
    market = fetch_kalshi_market(normalized_ticker)
    orderbook = fetch_kalshi_orderbook(normalized_ticker)
    market_data = normalize_orderbook(orderbook)
    rule = parse_weather_rule(market)

    location_key = rule.get("location")
    if location_key not in KNOWN_LOCATIONS:
        model = {
            "probability_yes": 0.5,
            "confidence": "low",
            "notes": ["Location is unsupported by the MVP weather map."],
        }
    else:
        hourly = fetch_nws_hourly_forecast(KNOWN_LOCATIONS[location_key])
        model = estimate_probability(rule, hourly)

    decision = decide(
        model_p=model["probability_yes"],
        market_data=market_data,
        ambiguity_score=rule["ambiguity_score"],
        market_status=market.get("status", "active"),
    )

    return {
        "run_id": f"research_{now.strftime('%Y%m%dT%H%M%SZ')}_{normalized_ticker}",
        "timestamp_utc": now.isoformat(),
        "venue": "kalshi",
        "market_ticker": normalized_ticker,
        "market_title": market.get("title"),
        "status": market.get("status"),
        "close_time": market.get("close_time"),
        "resolution": rule,
        "market_data": market_data,
        "model": model,
        "decision": decision,
        "risk_flags": rule.get("unresolved_questions", []),
        "sources_used": [
            "Kalshi public market API",
            "Kalshi orderbook API",
            "NWS hourly forecast API",
        ],
        "paper_trade_only": True,
    }


def append_ledger_entry(result: dict, *, run_type: str = "live_weather_research", path: Path = DEFAULT_LEDGER_PATH) -> None:
    decision = result.get("decision", {})
    market_data = result.get("market_data", {})
    model = result.get("model", {})
    entry = {
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "run_type": run_type,
        "run_id": result.get("run_id"),
        "ticker": result.get("market_ticker"),
        "model_probability_yes": model.get("probability_yes"),
        "yes_ask": market_data.get("yes_ask"),
        "net_edge": decision.get("net_edge"),
        "action": decision.get("action"),
        "paper_trade_only": True,
    }
    with path.open("a", encoding="utf-8") as ledger:
        ledger.write(json.dumps(entry, sort_keys=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Research one Kalshi weather market.")
    parser.add_argument("--ticker", required=True, help="Kalshi market ticker")
    parser.add_argument(
        "--no-ledger",
        action="store_true",
        help="Skip appending a summary row to ledger.jsonl.",
    )
    parser.add_argument(
        "--ledger-path",
        type=Path,
        default=DEFAULT_LEDGER_PATH,
        help="Path for append-only JSONL run summaries.",
    )
    args = parser.parse_args()

    result = research_market(args.ticker)
    if not args.no_ledger:
        append_ledger_entry(result, path=args.ledger_path)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
