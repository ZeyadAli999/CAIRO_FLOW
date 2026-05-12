"""Non-destructive validation for CairoFlow transportation data."""
from __future__ import annotations

from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

from src.data.data_enrichment import as_record, normalized_pair


@dataclass(frozen=True)
class ValidationIssue:
    severity: str
    code: str
    message: str
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationReport:
    issues: list[ValidationIssue] = field(default_factory=list)
    node_count: int = 0
    facility_count: int = 0
    existing_road_count: int = 0
    potential_road_count: int = 0
    duplicate_bidirectional_roads: list[dict[str, Any]] = field(default_factory=list)
    isolated_nodes: list[str] = field(default_factory=list)
    isolated_medical_facilities: list[str] = field(default_factory=list)
    connected_components: list[list[str]] = field(default_factory=list)

    def add(self, severity: str, code: str, message: str, **context: Any) -> None:
        self.issues.append(ValidationIssue(severity, code, message, context))

    @property
    def fatal_errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "fatal"]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def infos(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "info"]

    @property
    def ok(self) -> bool:
        return not self.fatal_errors


def _ids(records: list[dict], key: str = "id") -> list[str]:
    return [str(r.get(key)) for r in records]


def _split_ids(value: Any) -> list[str]:
    if value is None:
        return []
    return [part.strip() for part in str(value).split(",") if part.strip()]


def validate_source_data(data: dict[str, list[Any]]) -> ValidationReport:
    """Validate source data and return a report instead of raising."""
    neighborhoods = [as_record(r) for r in data.get("neighborhoods", [])]
    facilities = [as_record(r) for r in data.get("facilities", [])]
    existing = [as_record(r) for r in data.get("existing_roads", [])]
    potential = [as_record(r) for r in data.get("potential_roads", [])]
    traffic = [as_record(r) for r in data.get("traffic_flow", [])]
    metros = [as_record(r) for r in data.get("metro_lines", [])]
    buses = [as_record(r) for r in data.get("bus_routes", [])]
    demands = [as_record(r) for r in data.get("transit_demand", [])]

    report = ValidationReport(
        node_count=len(neighborhoods) + len(facilities),
        facility_count=len(facilities),
        existing_road_count=len(existing),
        potential_road_count=len(potential),
    )

    node_ids = set(_ids(neighborhoods)) | set(_ids(facilities))
    _check_unique(report, _ids(neighborhoods) + _ids(facilities), "node", "Node ID")
    _check_unique(report, _ids(facilities), "facility", "Facility ID")

    for road in existing:
        _check_endpoint(report, road, node_ids, "existing_road_endpoint")
        _check_positive(report, road, "distance_km", "existing_road_distance")
        _check_positive(report, road, "capacity", "existing_road_capacity")
        condition = _num(road.get("condition"))
        if condition is None or condition < 1 or condition > 10:
            report.add(
                "fatal", "road_condition_range",
                "Existing road condition must be between 1 and 10.",
                road=road,
            )

    for road in potential:
        _check_endpoint(report, road, node_ids, "potential_road_endpoint")
        _check_positive(report, road, "distance_km", "potential_road_distance")
        _check_positive(report, road, "capacity", "potential_road_capacity")
        _check_positive(report, road, "cost_million_egp", "construction_cost")

    existing_pairs = {normalized_pair(r.get("from_id"), r.get("to_id")) for r in existing}
    for row in traffic:
        pair = normalized_pair(row.get("from_id"), row.get("to_id"))
        if pair not in existing_pairs:
            report.add(
                "warning", "traffic_without_existing_road",
                "Traffic row does not match an existing road.",
                traffic_row=row,
            )
        for key in ("morning_peak", "afternoon", "evening_peak", "night"):
            value = _num(row.get(key))
            if value is None or value < 0:
                report.add(
                    "fatal", "traffic_negative",
                    "Traffic values must be non-negative.",
                    field=key, traffic_row=row,
                )

    for metro in metros:
        _check_positive(report, metro, "daily_passengers", "metro_passengers")
        for station in _split_ids(metro.get("stations")):
            if station not in node_ids:
                report.add(
                    "fatal", "metro_station_id",
                    "Metro station ID is not a valid node.",
                    line_id=metro.get("line_id"), station=station,
                )

    for bus in buses:
        _check_positive(report, bus, "daily_passengers", "bus_passengers")
        for stop in _split_ids(bus.get("stops")):
            if stop not in node_ids:
                report.add(
                    "fatal", "bus_stop_id",
                    "Bus stop ID is not a valid node.",
                    route_id=bus.get("route_id"), stop=stop,
                )

    for demand in demands:
        _check_positive(report, demand, "daily_passengers", "demand_passengers")
        for key in ("from_id", "to_id"):
            node_id = str(demand.get(key))
            if node_id not in node_ids:
                report.add(
                    "fatal", "demand_pair_id",
                    "Transit demand endpoint is not a valid node.",
                    field=key, demand=demand,
                )

    _detect_duplicate_bidirectional_roads(report, existing)
    _detect_isolation_and_connectivity(report, node_ids, facilities, existing)

    return report


