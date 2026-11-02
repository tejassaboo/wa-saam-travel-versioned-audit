"""Shared core of this plugin: the fixture schema and loader, date arithmetic, and the regime lookup the
tools and the verifier both run.

Pure standard library (json, re, pathlib) and no clock, so the sandboxed verifier can run it too. It is
vendored byte-identical into src/plugin/ and verifier/ (a test checks the two copies). Dates are compared
as day numbers computed here: nothing uses datetime.
"""

import itertools
import json
import re
from pathlib import Path

DATE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
MONTH_DAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
FIRST_COVERED_DATE = "2024-01-01"  # the regime table starts here; earlier dates are out of scope

# Each fixture table: its file's records' keys, the first one the record's id.
SCHEMA = {
    "airports": ("code", "city", "continental_us"),
    "travelers": ("traveler_id", "name", "agency", "traveler_type"),
    "regimes": (
        "regime_id",
        "effective_from",
        "effective_to",
        "business_over_minutes",
        "pov_rate_tenth_cents",
        "source",
    ),
}
SCENARIO_KEYS = (
    "scenario",
    "request_text",
    "traveler_id",
    "departure_date",
    "return_date",
    "overnight",
    "travel_status_minutes",
    "air",
    "pov_drives",
    "lodging",
)
AIR_KEYS = (
    "origin",
    "destination",
    "segments",
    "scheduled_one_way_minutes",
    "cabin_flown",
    "booking_date",
    "business_approval_date",
    "unused_state_miles",
)
SEGMENT_KEYS = ("flight", "origin", "destination", "depart_local", "arrive_local", "in_air_minutes")
DRIVE_KEYS = ("date", "from_place", "to_place", "miles")
LODGING_KEYS = (
    "location",
    "hotel",
    "nights",
    "nightly_rate_cents",
    "max_lodging_cents",
    "mie_cents",
    "exception_approval_date",
    "claimed_reasons",
    "attendance_required",
    "lowest_advertised_rate_cents",
)


def day_number(text):
    """Days from 1970-01-01 to the date YYYY-MM-DD; ValueError for anything but a real calendar date."""
    match = DATE.fullmatch(text) if isinstance(text, str) else None
    if match is None:
        raise ValueError(f"{text!r} is not a YYYY-MM-DD date")
    year, month, day = (int(part) for part in match.groups())
    leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
    if not 1 <= month <= 12 or not 1 <= day <= MONTH_DAYS[month - 1] + (month == 2 and leap):
        raise ValueError(f"{text!r} is not a calendar date")
    shifted = year - (month <= 2)  # Howard Hinnant's days_from_civil
    era = shifted // 400
    year_of_era = shifted - era * 400
    day_of_year = (153 * ((month + 9) % 12) + 2) // 5 + day - 1
    return era * 146097 + year_of_era * 365 + year_of_era // 4 - year_of_era // 100 + day_of_year - 719468


def days_between(start, end):
    """Calendar days from date ``start`` to date ``end`` (negative when end is earlier)."""
    return day_number(end) - day_number(start)


def is_before(first, second):
    """Date ``first`` is a strictly earlier calendar day than date ``second``."""
    return day_number(first) < day_number(second)


def load_world(data_dir):
    """Every fixture table under ``data_dir``: airports and travelers by id, regimes in date order."""
    world = {}
    for table, keys in SCHEMA.items():
        records = json.loads((Path(data_dir) / f"{table}.json").read_text(encoding="utf-8"))
        world[table] = {record[keys[0]]: record for record in records}
    return world


def load_scenario(data_dir, scenario_id):
    """One scenario's voucher facts (never its expected answer), from scenarios/<id>.json under ``data_dir``."""
    return json.loads((Path(data_dir) / "scenarios" / f"{scenario_id}.json").read_text(encoding="utf-8"))


def regime_on(world, date):
    """The regime record in effect on ``date``: effective_from <= date <= effective_to (null: open-ended)."""
    if is_before(date, FIRST_COVERED_DATE):
        raise ValueError(f"{date} is before {FIRST_COVERED_DATE}, where the regime table starts")
    day = day_number(date)
    found = [
        regime
        for regime in world["regimes"].values()
        if day_number(regime["effective_from"]) <= day
        and (regime["effective_to"] is None or day <= day_number(regime["effective_to"]))
    ]
    if len(found) != 1:
        raise ValueError(f"{date} falls in {len(found)} regimes, not exactly one")
    return found[0]


