"""The oracle's rules at every threshold, exactly at the limit and one unit past it: the business-class
threshold in both regimes, every mileage-regime boundary (the day before and the day of each change), the
150% lodging cap, the meal-hour rules, plus the brief's section 11 cross-policy row for WA SAAM."""

import pytest

from plugin.fixtures import world
from plugin.rules import (
    exception_cap_cents,
    lodging_decision,
    meals_eligible,
    mileage_cents,
    oracle,
    reimbursable_cabin,
    round_half_up_tenths,
)
from plugin.world import day_number, days_between, is_before, regime_on


def trip(departure="2025-03-03", **changes):
    """A synthetic voucher: an approved, miles-exhausted business SEA-NRT flight of 600 scheduled minutes."""
    air = {
        "origin": "SEA",
        "destination": "NRT",
        "segments": [],
        "scheduled_one_way_minutes": 600,
        "cabin_flown": "business",
        "booking_date": "2024-11-01",
        "business_approval_date": "2024-11-02",
        "unused_state_miles": 0,
    }
    base = {
        "scenario": "synthetic",
        "request_text": "",
        "traveler_id": "W201",
        "departure_date": departure,
        "return_date": departure,
        "overnight": True,
        "travel_status_minutes": None,
        "air": air,
        "pov_drives": [],
        "lodging": None,
    }
    return {**base, **changes}


def room(rate, approval="2026-09-01", reasons=("conference_venue",), attend=False, lowest=None, maximum=23200, mie=9200):
    return trip(
        "2026-10-18",
        air=None,
        lodging={
            "location": "Chicago",
            "hotel": "Test",
            "nights": 1,
            "nightly_rate_cents": rate,
            "max_lodging_cents": maximum,
            "mie_cents": mie,
            "exception_approval_date": approval,
            "claimed_reasons": list(reasons),
            "attendance_required": attend,
            "lowest_advertised_rate_cents": lowest,
        },
    )


def flight(departure, **air):
    facts = trip(departure)
    facts["air"] = {**facts["air"], **air}
    return facts


@pytest.mark.parametrize(
    ("departure", "minutes", "cabin"),
    [
        ("2025-06-01", 480, "tourist"),  # exactly 8 h is not in excess of 8 h
        ("2025-06-01", 481, "business"),
        ("2024-06-01", 840, "tourist"),  # exactly 14 h is not in excess of 14 h
        ("2024-06-01", 841, "business"),
        ("2024-06-01", 600, "tourist"),
        ("2024-12-31", 600, "tourist"),  # the day before 25A-01
        ("2025-01-01", 600, "business"),  # the day of 25A-01
        ("2026-07-01", 481, "business"),  # later regimes keep 480
    ],
)
def test_business_threshold_by_departure_regime(departure, minutes, cabin) -> None:
    facts = flight(departure, scheduled_one_way_minutes=minutes, business_approval_date="2024-01-01")
    assert reimbursable_cabin(world(), facts) == cabin


@pytest.mark.parametrize(
    ("approval", "cabin"),
    [("2025-03-02", "business"), ("2025-03-03", "tourist"), ("2025-03-04", "tourist"), (None, "tourist")],
)
def test_approval_must_be_dated_before_the_departure_day(approval, cabin) -> None:
    assert reimbursable_cabin(world(), flight("2025-03-03", business_approval_date=approval)) == cabin


@pytest.mark.parametrize(("miles", "cabin"), [(0, "business"), (1, "tourist"), (40000, "tourist")])
def test_every_state_mile_must_be_used_first(miles, cabin) -> None:
    assert reimbursable_cabin(world(), flight("2025-03-03", unused_state_miles=miles)) == cabin


@pytest.mark.parametrize(
    ("origin", "destination", "cabin"),
    [("SEA", "NRT", "business"), ("NRT", "SEA", "business"), ("HNL", "SEA", "business"), ("SEA", "BOS", "tourist")],
)
def test_one_end_outside_the_continental_us(origin, destination, cabin) -> None:
    assert reimbursable_cabin(world(), flight("2025-03-03", origin=origin, destination=destination)) == cabin


@pytest.mark.parametrize(
    ("flown", "minutes", "cabin"),
    [("tourist", 600, "tourist"), ("first", 600, "business"), ("first", 300, "tourist"), ("business", 300, "tourist")],
)
def test_the_reimbursed_cabin_is_never_above_the_one_flown_or_the_entitlement(flown, minutes, cabin) -> None:
    facts = flight("2025-03-03", cabin_flown=flown, scheduled_one_way_minutes=minutes)
    assert reimbursable_cabin(world(), facts) == cabin


def test_no_air_means_no_cabin() -> None:
    assert reimbursable_cabin(world(), trip(air=None)) is None


@pytest.mark.parametrize(
    ("date", "rate"),
    [
        ("2024-01-01", 670),
        ("2024-12-31", 670),
        ("2025-01-01", 700),
        ("2025-12-31", 700),
        ("2026-01-01", 725),
        ("2026-06-30", 725),
        ("2026-07-01", 760),
        ("2026-11-02", 760),
        ("2024-02-29", 670),
    ],
)
def test_every_mileage_regime_boundary(date, rate) -> None:
    assert regime_on(world(), date)["pov_rate_tenth_cents"] == rate
    drive = {"date": date, "from_place": "a", "to_place": "b", "miles": 100}
    assert mileage_cents(world(), trip(date, air=None, pov_drives=[drive])) == rate * 10


def test_the_regime_table_starts_on_2024_01_01() -> None:
    with pytest.raises(ValueError, match="before 2024-01-01"):
        regime_on(world(), "2023-12-31")


