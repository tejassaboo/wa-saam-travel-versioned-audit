"""Washington State SAAM Chapter 10 as this plugin's toy handbook states it (src/plugin/data/handbook.md):
the oracle that the reference tool and the verifier both run on the bundled fixtures.

Byte-identical in src/plugin/ and verifier/ (a test checks the two copies), so it keeps to the
verifier's pure-stdlib rules. Every function is a pure function of the fixtures and one scenario.
Money is int cents; the mileage rate is int tenths of a cent, so no float is ever used.
"""

from .world import is_before, regime_on

# The six situations of SAAM 10.30.20.a; any other claimed reason does not count.
LISTED_REASONS = (
    "accompany_official",
    "escalated_costs",
    "distant_savings_consumed",
    "conference_venue",
    "ada_or_safety",
    "suite_cheaper",
)
MEAL_MINUTES = {"employee": 660, "volunteer": 300, "board_member": 300}  # "at least" this long (C9)
FLOWN_LADDER = ("tourist", "business", "first")


def voucher(world, scenario):
    """The voucher get_voucher shows: the scenario's facts with its traveler and airports filled in."""
    air = scenario["air"]
    if air is not None:
        air = {
            **air,
            "origin": dict(world["airports"][air["origin"]]),
            "destination": dict(world["airports"][air["destination"]]),
            "segments": [dict(segment) for segment in air["segments"]],
        }
    lodging = scenario["lodging"]
    if lodging is not None:
        lodging = {**lodging, "claimed_reasons": list(lodging["claimed_reasons"])}
    return {
        "scenario": scenario["scenario"],
        "request_text": scenario["request_text"],
        "traveler": dict(world["travelers"][scenario["traveler_id"]]),
        "departure_date": scenario["departure_date"],
        "return_date": scenario["return_date"],
        "overnight": scenario["overnight"],
        "travel_status_minutes": scenario["travel_status_minutes"],
        "air": air,
        "pov_drives": [dict(drive) for drive in scenario["pov_drives"]],
        "lodging": lodging,
    }


def business_conditions(world, scenario):
    """Each condition of business class (C3-C5) as {name: (holds, words)}; None when no airfare is claimed.
    The regime is the one in effect on the trip's departure date (C1)."""
    air = scenario["air"]
    if air is None:
        return None
    departure = scenario["departure_date"]
    regime = regime_on(world, departure)
    origin, destination = (world["airports"][air[key]] for key in ("origin", "destination"))
    outside = not (origin["continental_us"] and destination["continental_us"])
    minutes, over = air["scheduled_one_way_minutes"], regime["business_over_minutes"]
    approval = air["business_approval_date"]
    approved = approval is not None and is_before(approval, departure)
    miles = air["unused_state_miles"]
    return {
        "outside_continental_us": (
            outside,
            f"{origin['code']} and {destination['code']} are both in the continental US"
            if not outside
            else f"{origin['code'] if not origin['continental_us'] else destination['code']} is outside the continental US",
        ),
        "over_threshold": (
            minutes > over,
            (
                f"scheduled one-way {minutes} min is {'' if minutes > over else 'not '}> {over} "
                f"(regime {regime['regime_id']}, in effect on departure {departure})"
            ),
        ),
        "approved_in_advance": (
            approved,
            "business class was never approved"
            if approval is None
            else f"business class approved {approval}, {'before' if approved else 'not before'} departure {departure}",
        ),
        "miles_exhausted": (
            miles == 0,
            "state frequent-flyer miles are exhausted (0 left)" if miles == 0 else f"{miles} state frequent-flyer miles remain unspent",
        ),
    }


def reimbursable_cabin(world, scenario):
    """tourist or business (C6): business only when every condition holds and business or first was flown."""
    conditions = business_conditions(world, scenario)
    if conditions is None:
        return None
    entitled = "business" if all(holds for holds, _ in conditions.values()) else "tourist"
    flown = scenario["air"]["cabin_flown"]
    return flown if FLOWN_LADDER.index(flown) < FLOWN_LADDER.index(entitled) else entitled


