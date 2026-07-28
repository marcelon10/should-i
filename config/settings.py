"""
Central configuration for the "should-i" data platform.

Everything the pipelines need to know about *you* lives here:
where you are, what you care about, and where data lands.
Change LOCATION to your own coordinates before running.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# --- Paths --------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("SHOULD_I_DATA_DIR", PROJECT_ROOT / "data"))
RAW_DIR = DATA_DIR / "raw"
WAREHOUSE_PATH = DATA_DIR / "warehouse" / "should_i.duckdb"


# --- Who / where you are ------------------------------------------------
@dataclass(frozen=True)
class Location:
    name: str
    latitude: float
    longitude: float
    timezone: str


# CHANGE THIS to your own location.
LOCATION = Location(
    name="Juiz de Fora",
    latitude=-21.771059,
    longitude=-43.348787,
    timezone="America/Sao_Paulo",
)


# --- Your personal thresholds ------------------------------------------
# These turn raw numbers into decisions. Tune to taste.
@dataclass(frozen=True)
class Thresholds:
    max_bike_aqi: int = 100  # won't bike above this air quality index
    max_bike_wind_kmh: float = 35.0  # too gusty to enjoy
    max_bike_precip_prob: int = 40  # % chance of rain that kills the idea
    min_run_temp_c: float = 4.0
    max_run_temp_c: float = 30.0
    cheap_power_percentile: int = 30  # bottom X% of day's prices = "cheap"


THRESHOLDS = Thresholds()


# --- Source registry ----------------------------------------------------
@dataclass(frozen=True)
class SourceConfig:
    name: str
    kind: str  # "batch" | "incremental" | "reference"
    base_url: str
    params: dict = field(default_factory=dict)


SOURCES = {
    "weather": SourceConfig(
        name="weather",
        kind="batch",
        base_url="https://api.open-meteo.com/v1/forecast",
        params={
            "hourly": "temperature_2m,precipitation_probability,wind_speed_10m",
            "daily": "temperature_2m_max,temperature_2m_min,"
            "precipitation_probability_max,wind_speed_10m_max",
            "forecast_days": 2,
        },
    ),
    # Phase 2 adds: air quality (OpenAQ), electricity prices, etc.
}
