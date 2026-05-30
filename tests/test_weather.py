"""Tests for the weather feature source.

No network: a fake session records the request and returns a canned forecast, so
we can assert both the math and — critically — the **no-lookahead contract**:
the historical path must query the forecast *archive* for the given date and the
`precipitation_probability` *forecast* field, never an observations endpoint or
the `precipitation` *observed* field (that would leak settlement data into a
feature).

Run standalone:   uv run python tests/test_weather.py
Or with pytest:   uv run pytest -q tests/test_weather.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kalshi_agent.weather import (
    _ARCHIVE_FORECAST_URL,
    _HIGH_TEMP_SCALE_F,
    _LIVE_URL,
    WEATHER_LOCATIONS,
    MeteoSource,
    rain_probability,
)


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class _FakeSession:
    """Records (url, params) of each GET and returns a fixed payload."""

    def __init__(self, pops):
        self._payload = {"hourly": {"precipitation_probability": pops}}
        self.calls: list[tuple[str, dict]] = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        return _FakeResp(self._payload)


class _FakeHighTempSession:
    """Records (url, params) and returns a canned daily high-temp payload."""

    def __init__(self, high_f: float | None):
        # Wrap in a list as Open-Meteo does; None simulates a missing value.
        values = [high_f] if high_f is not None else [None]
        self._payload = {"daily": {"temperature_2m_max": values}}
        self.calls: list[tuple[str, dict]] = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        return _FakeResp(self._payload)


def _high_source_with(high_f: float | None) -> tuple[MeteoSource, _FakeHighTempSession]:
    src = MeteoSource()
    fake = _FakeHighTempSession(high_f)
    src._session = fake
    return src, fake


def _source_with(pops) -> tuple[MeteoSource, _FakeSession]:
    src = MeteoSource()
    fake = _FakeSession(pops)
    src._session = fake  # inject the fake transport
    return src, fake


# --- pure math -----------------------------------------------------------

def test_rain_probability_weighting():
    assert rain_probability([]) == 0.5            # empty -> display default
    assert rain_probability([1.0]) == 1.0         # 0.65*1 + 0.35*1
    assert rain_probability([0.0, 1.0]) == 0.825  # peak 1.0, avg 0.5
    assert rain_probability([0.2, 0.2, 0.2]) == 0.2
    # Peak must dominate: one rainy hour outweighs a flat low day of equal mean.
    spiky = rain_probability([0.0, 0.0, 0.0, 1.0])      # peak 1.0, avg 0.25
    flat = rain_probability([0.25, 0.25, 0.25, 0.25])   # peak 0.25, avg 0.25
    assert spiky > flat


# --- live path -----------------------------------------------------------

def test_live_path_url_params_and_features():
    src, fake = _source_with([0, 50, None, 100])  # None must be dropped
    feats = src.precip_features(40.0, -73.0, timezone="America/New_York")

    url, params = fake.calls[0]
    assert url == _LIVE_URL
    assert params["forecast_days"] == 1
    assert "start_date" not in params               # live: no date window
    assert params["hourly"] == "precipitation_probability"

    # pops normalized to [0,0.5,1.0]; peak 1.0, avg 0.5 -> 0.825
    assert feats["fair_prob_yes"] == 0.825
    assert feats["weather_hours"] == 3              # None filtered out
    assert feats["weather_max_pop"] == 1.0
    assert feats["weather_source"] == "open-meteo:forecast"
    assert feats["weather_as_of_date"] is None
    assert feats["weather_confidence"] == "medium"


# --- historical / no-lookahead path -------------------------------------

def test_historical_path_is_no_lookahead():
    src, fake = _source_with([20, 20])
    feats = src.precip_features(40.0, -73.0, timezone="UTC", as_of_date="2025-03-01")

    url, params = fake.calls[0]
    # The whole no-lookahead guarantee in two assertions:
    assert url == _ARCHIVE_FORECAST_URL                 # archived *forecast*, not observations
    assert params["hourly"] == "precipitation_probability"  # forecast field, not observed `precipitation`
    assert params["start_date"] == params["end_date"] == "2025-03-01"
    assert "forecast_days" not in params

    assert feats["fair_prob_yes"] == 0.2
    assert feats["weather_source"] == "open-meteo:historical-forecast"
    assert feats["weather_as_of_date"] == "2025-03-01"


# --- no-signal abstention -----------------------------------------------

def test_no_signal_returns_none_not_fifty():
    # Both an empty array and an all-null array must mean "no signal", so decide
    # abstains rather than reading rain_probability's 0.5 display default.
    for pops in ([], [None, None]):
        src, _ = _source_with(pops)
        feats = src.precip_features(0.0, 0.0)
        assert feats["fair_prob_yes"] is None
        assert feats["weather_hours"] == 0
        assert feats["weather_max_pop"] is None
        assert feats["weather_confidence"] == "low"


# --- registry convenience ------------------------------------------------

def test_precip_features_for_uses_registry_coords():
    src, fake = _source_with([100])
    feats = src.precip_features_for("NYC")

    _, params = fake.calls[0]
    loc = WEATHER_LOCATIONS["NYC"]
    assert params["latitude"] == loc.lat
    assert params["longitude"] == loc.lon
    assert params["timezone"] == loc.timezone
    assert feats["fair_prob_yes"] == 1.0


# ── high-temp live vs historical URL/param switch ─────────────────────────────

def test_high_temp_live_path_url_and_params():
    src, fake = _high_source_with(82.5)
    feats = src.high_temp_features(40.0, -73.0, threshold_f=80, timezone="America/New_York")

    url, params = fake.calls[0]
    assert url == _LIVE_URL
    assert params["forecast_days"] == 1
    assert "start_date" not in params
    assert params["daily"] == "temperature_2m_max"
    assert params["temperature_unit"] == "fahrenheit"

    assert feats["weather_source"] == "open-meteo:forecast"
    assert feats["weather_as_of_date"] is None
    assert feats["weather_forecast_high_f"] == 82.5
    assert feats["weather_threshold_f"] == 80
    assert feats["weather_confidence"] == "medium"
    # margin = 82.5 - 80 = 2.5; logistic(2.5 / 2.5) = logistic(1.0) ≈ 0.7311
    import math
    expected = round(1 / (1 + math.exp(-2.5 / _HIGH_TEMP_SCALE_F)), 4)
    assert feats["fair_prob_yes"] == expected


def test_high_temp_historical_path_is_no_lookahead():
    src, fake = _high_source_with(75.0)
    feats = src.high_temp_features(
        40.0, -73.0, threshold_f=80,
        timezone="America/New_York", as_of_date="2025-06-01"
    )

    url, params = fake.calls[0]
    assert url == _ARCHIVE_FORECAST_URL          # archived forecast, never observations
    assert params["daily"] == "temperature_2m_max"
    assert params["temperature_unit"] == "fahrenheit"
    assert params["start_date"] == params["end_date"] == "2025-06-01"
    assert "forecast_days" not in params

    assert feats["weather_source"] == "open-meteo:historical-forecast"
    assert feats["weather_as_of_date"] == "2025-06-01"


def test_high_temp_logistic_at_zero_margin():
    # Exactly at the threshold -> logistic(0) = 0.5
    src, _ = _high_source_with(80.0)
    feats = src.high_temp_features(0.0, 0.0, threshold_f=80)
    assert feats["fair_prob_yes"] == 0.5


def test_high_temp_logistic_above_threshold():
    # Well above -> prob > 0.5
    src, _ = _high_source_with(90.0)
    feats = src.high_temp_features(0.0, 0.0, threshold_f=80)
    assert feats["fair_prob_yes"] is not None
    assert feats["fair_prob_yes"] > 0.5


def test_high_temp_logistic_below_threshold():
    # Well below -> prob < 0.5
    src, _ = _high_source_with(70.0)
    feats = src.high_temp_features(0.0, 0.0, threshold_f=80)
    assert feats["fair_prob_yes"] is not None
    assert feats["fair_prob_yes"] < 0.5


def test_high_temp_missing_forecast_gives_none_prob():
    # Open-Meteo returned a null value -> no signal, strategy abstains
    src, _ = _high_source_with(None)
    feats = src.high_temp_features(0.0, 0.0, threshold_f=80)
    assert feats["fair_prob_yes"] is None
    assert feats["weather_confidence"] == "low"
    assert feats["weather_forecast_high_f"] is None


def test_high_temp_features_for_uses_registry():
    src, fake = _high_source_with(95.0)
    feats = src.high_temp_features_for("MIA", threshold_f=90)

    _, params = fake.calls[0]
    loc = WEATHER_LOCATIONS["MIA"]
    assert params["latitude"] == loc.lat
    assert params["longitude"] == loc.lon
    assert params["timezone"] == loc.timezone
    # margin = 95 - 90 = 5; prob should be > 0.5
    assert feats["fair_prob_yes"] is not None
    assert feats["fair_prob_yes"] > 0.5


def test_new_locations_in_registry():
    # Ensure the three new cities are present and have the expected timezones.
    assert "LAX" in WEATHER_LOCATIONS
    assert WEATHER_LOCATIONS["LAX"].timezone == "America/Los_Angeles"
    assert "AUS" in WEATHER_LOCATIONS
    assert WEATHER_LOCATIONS["AUS"].timezone == "America/Chicago"
    assert "DEN" in WEATHER_LOCATIONS
    assert WEATHER_LOCATIONS["DEN"].timezone == "America/Denver"


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
