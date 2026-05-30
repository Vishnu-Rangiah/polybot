"""Kalshi weather-ticker rule parser: ticker string -> structured MarketRule.

The critical design property is **conservative None**: if we can't confidently
parse a ticker we return None so the caller abstains. A silent misparsed trade
(wrong city, wrong threshold, wrong date) is far worse than a missed trade.
This module therefore only recognises series that are explicitly listed in
_SERIES_TO_LOCATION; anything else is None, never a guess.

Ticker formats (verified against live Kalshi data):
  Rain:      KXRAINNYC-26MAY31-T0
  High-temp: KXHIGHNY-26MAY31-T79

Date segment: 2-digit year + 3-letter uppercase month + 2-digit day.
  "26MAY31" -> 2026-05-31.

High-temp threshold: the T-value is the *exceedance* threshold.  A market
titled "80° or above" carries T79, meaning YES resolves when the daily high is
strictly greater than 79°F (≥ 80°F).  We store `threshold_f = T_value + 1` so
callers can check `forecast_high >= rule.threshold_f` without off-by-one risk.

Why a separate module (not inline in run.py): the parser is independently
testable and reusable.  run.py stays thin; rule_parser owns the grammar.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# ── Series registry ──────────────────────────────────────────────────────────
# Only series present here will ever be parsed.  Adding an unrecognised series
# would require a deliberate code change, not a regex accident.  City codes are
# the keys into WEATHER_LOCATIONS in weather.py.
#
# IMPORTANT inconsistency in Kalshi naming: rain uses "NYC", high-temp uses
# "NY" — both mean New York City.  Both map to the same location key "NYC".
_SERIES_TO_LOCATION: dict[str, tuple[str, str]] = {
    # series_prefix -> (kind, location_key)
    "KXRAINNYC": ("rain", "NYC"),
    "KXHIGHNY":  ("high_temp", "NYC"),
    "KXHIGHCHI": ("high_temp", "CHI"),
    "KXHIGHMIA": ("high_temp", "MIA"),
    "KXHIGHLAX": ("high_temp", "LAX"),
    "KXHIGHAUS": ("high_temp", "AUS"),
    "KXHIGHDEN": ("high_temp", "DEN"),
}

# ── Date parsing ─────────────────────────────────────────────────────────────
_MONTH_MAP: dict[str, int] = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4,
    "MAY": 5, "JUN": 6, "JUL": 7, "AUG": 8,
    "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}

# Full ticker pattern: SERIES-DATEPART-TVALUE
# SERIES:   one or more uppercase letters/digits (no dash)
# DATEPART: exactly 2 digits + 3 uppercase letters + 2 digits
# TVALUE:   T followed by one or more digits
_TICKER_RE = re.compile(
    r"^([A-Z0-9]+)-(\d{2})([A-Z]{3})(\d{2})-T(\d+)$"
)


@dataclass(frozen=True)
class MarketRule:
    """Structured representation of a parsed Kalshi weather ticker.

    `threshold_f` is the temperature the daily high must *reach or exceed* for
    YES to resolve (already adjusted: T79 ticker -> threshold_f 80).  None for
    rain markets, which have no numeric threshold.

    `resolution_date` is the local calendar date on which weather is measured,
    in ISO 8601 format (YYYY-MM-DD).  This is local to the market's city, so
    callers using it for historical-forecast lookups should pair it with the
    location's timezone.
    """

    ticker: str
    kind: str           # "rain" | "high_temp"
    location_key: str   # key into WEATHER_LOCATIONS
    resolution_date: str  # YYYY-MM-DD
    threshold_f: int | None  # °F; None for rain; for high_temp = T_value + 1


def parse_ticker(ticker: str) -> MarketRule | None:
    """Parse a Kalshi weather ticker into a MarketRule, or None if unrecognised.

    Returns None (rather than raising) for anything we don't confidently
    understand: unknown series, unrecognised month code, or malformed structure.
    The caller should treat None as "abstain" — no trade — not as an error.

    Why so conservative: a wrong city or wrong threshold silently misdirects
    a trade.  The cost of abstaining on a valid ticker we could have parsed is
    a missed opportunity; the cost of trading on a misparsed ticker is a real
    financial loss with no recourse.
    """
    if not ticker:
        return None

    m = _TICKER_RE.match(ticker)
    if m is None:
        return None

    series, yy, mon_str, dd, t_str = m.groups()

    # Only accept explicitly registered series.
    entry = _SERIES_TO_LOCATION.get(series)
    if entry is None:
        return None

    kind, location_key = entry

    # Parse the month code conservatively; reject anything not in the map.
    month = _MONTH_MAP.get(mon_str.upper())
    if month is None:
        return None

    # Build the ISO date.  Year is 2000 + the two-digit segment.
    try:
        year = 2000 + int(yy)
        day = int(dd)
        # Quick validity check without importing datetime fully — just ensure
        # month/day are in plausible range; deeper validation is fine to skip
        # because open-meteo will error on truly invalid dates.
        if not (1 <= month <= 12 and 1 <= day <= 31):
            return None
        resolution_date = f"{year:04d}-{month:02d}-{day:02d}"
    except ValueError:
        return None

    # Threshold: None for rain; for high_temp the T value is the exceedance
    # floor (T79 -> YES if high > 79, i.e. >= 80), so we add 1 here once so
    # all callers can use >= without remembering the off-by-one.
    threshold_f: int | None = None
    if kind == "high_temp":
        threshold_f = int(t_str) + 1

    return MarketRule(
        ticker=ticker,
        kind=kind,
        location_key=location_key,
        resolution_date=resolution_date,
        threshold_f=threshold_f,
    )
