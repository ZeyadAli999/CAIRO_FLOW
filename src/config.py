"""App-wide configuration constants and paths."""
from __future__ import annotations

from pathlib import Path

PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
DATA_DIR: Path = PROJECT_ROOT / "data"
RAW_DIR: Path = DATA_DIR / "raw"
DB_PATH: Path = DATA_DIR / "cairo.db"
DB_URL: str = f"sqlite:///{DB_PATH.as_posix()}"

CSV_FILES: dict[str, str] = {
    "neighborhoods": "neighborhoods.csv",
    "facilities": "facilities.csv",
    "existing_roads": "existing_roads.csv",
    "potential_roads": "potential_roads.csv",
    "traffic_flow": "traffic_flow.csv",
    "metro_lines": "metro_lines.csv",
    "bus_routes": "bus_routes.csv",
    "transit_demand": "transit_demand.csv",
}

MAP_CENTER: tuple[float, float] = (30.05, 31.25)
MAP_ZOOM: int = 11
DARK_TILE_URL: str = "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
DARK_TILE_ATTRIBUTION: str = (
    '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> '
    '&copy; <a href="https://carto.com/attributions">CARTO</a>'
)

TIMES_OF_DAY: list[str] = ["Morning", "Afternoon", "Evening", "Night"]
DEFAULT_TIME_OF_DAY: str = "Morning"

MODES: list[dict[str, str]] = [
    {"id": "network",   "label": "Network",   "icon": "lucide:network"},
    {"id": "route",     "label": "Route",     "icon": "lucide:route"},
    {"id": "emergency", "label": "Emergency", "icon": "lucide:siren"},
    {"id": "maintain",  "label": "Maintain",  "icon": "lucide:wrench"},
    {"id": "transit",   "label": "Transit",   "icon": "lucide:bus"},
]
DEFAULT_MODE: str = "route"
