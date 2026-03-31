"""Realistic data shape tests for prepare/compute splits.

Validates that compute functions handle real-world TP API data shapes
gracefully — including None values, missing fields, empty collections,
and sport-specific variations (swimming, running, cycling).
"""

from datetime import date

import pytest

from tp_mcp.tools.analyze import analyse_workout
from tp_mcp.tools.fitness import compute_fitness_metrics


class TestFitnessRealisticShapes:
    """Tests for compute_fitness_metrics with realistic API data shapes."""

    def test_compute_handles_empty_daily_data(self):
        """Empty raw_data should return an empty data list and no current."""
        result = compute_fitness_metrics(
            raw_data=[],
            query_start=date(2026, 3, 1),
            query_end=date(2026, 3, 31),
            query_days=30,
        )
        assert result["data"] == []
        assert result["current"] is None
        assert result["days"] == 30

    def test_compute_handles_none_tsb(self):
        """TSB=None should be handled gracefully via get() default."""
        raw = [
            {"workoutDay": "2026-03-01T00:00:00", "tssActual": 0, "ctl": 50.0, "atl": 40.0, "tsb": None}
        ]
        result = compute_fitness_metrics(
            raw_data=raw,
            query_start=date(2026, 3, 1),
            query_end=date(2026, 3, 1),
            query_days=0,
        )
        assert result is not None
        # None is coerced to 0 by the get() default, then rounded
        assert result["daily_data"][0]["tsb"] == 0

    def test_compute_handles_none_ctl_atl(self):
        """None CTL/ATL should be handled via get() default to 0."""
        raw = [
            {"workoutDay": "2026-03-01T00:00:00", "tssActual": None, "ctl": None, "atl": None, "tsb": None}
        ]
        result = compute_fitness_metrics(
            raw_data=raw,
            query_start=date(2026, 3, 1),
            query_end=date(2026, 3, 1),
            query_days=0,
        )
        assert result["daily_data"][0]["ctl"] == 0
        assert result["daily_data"][0]["atl"] == 0
        assert result["daily_data"][0]["tsb"] == 0

    def test_compute_handles_missing_keys(self):
        """Entries missing expected keys should use defaults from get()."""
        raw = [
            {"workoutDay": "2026-03-01T00:00:00"}
        ]
        result = compute_fitness_metrics(
            raw_data=raw,
            query_start=date(2026, 3, 1),
            query_end=date(2026, 3, 1),
            query_days=0,
        )
        assert result["daily_data"][0]["tss"] == 0
        assert result["daily_data"][0]["ctl"] == 0
        assert result["daily_data"][0]["atl"] == 0
        assert result["daily_data"][0]["tsb"] == 0

    def test_compute_rounds_correctly(self):
        """Values should be rounded to 1 decimal place."""
        raw = [
            {
                "workoutDay": "2026-03-01T00:00:00",
                "tssActual": 100,
                "ctl": 50.123456,
                "atl": 40.789012,
                "tsb": 9.334444,
            }
        ]
        result = compute_fitness_metrics(
            raw_data=raw,
            query_start=date(2026, 3, 1),
            query_end=date(2026, 3, 1),
            query_days=0,
        )
        daily = result["daily_data"]
        assert daily[0]["ctl"] == 50.1
        assert daily[0]["atl"] == 40.8
        assert daily[0]["tsb"] == 9.3

    def test_compute_date_strips_time_component(self):
        """workoutDay with time component should be stripped to date only."""
        raw = [
            {"workoutDay": "2026-03-15T12:34:56.789Z", "tssActual": 80, "ctl": 45, "atl": 50, "tsb": -5}
        ]
        result = compute_fitness_metrics(
            raw_data=raw,
            query_start=date(2026, 3, 15),
            query_end=date(2026, 3, 15),
            query_days=0,
        )
        assert result["daily_data"][0]["date"] == "2026-03-15"

    def test_compute_multi_day_range(self):
        """Multiple entries should all appear and latest becomes current."""
        raw = [
            {"workoutDay": "2026-03-01T00:00:00", "tssActual": 50, "ctl": 40, "atl": 35, "tsb": 5},
            {"workoutDay": "2026-03-02T00:00:00", "tssActual": 100, "ctl": 42, "atl": 55, "tsb": -13},
            {"workoutDay": "2026-03-03T00:00:00", "tssActual": 0, "ctl": 41, "atl": 45, "tsb": -4},
        ]
        result = compute_fitness_metrics(
            raw_data=raw,
            query_start=date(2026, 3, 1),
            query_end=date(2026, 3, 3),
            query_days=2,
        )
        assert len(result["daily_data"]) == 3
        assert result["current"]["ctl"] == 41.0
        assert result["current"]["tsb"] == -4.0

    def test_compute_fitness_status_exhausted(self):
        """TSB <= -25 should map to exhausted status."""
        raw = [
            {"workoutDay": "2026-03-01T00:00:00", "tssActual": 200, "ctl": 30, "atl": 80, "tsb": -50}
        ]
        result = compute_fitness_metrics(
            raw_data=raw,
            query_start=date(2026, 3, 1),
            query_end=date(2026, 3, 1),
            query_days=0,
        )
        assert result["current"]["fitness_status"] == "Exhausted (overreaching risk)"

    def test_compute_fitness_status_very_fresh(self):
        """TSB > 25 should map to very fresh / detraining risk."""
        raw = [
            {"workoutDay": "2026-03-01T00:00:00", "tssActual": 0, "ctl": 60, "atl": 20, "tsb": 40}
        ]
        result = compute_fitness_metrics(
            raw_data=raw,
            query_start=date(2026, 3, 1),
            query_end=date(2026, 3, 1),
            query_days=0,
        )
        assert result["current"]["fitness_status"] == "Very Fresh (detraining risk)"


