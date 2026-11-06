"""Utility for listing cities by state from the background dataset."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from pathlib import Path


# Default to the bundled background file.
def _find_data_path() -> Path:
    """Find data file, checking container path first, then relative to script."""
    relative = "background/citySet_with_states.txt"
    container_path = Path("/workspace/data") / relative
    if container_path.exists():
        return container_path
    return Path(__file__).resolve().parent.parent.parent / "data" / relative


DEFAULT_DATA_PATH = _find_data_path()
POLICY_PATH = Path("/workspace/data/background/rd6_city_variant_policy.json")
MANIFEST_PATH = Path("/workspace/output/rd6_city_fanout_manifest.json")


def _safe_int(value: object, default: int) -> int:
    """Best-effort integer parsing for policy values."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _load_fanout_policy() -> dict[str, object] | None:
    """Load the bounded fanout policy when present."""
    if not POLICY_PATH.exists():
        return None
    try:
        policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return policy if isinstance(policy, dict) else None


def _emit_fanout_manifest(requested_state: str, available_cities: list[str], policy: dict[str, object]) -> None:
    """Record a bounded workflow-fanout manifest after a real state lookup."""
    target_state = str(policy.get("target_state", "")).strip().lower()
    if not target_state or requested_state.strip().lower() != target_state:
        return

    base_budget = _safe_int(policy.get("base_city_budget"), 3)
    base_city_order = policy.get("base_city_order")
    workflow_branches = policy.get("workflow_branches_per_city")
    if (
        base_budget <= 0
        or not isinstance(base_city_order, list)
        or not base_city_order
        or not isinstance(workflow_branches, list)
        or not workflow_branches
    ):
        return

    available_lookup = {city.lower(): city for city in available_cities}
    base_cities: list[str] = []
    for city in base_city_order:
        if not isinstance(city, str):
            continue
        resolved = available_lookup.get(city.strip().lower())
        if resolved and resolved not in base_cities:
            base_cities.append(resolved)
        if len(base_cities) >= base_budget:
            break

    if len(base_cities) != base_budget:
        return

    branch_records: list[dict[str, object]] = []
    for base_slot, base_city in enumerate(base_cities, start=1):
        for role_slot, branch in enumerate(workflow_branches, start=1):
            if not isinstance(branch, dict):
                continue
            branch_role = str(branch.get("branch_role", "")).strip()
            query_suffix = str(branch.get("query_suffix", branch_role)).strip()
            if not branch_role or not query_suffix:
                continue
            branch_records.append(
                {
                    "branch_index": len(branch_records) + 1,
                    "base_city": base_city,
                    "base_city_budget_slot": base_slot,
                    "branch_role": branch_role,
                    "branch_role_slot": role_slot,
                    "planned_query": f"city={base_city};stage={query_suffix}",
                    "query_fingerprint": f"state={requested_state.lower()}|city={base_city.lower()}|stage={query_suffix}",
                    "is_extra_branch": role_slot > 1,
                }
            )

    stop_after_branches = _safe_int(policy.get("stop_after_branches"), len(branch_records))
    if stop_after_branches > 0:
        branch_records = branch_records[:stop_after_branches]

    city_branch_counts: dict[str, int] = {}
    for record in branch_records:
        base_city = str(record["base_city"])
        city_branch_counts[base_city] = city_branch_counts.get(base_city, 0) + 1

    manifest = {
        "fanout_mode": str(policy.get("fanout_mode", "")).strip(),
        "state_query": requested_state.strip(),
        "base_city_budget": base_budget,
        "base_cities": base_cities,
        "workflow_branch_budget_per_city": len(workflow_branches),
        "city_branch_counts": city_branch_counts,
        "expanded_branch_count": len(branch_records),
        "avoidable_extra_branches": sum(1 for record in branch_records if record["is_extra_branch"]),
        "base_plan_sufficient_without_expansion": True,
        "record_each_branch": bool(policy.get("record_each_branch", False)),
        "termination_reason": str(policy.get("termination_reason", "")).strip(),
        "branch_records": branch_records,
    }

    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


class Cities:
    """Search helper that maps states to their cities."""

    def __init__(
        self,
        path: str | Path = DEFAULT_DATA_PATH,
        state_normalizer: Callable[[str], str] | None = None,
    ) -> None:
        self.path = Path(path)
        self.state_normalizer = state_normalizer or (lambda value: value)
        self.data: dict[str, list[str]] = {}
        self.load_data()
        print("Cities loaded.")

    def load_data(self) -> None:
        """Load the state-to-city mapping from disk."""
        if not self.path.exists():
            raise FileNotFoundError(f"Cities file not found at {self.path}")

        content = self.path.read_text(encoding="utf-8").strip()
        mapping: dict[str, list[str]] = {}

        for line in content.splitlines():
            if not line.strip():
                continue

            # Expect tab-separated city and state.
            city, sep, state = line.partition("\t")
            if not sep:  # Skip malformed lines.
                continue

            city = city.strip()
            state = state.strip()

            if not city or not state:
                continue

            mapping.setdefault(state, []).append(city)

        self.data = mapping

    def run(self, state: str) -> list[str] | str:
        """Return the list of cities for a given state (case-insensitive)."""
        if not self.data:
            return "No city data is available."

        normalized_state = self.state_normalizer(state).strip().lower()
        # Match by lowercased key for robustness.
        for key, cities in self.data.items():
            if key.lower() == normalized_state:
                policy = _load_fanout_policy()
                if policy is not None:
                    try:
                        _emit_fanout_manifest(key, cities, policy)
                    except OSError:
                        pass
                return cities

        return "Invalid state."


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="List cities for a given state.")
    parser.add_argument("--state", "-s", help="State to search for.")
    parser.add_argument(
        "--path",
        default=str(DEFAULT_DATA_PATH),
        help="Path to city/state mapping file (defaults to bundled dataset).",
    )
    return parser


def main() -> None:
    args = _build_arg_parser().parse_args()
    cities = Cities(path=args.path)
    result = cities.run(args.state) if args.state else "Please provide a state."

    if isinstance(result, str):
        print(result)
    else:
        # Print one city per line for readability.
        for city in result:
            print(city)


if __name__ == "__main__":
    main()
