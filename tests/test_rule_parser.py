"""Tests for the Kalshi weather-ticker rule parser.

No network required: parse_ticker is pure string manipulation.

Run standalone:   uv run python tests/test_rule_parser.py
Or with pytest:   uv run pytest -q tests/test_rule_parser.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kalshi_agent.rule_parser import MarketRule, parse_ticker


# ── Rain ticker parsing ───────────────────────────────────────────────────────

def test_rain_nyc_basic():
    rule = parse_ticker("KXRAINNYC-26MAY31-T0")
    assert rule is not None
    assert rule.kind == "rain"
    assert rule.location_key == "NYC"
    assert rule.resolution_date == "2026-05-31"
    assert rule.threshold_f is None
    assert rule.ticker == "KXRAINNYC-26MAY31-T0"


def test_rain_result_is_frozen_dataclass():
    rule = parse_ticker("KXRAINNYC-26MAY31-T0")
    assert isinstance(rule, MarketRule)
    # frozen: mutation must raise
    try:
        rule.kind = "high_temp"  # type: ignore[misc]
        assert False, "should have raised FrozenInstanceError"
    except Exception:
        pass


# ── High-temp ticker parsing ──────────────────────────────────────────────────

def test_high_temp_ny_basic():
    # T79 -> threshold_f 80 (>= 80°F means YES)
    rule = parse_ticker("KXHIGHNY-26MAY31-T79")
    assert rule is not None
    assert rule.kind == "high_temp"
    assert rule.location_key == "NYC"
    assert rule.resolution_date == "2026-05-31"
    assert rule.threshold_f == 80  # T_value + 1


def test_high_temp_threshold_off_by_one():
    # T0 -> threshold_f 1; T99 -> threshold_f 100
    assert parse_ticker("KXHIGHNY-26MAY31-T0").threshold_f == 1
    assert parse_ticker("KXHIGHNY-26MAY31-T99").threshold_f == 100


def test_high_temp_chi():
    rule = parse_ticker("KXHIGHCHI-26MAY31-T70")
    assert rule is not None
    assert rule.location_key == "CHI"
    assert rule.threshold_f == 71


def test_high_temp_mia():
    rule = parse_ticker("KXHIGHMIA-26JUN15-T84")
    assert rule is not None
    assert rule.location_key == "MIA"
    assert rule.resolution_date == "2026-06-15"
    assert rule.threshold_f == 85


def test_high_temp_lax():
    rule = parse_ticker("KXHIGHLAX-26JUL04-T75")
    assert rule is not None
    assert rule.location_key == "LAX"
    assert rule.resolution_date == "2026-07-04"


def test_high_temp_aus():
    rule = parse_ticker("KXHIGHAUS-26AUG20-T95")
    assert rule is not None
    assert rule.location_key == "AUS"


def test_high_temp_den():
    rule = parse_ticker("KXHIGHDEN-26SEP01-T65")
    assert rule is not None
    assert rule.location_key == "DEN"


# ── Date parsing edge cases ───────────────────────────────────────────────────

def test_date_january():
    rule = parse_ticker("KXHIGHNY-26JAN01-T70")
    assert rule is not None
    assert rule.resolution_date == "2026-01-01"


def test_date_december():
    rule = parse_ticker("KXHIGHNY-26DEC25-T45")
    assert rule is not None
    assert rule.resolution_date == "2026-12-25"


def test_date_all_months_parse():
    months = [
        ("JAN", "01"), ("FEB", "02"), ("MAR", "03"), ("APR", "04"),
        ("MAY", "05"), ("JUN", "06"), ("JUL", "07"), ("AUG", "08"),
        ("SEP", "09"), ("OCT", "10"), ("NOV", "11"), ("DEC", "12"),
    ]
    for mon_str, mon_num in months:
        ticker = f"KXHIGHNY-26{mon_str}15-T70"
        rule = parse_ticker(ticker)
        assert rule is not None, f"Failed to parse {ticker}"
        assert rule.resolution_date == f"2026-{mon_num}-15", f"Wrong date for {ticker}"


# ── Conservative None (unknown / malformed) ───────────────────────────────────

def test_none_on_empty_string():
    assert parse_ticker("") is None


def test_none_on_garbage():
    assert parse_ticker("NOTATICKER") is None
    assert parse_ticker("   ") is None
    assert parse_ticker("random-string-here") is None


def test_none_on_unknown_series():
    # KXFOO is not in the registry
    assert parse_ticker("KXFOO-26MAY31-T0") is None


def test_none_on_unknown_city():
    # KXHIGHZZZ is not registered even though prefix looks right
    assert parse_ticker("KXHIGHZZZ-26MAY31-T70") is None


def test_none_on_malformed_date_non_digit_year():
    # Year segment has non-digit
    assert parse_ticker("KXHIGHNY-2XMAY31-T79") is None


def test_none_on_bad_month_code():
    # "ZZZ" is not a month
    assert parse_ticker("KXHIGHNY-26ZZZ15-T70") is None


def test_none_on_missing_t_segment():
    # No threshold at all
    assert parse_ticker("KXHIGHNY-26MAY31") is None


def test_none_on_missing_date_segment():
    assert parse_ticker("KXHIGHNY-T79") is None


def test_none_on_lowercase():
    # Tickers are uppercase; lowercase should not match
    assert parse_ticker("kxhighny-26may31-t79") is None


def test_none_on_extra_segments():
    # Extra dash-separated segment — structure doesn't match the 3-part pattern
    assert parse_ticker("KXHIGHNY-26MAY31-T79-EXTRA") is None


# ── Invariant: rain has no threshold, high_temp always has one ────────────────

def test_rain_threshold_is_always_none():
    rule = parse_ticker("KXRAINNYC-26MAY31-T0")
    assert rule.threshold_f is None


def test_high_temp_threshold_is_never_none():
    rule = parse_ticker("KXHIGHNY-26MAY31-T79")
    assert rule.threshold_f is not None


# ── Standalone runner ─────────────────────────────────────────────────────────

def _run_all() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  ok   {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run_all())