def _check_unique(
    report: ValidationReport,
    values: list[str],
    code_prefix: str,
    label: str,
) -> None:
    counts = Counter(values)
    duplicates = sorted([value for value, count in counts.items() if count > 1])
    if duplicates:
        report.add(
            "fatal", f"{code_prefix}_id_duplicate",
            f"{label}s must be unique.",
            duplicates=duplicates,
        )


def _check_endpoint(
    report: ValidationReport,
    road: dict,
    node_ids: set[str],
    code: str,
) -> None:
    for key in ("from_id", "to_id"):
        node_id = str(road.get(key))
        if node_id not in node_ids:
            report.add(
                "fatal", code,
                "Road endpoint is not a valid node.",
                field=key, road=road,
            )


def _check_positive(report: ValidationReport, record: dict, field_name: str, code: str) -> None:
    value = _num(record.get(field_name))
    if value is None or value <= 0:
        report.add(
            "fatal", code,
            f"{field_name} must be positive.",
            record=record,
        )


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _detect_duplicate_bidirectional_roads(
    report: ValidationReport, existing: list[dict]
) -> None:
    by_pair: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for road in existing:
        by_pair[normalized_pair(road.get("from_id"), road.get("to_id"))].append(road)
    for pair, roads in sorted(by_pair.items()):
        if len(roads) <= 1:
            continue
        detail = {"pair": pair, "count": len(roads), "roads": roads}
        report.duplicate_bidirectional_roads.append(detail)
        report.add(
            "info", "duplicate_bidirectional_road",
            "Duplicate bidirectional road detected; graph views may normalize it.",
            **detail,
        )


def _detect_isolation_and_connectivity(
    report: ValidationReport,
    node_ids: set[str],
    facilities: list[dict],
    existing: list[dict],
) -> None:
    adjacency: dict[str, set[str]] = {node_id: set() for node_id in node_ids}
    for road in existing:
        u, v = str(road.get("from_id")), str(road.get("to_id"))
        if u in adjacency and v in adjacency:
            adjacency[u].add(v)
            adjacency[v].add(u)

    report.isolated_nodes = sorted([node for node, nbs in adjacency.items() if not nbs])
    if report.isolated_nodes:
        report.add(
            "warning", "isolated_nodes",
            "Some nodes have no existing-road connection.",
            isolated_nodes=report.isolated_nodes,
        )

    medical_ids = {
        str(f.get("id")) for f in facilities if f.get("type") == "Medical"
    }
    report.isolated_medical_facilities = sorted(medical_ids & set(report.isolated_nodes))
    if report.isolated_medical_facilities:
        report.add(
            "warning", "isolated_medical_facilities",
            "Medical facilities are isolated from existing roads.",
            isolated_medical_facilities=report.isolated_medical_facilities,
        )

    seen: set[str] = set()
    components: list[list[str]] = []
    for node in sorted(node_ids):
        if node in seen:
            continue
        queue: deque[str] = deque([node])
        seen.add(node)
        comp: list[str] = []
        while queue:
            cur = queue.popleft()
            comp.append(cur)
            for nb in adjacency[cur]:
                if nb not in seen:
                    seen.add(nb)
                    queue.append(nb)
        components.append(sorted(comp))

    report.connected_components = sorted(components, key=lambda c: (-len(c), c[0]))
    if len(report.connected_components) > 1:
        report.add(
            "warning", "graph_disconnected",
            "Existing-road graph is disconnected.",
            component_count=len(report.connected_components),
            largest_component_size=len(report.connected_components[0]),
        )

