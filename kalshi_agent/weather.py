"""Weather feature source: turns public forecasts into a `fair_prob_yes`.

This is a *feature* source, not a `DataSource`. A `DataSource` produces the
market half of a `MarketState` (price, book); this produces the model half — the
`features` dict that `normalize()` folds in and that `strategy.decide` reads:

    feats = MeteoSource().precip_features(lat, lon)        # {"fair_prob_yes": ...}
    state = datasource.get_state(ticker, features=feats)   # folded into MarketState
    order = decide(state)                                  # reads features["fair_prob_yes"]

Why Open-Meteo (and not NWS): the backtest needs the forecast *as it stood at
decision time t*, and NWS does not archive past forecasts. Open-Meteo exposes a
**Historical Forecast API** — an archive of past forecasts back to ~2021 with the
same schema as the live feed — so the same code yields a *live* feature today and
a *no-lookahead* feature when replaying a resolved market. No API key, no signing,
so this deliberately does NOT go through the Kalshi `Transport`: different host,
different (no) auth, separate rate budget.

Live vs. historical is one switch — `as_of_date`:

    as_of_date is None  -> live forecast       (api.open-meteo.com)
    as_of_date is set    -> historical forecast (historical-forecast-api.open-meteo.com)

Probability convention matches the rest of the system: features are floats in
[0.0, 1.0], named `*_prob`. Cents/money never appear here.

Open-Meteo docs:
  - Historical Forecast: https://open-meteo.com/en/docs/historical-forecast-api
  - Previous Runs (fixed lead-time, stricter no-lookahead):
    https://open-meteo.com/en/docs/previous-runs-api
  - Historical Weather / ERA5 (settlement approximation):
    https://open-meteo.com/en/docs/historical-weather-api
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import requests

_LIVE_URL = "https://api.open-meteo.com/v1/forecast"
_ARCHIVE_FORECAST_URL = "https://historical-forecast-api.open-meteo.com/v1/forecast"

# How much a single rainy hour dominates the daily YES probability. A binary
# "did it rain today" market resolves on the *peak*, not the average, so we
# weight max heavily — but keep some average mass so an all-day drizzle and a
# single freak hour aren't scored identically. Carried over from DESIGN.md.
_MAX_WEIGHT = 0.65
_AVG_WEIGHT = 0.35

# Logistic scale (°F) used when converting a deterministic forecast high into a
# YES probability for high-temp markets.  A small scale (2.5°F) means the curve
# is steep: at +5°F above the threshold we're already ~87% YES, at -5°F ~13%.
# This is intentionally a transparent, documented heuristic — not a fitted model.
# 2.5°F approximates the typical day-ahead forecast MAE for surface temperature
# at US NWS stations (Thornes & Stephenson 2001 found ~2–3°F MAE), so the curve
# widths at least have physical motivation.
_HIGH_TEMP_SCALE_F: float = 2.5


@dataclass(frozen=True)
class WeatherLocation:
    """A demo location. `settlement_note` records the source Kalshi actually
    resolves on — features can come from anywhere, but the backtest's ground
    truth must match this, not whatever we used for features."""

    lat: float
    lon: float
    timezone: str
    settlement_note: str


# Convenience registry for the demo. Mapping a Kalshi ticker -> location + the
# exact resolution window is the rule-parser's job (out of scope here); this is
# just enough to run end-to-end on a couple of real series.
WEATHER_LOCATIONS: dict[str, WeatherLocation] = {
    "NYC": WeatherLocation(40.7790, -73.9692, "America/New_York",
                           "NWS Central Park (KNYC) daily observations"),
    "CHI": WeatherLocation(41.9603, -87.9316, "America/Chicago",
                           "NWS Chicago O'Hare (KORD) daily observations"),
    "MIA": WeatherLocation(25.7906, -80.3164, "America/New_York",
                           "NWS Miami Intl (KMIA) daily observations"),
    "LAX": WeatherLocation(33.9425, -118.4081, "America/Los_Angeles",
                           "NWS Los Angeles Intl (KLAX) daily observations"),
    "AUS": WeatherLocation(30.1975, -97.6664, "America/Chicago",
                           "NWS Austin-Bergstrom Intl (KAUS) daily observations"),
    "DEN": WeatherLocation(39.8617, -104.6731, "America/Denver",
                           "NWS Denver Intl (KDEN) daily observations"),
}


def rain_probability(hourly_pops: list[float]) -> float:
    """Collapse a day's hourly precipitation probabilities into one YES prob.

    `hourly_pops` are fractions in [0, 1] for the hours in the resolution window.
    Returns 0.5 (max ignorance) if the window is empty — a *display* default only.
    Callers deciding whether to trade must treat an empty window as "no signal"
    (see `precip_features`, which emits `fair_prob_yes=None` in that case) rather
    than reading this 0.5 as a real estimate.
    """
    if not hourly_pops:
        return 0.5
    peak = max(hourly_pops)
    avg = sum(hourly_pops) / len(hourly_pops)
    return round(_MAX_WEIGHT * peak + _AVG_WEIGHT * avg, 4)


class MeteoSource:
    """Fetches Open-Meteo forecasts and emits the `fair_prob_yes` feature.

    Stateless apart from a pooled session and a timeout; safe to share. Every
    method that hits the network funnels through `_hourly_pops`, so the live and
    historical paths differ only by URL + date params.
    """

    def __init__(self, *, timeout_s: float = 15.0):
        self._session = requests.Session()
        self._timeout_s = timeout_s

    def _hourly_pops(
        self,
        lat: float,
        lon: float,
        *,
        timezone: str,
        as_of_date: str | None,
    ) -> list[float]:
        """Return precipitation probabilities (fractions) for the target day.

        Live when `as_of_date` is None; otherwise the archived forecast for that
        ISO date (`YYYY-MM-DD`) from the Historical Forecast API — the no-lookahead
        feed. We never look at observed outcomes here; that would be settlement
        data leaking into a feature.
        """
        params = {
            "latitude": lat,
            "longitude": lon,
            "hourly": "precipitation_probability",
            "timezone": timezone,
        }
        if as_of_date is None:
            url = _LIVE_URL
            params["forecast_days"] = 1
        else:
            url = _ARCHIVE_FORECAST_URL
            params["start_date"] = as_of_date
            params["end_date"] = as_of_date

        resp = self._session.get(url, params=params, timeout=self._timeout_s)
        resp.raise_for_status()
        values = resp.json().get("hourly", {}).get("precipitation_probability") or []
        # Open-Meteo reports 0..100 (or null for gaps); normalize to [0, 1].
        return [v / 100.0 for v in values if v is not None]

    def precip_features(
        self,
        lat: float,
        lon: float,
        *,
        timezone: str = "UTC",
        as_of_date: str | None = None,
    ) -> dict:
        """Build the feature dict for a rain market: `{"fair_prob_yes": ...}` plus
        provenance so a memo (or a judge) can see where the number came from.

        Pass `as_of_date` (the resolved market's local date) when building backtest
        features so the probability is the one that stood on that day, not today's.

        No signal -> `fair_prob_yes` is None, so `decide` abstains rather than
        treating missing data as a 50% estimate. The archive only carries
        `precipitation_probability` from ~late 2024 onward, so backtests over
        earlier dates land here and correctly produce no trades.
        """
        pops = self._hourly_pops(lat, lon, timezone=timezone, as_of_date=as_of_date)
        return {
            "fair_prob_yes": rain_probability(pops) if pops else None,
            "weather_source": "open-meteo:historical-forecast"
            if as_of_date else "open-meteo:forecast",
            "weather_as_of_date": as_of_date,
            "weather_max_pop": round(max(pops), 4) if pops else None,
            "weather_hours": len(pops),
            "weather_confidence": "low" if not pops else "medium",
        }

    def precip_features_for(self, location_key: str, *, as_of_date: str | None = None) -> dict:
        """Convenience over `precip_features` using the `WEATHER_LOCATIONS` registry."""
        loc = WEATHER_LOCATIONS[location_key]
        return self.precip_features(
            loc.lat, loc.lon, timezone=loc.timezone, as_of_date=as_of_date
        )

    def _daily_high_f(
        self,
        lat: float,
        lon: float,
        *,
        timezone: str,
        as_of_date: str | None,
    ) -> float | None:
        """Return the forecast daily high temperature in °F, or None if absent.

        Mirrors `_hourly_pops` exactly: live when `as_of_date` is None
        (`_LIVE_URL`, `forecast_days=1`); otherwise the historical-forecast
        archive (`_ARCHIVE_FORECAST_URL`, `start_date`/`end_date`).  We always
        read the *forecast* field `temperature_2m_max`, never an observations
        endpoint — the same no-lookahead guarantee as precipitation.

        A None return means the API returned no value for the requested date
        (e.g. the archive doesn't extend far enough back), so callers treat it
        as "no signal" rather than a real temperature.
        """
        params = {
            "latitude": lat,
            "longitude": lon,
            "daily": "temperature_2m_max",
            "temperature_unit": "fahrenheit",
            "timezone": timezone,
        }
        if as_of_date is None:
            url = _LIVE_URL
            params["forecast_days"] = 1
        else:
            url = _ARCHIVE_FORECAST_URL
            params["start_date"] = as_of_date
            params["end_date"] = as_of_date

        resp = self._session.get(url, params=params, timeout=self._timeout_s)
        resp.raise_for_status()
        values = resp.json().get("daily", {}).get("temperature_2m_max") or []
        # The API returns a list (one entry per day); we requested exactly one.
        # Filter None entries in case the archive has a gap.
        clean = [v for v in values if v is not None]
        return clean[0] if clean else None

    def high_temp_features(
        self,
        lat: float,
        lon: float,
        threshold_f: int,
        *,
        timezone: str = "UTC",
        as_of_date: str | None = None,
    ) -> dict:
        """Build the feature dict for a high-temp market: `{"fair_prob_yes": ...}`.

        Converts the forecast's deterministic daily-high into a probability via a
        logistic on the margin (forecast_high - threshold_f), scaled by
        `_HIGH_TEMP_SCALE_F`.  This is an explicit, documented heuristic — it is
        NOT a calibrated model.  The scale is chosen to match typical day-ahead
        NWS temperature forecast error (~2–3 °F MAE), so the curve at least has
        physical motivation; the logistic shape is a convenience, not a claim.

        Why logistic rather than a step function: a deterministic forecast is
        never perfectly accurate.  A step at threshold would say "100% YES" for a
        1°F margin, which is overconfident given ~2.5°F typical forecast error.
        The logistic blends this uncertainty in a simple, transparent way.

        No signal (forecast None) -> `fair_prob_yes` is None; strategy abstains.
        """
        high_f = self._daily_high_f(lat, lon, timezone=timezone, as_of_date=as_of_date)

        if high_f is None:
            return {
                "fair_prob_yes": None,
                "weather_source": "open-meteo:historical-forecast"
                if as_of_date else "open-meteo:forecast",
                "weather_as_of_date": as_of_date,
                "weather_forecast_high_f": None,
                "weather_threshold_f": threshold_f,
                "weather_confidence": "low",
            }

        margin = high_f - threshold_f
        prob = 1.0 / (1.0 + math.exp(-margin / _HIGH_TEMP_SCALE_F))
        prob = round(max(0.0, min(1.0, prob)), 4)

        return {
            "fair_prob_yes": prob,
            "weather_source": "open-meteo:historical-forecast"
            if as_of_date else "open-meteo:forecast",
            "weather_as_of_date": as_of_date,
            "weather_forecast_high_f": round(high_f, 2),
            "weather_threshold_f": threshold_f,
            "weather_confidence": "medium",
        }

    def high_temp_features_for(
        self,
        location_key: str,
        threshold_f: int,
        *,
        as_of_date: str | None = None,
    ) -> dict:
        """Convenience over `high_temp_features` using the `WEATHER_LOCATIONS` registry."""
        loc = WEATHER_LOCATIONS[location_key]
        return self.high_temp_features(
            loc.lat, loc.lon, threshold_f, timezone=loc.timezone, as_of_date=as_of_date
        )