def test_mileage_rounds_half_up_once_after_summing() -> None:
    def drives(*pairs):
        return trip("2026-03-02", air=None, pov_drives=[{"date": d, "from_place": "a", "to_place": "b", "miles": m} for d, m in pairs])

    assert mileage_cents(world(), drives(("2026-03-02", 121))) == 8773  # 121 x 72.5 = 8772.5 cents, rounds up
    assert mileage_cents(world(), drives(("2026-03-02", 1), ("2026-03-03", 1))) == 145  # 72.5 + 72.5, not 73 + 73
    assert mileage_cents(world(), drives(("2025-12-31", 1), ("2026-01-01", 1))) == 143  # 70 + 72.5 = 142.5 -> 143
    assert round_half_up_tenths(4) == 0 and round_half_up_tenths(5) == 1 and round_half_up_tenths(14) == 1
    assert mileage_cents(world(), trip(air=None)) == 0


CAP = 48600  # 150% x (23200 + 9200)


@pytest.mark.parametrize(
    ("facts", "decision"),
    [
        (room(23200, approval=None, reasons=()), ("within_max", 23200)),  # exactly the maximum
        (room(23201, approval=None, reasons=()), ("capped_at_max", 23200)),  # one cent over, no exception
        (room(CAP), ("exception_150", CAP)),  # exactly 150%, approved listed exception
        (room(CAP + 1), ("exception_150", CAP)),  # one cent over 150%: pays the cap
        (room(CAP, reasons=()), ("capped_at_max", 23200)),  # exactly 150% without an exception
        (room(CAP + 1, reasons=("loyalty_program",)), ("capped_at_max", 23200)),  # one cent over, unlisted reason
        (room(CAP, approval=None), ("capped_at_max", 23200)),  # listed reason, never approved
        (room(CAP, approval="2026-10-18"), ("capped_at_max", 23200)),  # approved on the departure day
        (room(CAP, approval="2026-10-17"), ("exception_150", CAP)),  # approved the day before
        (room(30000, reasons=("ada_or_safety", "loyalty_program")), ("exception_150", 30000)),  # one listed is enough
    ],
)
def test_lodging_at_the_maximum_and_the_150_percent_cap(facts, decision) -> None:
    assert lodging_decision(facts) == decision


@pytest.mark.parametrize(
    ("facts", "decision"),
    [
        (room(54000, attend=True, lowest=54000), ("above_150_conference", 54000)),
        (room(54000, attend=True, lowest=50000), ("above_150_conference", 50000)),  # the most economical room
        (room(54000, attend=True, lowest=CAP), ("exception_150", CAP)),  # lowest exactly 150% does not exceed it
        (room(54000, attend=True, lowest=CAP + 1), ("above_150_conference", CAP + 1)),
        (room(54000, attend=True, lowest=None), ("exception_150", CAP)),  # undocumented
        (room(54000, attend=False, lowest=54000), ("exception_150", CAP)),  # attendance not required
        (room(54000, attend=True, lowest=54000, reasons=("escalated_costs",)), ("exception_150", CAP)),  # not the venue
        (room(54000, attend=True, lowest=54000, approval=None), ("capped_at_max", 23200)),
        (room(CAP, attend=True, lowest=54000), ("exception_150", CAP)),  # the room itself is not above 150%
    ],
)
def test_above_150_needs_every_condition(facts, decision) -> None:
    assert lodging_decision(facts) == decision


def test_the_cap_is_lodging_plus_mie_and_rounds_down() -> None:
    assert exception_cap_cents({"max_lodging_cents": 11300, "mie_cents": 6800}) == 27150  # the rate sheet's $271.50
    assert exception_cap_cents({"max_lodging_cents": 11300, "mie_cents": 6801}) == 27151  # 27151.5 rounds down
    assert lodging_decision(trip(air=None)) == (None, 0)


@pytest.mark.parametrize(
    ("traveler", "minutes", "eligible"),
    [("W201", 659, False), ("W201", 660, True), ("W205", 299, False), ("W205", 300, True)],
)
def test_same_day_meal_hours(traveler, minutes, eligible) -> None:
    facts = trip(air=None, traveler_id=traveler, overnight=False, travel_status_minutes=minutes)
    assert meals_eligible(world(), facts) is eligible


def test_board_members_need_five_hours_and_overnight_trips_have_no_same_day_answer() -> None:
    board = {**world(), "travelers": {**world()["travelers"], "B1": {"traveler_id": "B1", "traveler_type": "board_member"}}}
    for minutes, eligible in ((299, False), (300, True)):
        facts = trip(air=None, traveler_id="B1", overnight=False, travel_status_minutes=minutes)
        assert meals_eligible(board, facts) is eligible
    assert meals_eligible(world(), trip(air=None)) is None


@pytest.mark.parametrize("departure", ["2024-06-03", "2025-06-02"])
def test_section_11_cross_policy_row_for_wa_saam(departure) -> None:
    """Leg 1 360 min, layover 90, leg 2 420 min, international: one-way scheduled 870 exceeds both 840 and 480,
    so business in either regime with advance approval and exhausted miles; tourist without approval."""
    facts = flight(departure, scheduled_one_way_minutes=360 + 90 + 420, business_approval_date="2024-01-02")
    assert oracle(world(), facts)["reimbursable_cabin"] == "business"
    assert reimbursable_cabin(world(), flight(departure, scheduled_one_way_minutes=870, business_approval_date=None)) == "tourist"


def test_date_arithmetic() -> None:
    assert days_between("2024-02-28", "2024-03-01") == 2  # leap day
    assert days_between("2025-02-28", "2025-03-01") == 1
    assert is_before("2024-12-31", "2025-01-01") and not is_before("2025-01-01", "2025-01-01")
    for bad in ("2025-02-29", "2025-13-01", "2025-1-01", "20250101", None):
        with pytest.raises(ValueError):
            day_number(bad)