def drive_tenth_cents(world, drive):
    """One drive's mileage in tenths of a cent, at the rate in effect on the drive's own date (C1, C8)."""
    return drive["miles"] * regime_on(world, drive["date"])["pov_rate_tenth_cents"]


def round_half_up_tenths(tenths):
    """Tenths of a cent to whole cents, a half cent rounding up (C8)."""
    return (tenths + 5) // 10


def mileage_cents(world, scenario):
    """Every drive's exact amount summed, then rounded half up once to whole cents (C8)."""
    return round_half_up_tenths(sum(drive_tenth_cents(world, drive) for drive in scenario["pov_drives"]))


def exception_cap_cents(lodging):
    """150% of the location's lodging plus M&IE, in cents, rounded down to a whole cent (C7)."""
    return (lodging["max_lodging_cents"] + lodging["mie_cents"]) * 3 // 2


def above_150_holds(lodging, departure_date):
    """Every condition of SAAM 10.30.20.b as the toy handbook states it (C7, step 2)."""
    approval, lowest = lodging["exception_approval_date"], lodging["lowest_advertised_rate_cents"]
    cap = exception_cap_cents(lodging)
    return (
        approval is not None
        and is_before(approval, departure_date)
        and lodging["nightly_rate_cents"] > cap
        and "conference_venue" in lodging["claimed_reasons"]
        and lodging["attendance_required"]
        and lowest is not None
        and lowest > cap
    )


def lodging_decision(scenario):
    """(basis, reimbursable cents per night) under C7; (None, 0) when no lodging is claimed."""
    lodging = scenario["lodging"]
    if lodging is None:
        return None, 0
    rate, maximum = lodging["nightly_rate_cents"], lodging["max_lodging_cents"]
    if rate <= maximum:
        return "within_max", rate
    if above_150_holds(lodging, scenario["departure_date"]):
        return "above_150_conference", min(rate, lodging["lowest_advertised_rate_cents"])
    approval = lodging["exception_approval_date"]
    approved = approval is not None and is_before(approval, scenario["departure_date"])
    if approved and any(reason in LISTED_REASONS for reason in lodging["claimed_reasons"]):
        return "exception_150", min(rate, exception_cap_cents(lodging))
    return "capped_at_max", maximum


def basis_amount(basis, lodging):
    """The nightly amount a stated basis pays for this lodging, or None when the basis cannot apply to it
    at all (an internal-consistency check that does not judge whether the basis is the right one)."""
    rate, maximum, cap = lodging["nightly_rate_cents"], lodging["max_lodging_cents"], exception_cap_cents(lodging)
    lowest = lodging["lowest_advertised_rate_cents"]
    if basis == "within_max":
        return rate if rate <= maximum else None
    if basis == "capped_at_max":
        return maximum if rate > maximum else None
    if basis == "exception_150":
        return min(rate, cap) if rate > maximum else None
    if basis == "above_150_conference":
        return min(rate, lowest) if rate > cap and lowest is not None and lowest > cap else None
    return None


def meals_eligible(world, scenario):
    """The same-day meal rule (C9): at least 660 minutes in travel status for an employee, 300 for a
    volunteer or board member; None for an overnight trip."""
    if scenario["overnight"]:
        return None
    kind = world["travelers"][scenario["traveler_id"]]["traveler_type"]
    return scenario["travel_status_minutes"] >= MEAL_MINUTES[kind]


def oracle(world, scenario):
    """The one correct audit of ``scenario``, as the task output's plain JSON."""
    basis, per_night = lodging_decision(scenario)
    return {
        "reimbursable_cabin": reimbursable_cabin(world, scenario),
        "mileage_cents": mileage_cents(world, scenario),
        "lodging_basis": basis,
        "lodging_per_night_cents": per_night,
        "meals_eligible_same_day": meals_eligible(world, scenario),
    }