class TestWorkoutRealisticShapes:
    """Tests for analyse_workout with realistic API data shapes."""

    def _make_analysis_data(self, **overrides) -> dict:
        """Build a minimal valid analysis payload with optional overrides."""
        base = {
            "workoutId": 12345,
            "startTimestamp": "2026-03-15T06:00:00",
            "stopTimestamp": "2026-03-15T07:00:00",
            "totals": [{"name": "Duration", "value": 3600, "unit": "s"}],
            "dataElements": [],
            "data": [],
            "lapData": [],
            "lapColumns": [],
        }
        base.update(overrides)
        return base

    def test_analyse_minimal_workout(self):
        """A workout with only required fields should parse cleanly."""
        raw = self._make_analysis_data()
        result = analyse_workout(raw, workout_id=12345)
        assert result["workoutId"] == 12345
        assert "Duration" in result["totals"]
        assert result["time_series_points"] == 0

    def test_analyse_cycling_workout_with_power(self):
        """Cycling workout with power channel should include power stats."""
        raw = self._make_analysis_data(
            dataElements=[
                {
                    "identifier": "power",
                    "name": "Power",
                    "unit": "W",
                    "min": 80.0,
                    "max": 450.0,
                    "average": 220.0,
                    "zones": [
                        {"name": "Z1", "min": 0, "max": 150, "seconds": 600},
                        {"name": "Z2", "min": 150, "max": 220, "seconds": 1200},
                    ],
                }
            ],
            data=[{"power": 200, "hr": 145}, {"power": 250, "hr": 155}],
        )
        result = analyse_workout(raw, workout_id=12345)
        assert len(result["dataChannels"]) == 1
        assert result["dataChannels"][0]["name"] == "Power"
        assert result["dataChannels"][0]["unit"] == "W"
        assert result["dataChannels"][0]["average"] == 220.0
        assert len(result["dataChannels"][0]["zones"]) == 2
        assert result["time_series_points"] == 2

    def test_analyse_swimming_workout_no_power(self):
        """Swimming workout without power data should parse cleanly."""
        raw = self._make_analysis_data(
            totals=[
                {"name": "Duration", "value": 3600, "unit": "s"},
                {"name": "Distance", "value": 2500, "unit": "m"},
            ],
            dataElements=[
                {
                    "identifier": "heartrate",
                    "name": "Heart Rate",
                    "unit": "bpm",
                    "min": 95.0,
                    "max": 172.0,
                    "average": 142.0,
                }
            ],
        )
        result = analyse_workout(raw, workout_id=12345)
        assert "Duration" in result["totals"]
        assert "Distance" in result["totals"]
        assert result["dataChannels"][0]["name"] == "Heart Rate"

    def test_analyse_workout_with_no_data_elements(self):
        """Workout with no data channels (e.g. manual entry) should work."""
        raw = self._make_analysis_data(
            dataElements=[],
            data=[],
        )
        result = analyse_workout(raw, workout_id=12345)
        assert result["dataChannels"] == []
        assert result["time_series_points"] == 0

    def test_analyse_workout_with_lap_data(self):
        """Workout with lap splits should include lap data."""
        raw = self._make_analysis_data(
            lapData=[
                {"lap": 1, "duration": 600, "distance": 1600},
                {"lap": 2, "duration": 620, "distance": 1600},
            ],
            lapColumns=[
                {"name": "Lap", "unit": None},
                {"name": "Duration", "unit": "s"},
                {"name": "Distance", "unit": "m"},
            ],
        )
        result = analyse_workout(raw, workout_id=12345)
        assert len(result["lapData"]) == 2
        assert len(result["lapColumns"]) == 3

    def test_analyse_workout_with_none_channel_fields(self):
        """Channel fields set to None should be excluded from output."""
        raw = self._make_analysis_data(
            dataElements=[
                {
                    "identifier": "speed",
                    "name": "Speed",
                    "unit": "m/s",
                    "min": None,
                    "max": None,
                    "average": 3.5,
                    "zones": None,
                }
            ],
        )
        result = analyse_workout(raw, workout_id=12345)
        channel = result["dataChannels"][0]
        assert channel["name"] == "Speed"
        assert channel["average"] == 3.5
        # None fields should be filtered out by the dict comprehension
        assert "min" not in channel
        assert "max" not in channel
        assert "zones" not in channel

    def test_analyse_workout_extra_fields_ignored(self):
        """Extra fields in raw data should be ignored (model has extra='ignore')."""
        raw = self._make_analysis_data(
            extraField1="ignored",
            someOtherThing=42,
        )
        result = analyse_workout(raw, workout_id=12345)
        assert result["workoutId"] == 12345
        # No error raised, extra fields silently ignored

    def test_analyse_preserves_data_file_path(self):
        """The result should contain a data_file path pointing to saved JSON."""
        raw = self._make_analysis_data()
        result = analyse_workout(raw, workout_id=99999)
        assert "data_file" in result
        assert "99999" in result["data_file"]

    def test_analyse_multiple_totals(self):
        """Multiple totals should all appear keyed by name."""
        raw = self._make_analysis_data(
            totals=[
                {"name": "Duration", "value": 3600, "unit": "s"},
                {"name": "Calories", "value": 850, "unit": "kcal"},
                {"name": "TSS", "value": 95.5, "unit": None},
                {"name": "IF", "value": 0.82, "unit": None},
            ],
        )
        result = analyse_workout(raw, workout_id=12345)
        assert len(result["totals"]) == 4
        assert result["totals"]["Duration"]["value"] == 3600
        assert result["totals"]["Calories"]["value"] == 850
        assert result["totals"]["TSS"]["value"] == 95.5
        assert result["totals"]["IF"]["value"] == 0.82