def regime_view(world, date):
    """A regime as get_rules_in_effect shows it, for one date."""
    return {"date": date, **regime_on(world, date)}


def schema_problems(world, scenarios):
    """Every way the fixtures break the schema, point at a record that does not exist, leave a gap or an
    overlap in the regime table, or state a voucher fact inconsistently."""
    problems = []
    for table, keys in SCHEMA.items():
        for record_id, record in world[table].items():
            if tuple(record) != keys:
                problems.append(f"{table} {record_id}: keys {list(record)} are not {list(keys)}")
    regimes = sorted(world["regimes"].values(), key=lambda regime: day_number(regime["effective_from"]))
    if regimes[0]["effective_from"] != FIRST_COVERED_DATE:
        problems.append(f"the regime table does not start on {FIRST_COVERED_DATE}")
    for earlier, later in itertools.pairwise(regimes):
        if earlier["effective_to"] is None or days_between(earlier["effective_to"], later["effective_from"]) != 1:
            problems.append(f"regimes {earlier['regime_id']} and {later['regime_id']} leave a gap or overlap")
    if regimes[-1]["effective_to"] is not None:
        problems.append("the last regime must be open-ended")
    for scenario in scenarios:
        name = scenario.get("scenario")
        if tuple(scenario) != SCENARIO_KEYS:
            problems.append(f"scenario {name}: keys {list(scenario)} are not {list(SCENARIO_KEYS)}")
            continue
        if scenario["traveler_id"] not in world["travelers"]:
            problems.append(f"scenario {name}: unknown traveler {scenario['traveler_id']}")
        start, end = scenario["departure_date"], scenario["return_date"]
        if days_between(start, end) < 0:
            problems.append(f"scenario {name}: returns before it departs")
        if scenario["overnight"] != (start != end):
            problems.append(f"scenario {name}: overnight must mean return_date after departure_date")
        if (scenario["travel_status_minutes"] is None) != scenario["overnight"]:
            problems.append(f"scenario {name}: travel_status_minutes is null exactly when the trip is overnight")
        for drive in scenario["pov_drives"]:
            if tuple(drive) != DRIVE_KEYS or drive["miles"] < 1:
                problems.append(f"scenario {name}: drive {drive} breaks the schema")
            elif not 0 <= days_between(start, drive["date"]) <= days_between(start, end):
                problems.append(f"scenario {name}: drive on {drive['date']} is outside the trip")
        if [drive["date"] for drive in scenario["pov_drives"]] != sorted(drive["date"] for drive in scenario["pov_drives"]):
            problems.append(f"scenario {name}: drives are not in date order")
        problems.extend(air_problems(world, name, scenario))
        lodging = scenario["lodging"]
        if lodging is not None and (tuple(lodging) != LODGING_KEYS or lodging["nights"] < 1 or not scenario["overnight"]):
            problems.append(f"scenario {name}: lodging breaks the schema or the trip is not overnight")
    return problems


def air_problems(world, name, scenario):
    air = scenario["air"]
    if air is None:
        return []
    if tuple(air) != AIR_KEYS:
        return [f"scenario {name}: air keys {list(air)} are not {list(AIR_KEYS)}"]
    problems = []
    segments = air["segments"]
    if not segments or any(tuple(segment) != SEGMENT_KEYS for segment in segments):
        problems.append(f"scenario {name}: segments break the schema")
        return problems
    codes = [air["origin"], *[segment["destination"] for segment in segments]]
    if [segment["origin"] for segment in segments] != codes[:-1] or codes[-1] != air["destination"]:
        problems.append(f"scenario {name}: segments do not chain from origin to destination")
    for code in codes:
        if code not in world["airports"]:
            problems.append(f"scenario {name}: unknown airport {code}")
    if segments[0]["depart_local"][:10] != scenario["departure_date"]:
        problems.append(f"scenario {name}: the flight does not leave on the departure date")
    if air["scheduled_one_way_minutes"] < sum(segment["in_air_minutes"] for segment in segments):
        problems.append(f"scenario {name}: scheduled one-way minutes are less than the in-air minutes")
    if days_between(air["booking_date"], scenario["departure_date"]) < 0:
        problems.append(f"scenario {name}: the ticket was bought after departure")
    return problems
