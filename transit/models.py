"""
Shared data models for the transit-board plugin.
"""

from dataclasses import dataclass, field
from typing import List


@dataclass
class Arrival:
    """A single upcoming train arrival at a station."""
    route_id: str        # "N", "D", "1"
    direction_id: int    # 0=outbound/south, 1=inbound/north
    direction_label: str # "Uptown & Queens", "Coney Island-Stillwell Av"
    minutes: int         # minutes until arrival (0 = arriving now)


@dataclass
class StationInfo:
    """Static information about a transit stop."""
    stop_id: str         # GTFS Stop ID (e.g., "R16") — primary lookup key
    station_id: str      # Numeric Station ID from CSV (e.g., "436")
    name: str
    routes: List[str]    # ["N", "Q", "R", "W"]
    north_label: str     # "Uptown & Queens"
    south_label: str     # "Downtown & Brooklyn"


@dataclass
class StopsSource:
    """Describes where to fetch static stop data for an agency."""
    primary_url: str    # data API endpoint (e.g. data.ny.gov JSON)
    fallback_url: str   # CSV download fallback
    column_map: dict    # maps CSV column names to StopsDatabase fields


@dataclass
class DirectionGroup:
    """A route+direction pair with its upcoming arrival times."""
    route_id: str
    direction_label: str
    arrivals: List[int]  # sorted ascending, e.g. [1, 5, 12]
    color: str           # official hex color, e.g. "#FCCC0A"
