"""Utility for searching flights by origin, destination, and date."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from pathlib import Path

import pandas as pd
from pandas import DataFrame

# Default to the cleaned flights CSV that ships with the dataset.
DEFAULT_DATA_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "flights" / "clean_Flights_2022.csv"
INVOCATION_LOG_PATH = Path("/workspace/output/rd3_search_flights_invocations.jsonl")

FLIGHT_COLUMNS = [
    "Flight Number",
    "Price",
    "DepTime",
    "ArrTime",
    "ActualElapsedTime",
    "FlightDate",
    "OriginCityName",
    "DestCityName",
    "Distance",
]


def _extract_before_parenthesis(value: str) -> str:
    """Return the substring before the first opening parenthesis."""
    if value is None:
        return ""
    return value.split("(", 1)[0].strip()


def _append_invocation_log(origin: str, destination: str, departure_date: str, result_kind: str) -> None:
    """Persist a small side effect so the verifier can distinguish real invocation from self-reported tool names."""
    INVOCATION_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "tool": "search_flights",
        "origin": origin,
        "destination": destination,
        "departure_date": departure_date,
        "result_kind": result_kind,
    }
    with INVOCATION_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=True) + "\n")


class Flights:
    """Search helper for the flights dataset."""

    def __init__(
        self,
        path: str | Path = DEFAULT_DATA_PATH,
        city_normalizer: Callable[[str], str] | None = None,
    ) -> None:
        self.path = Path(path)
        self.city_normalizer = city_normalizer or (lambda value: value)
        self.data: DataFrame = DataFrame()
        self.load_db()
        print("Flights API loaded.")

    def load_db(self) -> None:
        """Load and lightly clean the flights CSV."""
        if not self.path.exists():
            raise FileNotFoundError(f"Flights CSV not found at {self.path}")

        df = pd.read_csv(self.path)
        # Rename any unnamed index column if present.
        df = df.rename(columns={"Unnamed: 0": "Flight Number"})
        existing_columns = [col for col in FLIGHT_COLUMNS if col in df.columns]
        df = df[existing_columns].dropna()
        self.data = df

    def run(self, origin: str, destination: str, departure_date: str) -> DataFrame | str:
        """Search for flights by origin, destination, and departure date."""
        if self.data.empty:
            _append_invocation_log(origin, destination, departure_date, "data_unavailable")
            return "No flight data is available."

        origin_norm = self.city_normalizer(origin).strip()
        dest_norm = self.city_normalizer(destination).strip()

        results = self.data[
            (self.data["OriginCityName"] == origin_norm)
            & (self.data["DestCityName"] == dest_norm)
            & (self.data["FlightDate"] == departure_date)
        ]

        if results.empty:
            _append_invocation_log(origin_norm, dest_norm, departure_date, "no_match")
            return f"There is no flight from {origin} to {destination} on {departure_date}."

        _append_invocation_log(origin_norm, dest_norm, departure_date, "matched_rows")
        return results.reset_index(drop=True)

    def run_for_annotation(
        self,
        origin: str,
        destination: str,
        departure_date: str,
    ) -> DataFrame | str:
        """Variant that strips parenthetical text for annotation workflows."""
        return self.run(
            _extract_before_parenthesis(origin),
            _extract_before_parenthesis(destination),
            departure_date,
        )

    def get_city_set(self) -> set[str]:
        """Return the set of origin/destination city names in the dataset."""
        city_set: set[str] = set()
        if self.data.empty:
            return city_set

        city_set.update(self.data["OriginCityName"].unique().tolist())
        city_set.update(self.data["DestCityName"].unique().tolist())
        return city_set


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Search flights by origin, destination, and departure date.")
    parser.add_argument("--origin", "-o", help="Origin city name.")
    parser.add_argument("--destination", "-d", help="Destination city name.")
    parser.add_argument("--date", "-t", help="Departure date (YYYY-MM-DD).")
    parser.add_argument(
        "--path",
        default=str(DEFAULT_DATA_PATH),
        help="Path to flights CSV (defaults to bundled dataset).",
    )
    return parser


def main() -> None:
    args = _build_arg_parser().parse_args()
    flights = Flights(path=args.path)

    if not (args.origin and args.destination and args.date):
        print("Please provide --origin, --destination, and --date.")
        return

    result = flights.run(args.origin, args.destination, args.date)
    if isinstance(result, str):
        print(result)
    else:
        # Print in a compact, readable format without the pandas index.
        print(result.to_string(index=False))


if __name__ == "__main__":
    main()
