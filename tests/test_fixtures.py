"""The environment: the vendored copies stay identical, the handbook is the task's instructions and pins its
sources, and the fixtures hold their invariants (flight times recomputed here with zoneinfo, which the
plugin itself never uses at evaluation time)."""

import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from helpers import DATA, ROOT, SCENARIOS

from plugin.fixtures import scenario, world
from plugin.world import schema_problems

TIMEZONES = {
    "SEA": "America/Los_Angeles",
    "GEG": "America/Los_Angeles",
    "SFO": "America/Los_Angeles",
    "BOS": "America/New_York",
    "ORD": "America/Chicago",
    "NRT": "Asia/Tokyo",
    "HNL": "Pacific/Honolulu",
}
REGIMES = [  # the verified history (TIER2_DESIGNS.md T9): threshold minutes, POV rate in tenth-cents
    ("R2024", "2024-01-01", "2024-12-31", 840, 670),
    ("R2025", "2025-01-01", "2025-12-31", 480, 700),
    ("R2026A", "2026-01-01", "2026-06-30", 480, 725),
    ("R2026B", "2026-07-01", None, 480, 760),
]


@pytest.mark.parametrize("module", ["rules.py", "world.py"])
def test_the_verifier_runs_the_same_code(module: str) -> None:
    assert (ROOT / "verifier" / module).read_bytes() == (ROOT / "src" / "plugin" / module).read_bytes()


def instructions(manifest_text):
    """The task's instructions: the `|-` block scalar under it, unindented."""
    lines = manifest_text.split("\n")
    start = lines.index("    instructions: |-") + 1
    block = []
    for line in lines[start:]:
        if line and not line.startswith("      "):
            break
        block.append(line[6:])
    return "\n".join(block).rstrip("\n")


def test_the_handbook_is_the_task_instructions() -> None:
    handbook = (DATA / "handbook.md").read_text(encoding="utf-8")
    assert instructions((ROOT / "nanoagent.yaml").read_text(encoding="utf-8")) == handbook.rstrip("\n")
    assert len(handbook.split()) <= 1500


def test_the_handbook_pins_its_sources_and_states_the_toy_rules() -> None:
    handbook = (DATA / "handbook.md").read_text(encoding="utf-8")
    for needle in (
        "https://ofm.wa.gov/wp-content/uploads/2026/02/ch10.pdf",
        "13a95b08a4bdf0d62b4df0ee4f585de28329ddce29dae29a1c61935f04d21648",
        "25A-01",
        "26A-01",
        "26A-05",
        "Rates as of October 1, 2026",
        "2026-11-02",
        "## Clarifications (toy rules)",
        "The departure date selects the rule regime.",
        "does not say whether time on the ground at a connection counts; counting it is our toy rule",
        'The real text says only "in advance"; the calendar-day reading is our toy rule',
        "The most-economical-room duty of rule 7 is modelled only in step 2",
        "The real text states no rounding rule; this is our toy rule",
        "## Rules not in scope",
        'whether a routing is "direct" between the authorized points',
        "first-class or seat-upgrade rules: Chapter 10 has none",
        "## Step plan",
    ):
        assert needle in handbook, needle


def test_the_handbook_regime_table_matches_the_fixture() -> None:
    handbook = (DATA / "handbook.md").read_text(encoding="utf-8")
    for regime_id, start, end, over, rate in REGIMES:
        window = f"{start} to {end}" if end else f"from {start}"
        assert f"| {regime_id} | {window} | {over} | {rate} |" in handbook


def test_the_regime_fixture_is_the_verified_history() -> None:
    rows = [
        (r["regime_id"], r["effective_from"], r["effective_to"], r["business_over_minutes"], r["pov_rate_tenth_cents"])
        for r in world()["regimes"].values()
    ]
    assert rows == REGIMES


def test_the_fixtures_hold_their_schema_and_invariants() -> None:
    assert schema_problems(world(), [scenario(name) for name in SCENARIOS]) == []
    assert sorted(SCENARIOS) == sorted(path.stem for path in (DATA / "scenarios").glob("*.json"))


def test_every_traveler_and_airport_is_used_and_every_file_parses() -> None:
    used_travelers = {scenario(name)["traveler_id"] for name in SCENARIOS}
    assert used_travelers == set(world()["travelers"])
    codes = {
        code
        for name in SCENARIOS
        if scenario(name)["air"]
        for segment in scenario(name)["air"]["segments"]
        for code in (segment["origin"], segment["destination"])
    }
    assert codes <= set(world()["airports"]) and codes <= set(TIMEZONES)
    for path in DATA.rglob("*.json"):
        json.loads(path.read_text(encoding="utf-8"))


def stamp(local, code):
    return datetime.fromisoformat(local).replace(tzinfo=ZoneInfo(TIMEZONES[code]))


@pytest.mark.parametrize("name", [name for name in SCENARIOS if scenario(name)["air"]])
def test_flight_minutes_agree_with_the_local_times(name: str) -> None:
    air = scenario(name)["air"]
    for segment in air["segments"]:
        flown = stamp(segment["arrive_local"], segment["destination"]) - stamp(segment["depart_local"], segment["origin"])
        assert flown.total_seconds() // 60 == segment["in_air_minutes"], segment["flight"]
    first, last = air["segments"][0], air["segments"][-1]
    elapsed = stamp(last["arrive_local"], last["destination"]) - stamp(first["depart_local"], first["origin"])
    assert elapsed.total_seconds() // 60 == air["scheduled_one_way_minutes"]


def test_no_expected_answer_leaks_into_the_scenarios() -> None:
    for name in SCENARIOS:
        text = (DATA / "scenarios" / f"{name}.json").read_text(encoding="utf-8")
        for word in ("expected", "reimbursable_cabin", "lodging_basis", "mileage_cents", "within_max", "exception_150", "capped_at_max"):
            assert word not in text, (name, word)
