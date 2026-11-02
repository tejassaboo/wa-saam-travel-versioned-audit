"""A scripted agent with no LLM, written from the handbook (src/plugin/data/handbook.md) alone: it imports
nothing of the plugin's rules. It follows the step plan through a ``call(tool, arguments)`` function and
returns the submission it would make, so the tests can run each scenario end to end."""

from datetime import date

LISTED = {"accompany_official", "escalated_costs", "distant_savings_consumed", "conference_venue", "ada_or_safety", "suite_cheaper"}
LADDER = ["tourist", "business", "first"]


def before(first, second):
    return date.fromisoformat(first) < date.fromisoformat(second)


def cabin(voucher, regime):
    air = voucher["air"]
    outside = not (air["origin"]["continental_us"] and air["destination"]["continental_us"])
    over = air["scheduled_one_way_minutes"] > regime["business_over_minutes"]
    approval = air["business_approval_date"]
    advance = approval is not None and before(approval, voucher["departure_date"])
    entitled = "business" if outside and over and advance and air["unused_state_miles"] == 0 else "tourist"
    return min(entitled, air["cabin_flown"], key=LADDER.index)


def lodging(voucher):
    room = voucher["lodging"]
    if room is None:
        return None, 0
    rate, maximum = room["nightly_rate_cents"], room["max_lodging_cents"]
    cap = (maximum + room["mie_cents"]) * 3 // 2
    approval = room["exception_approval_date"]
    approved = approval is not None and before(approval, voucher["departure_date"])
    lowest = room["lowest_advertised_rate_cents"]
    if rate <= maximum:
        return "within_max", rate
    if rate > cap and approved and "conference_venue" in room["claimed_reasons"] and room["attendance_required"] and lowest is not None and lowest > cap:
        return "above_150_conference", min(rate, lowest)
    if approved and LISTED & set(room["claimed_reasons"]):
        return "exception_150", min(rate, cap)
    return "capped_at_max", maximum


def run(scenario, call):
    """(the tool calls made, in order, as (tool, arguments); the submission)."""
    calls = [("get_voucher", {"scenario": scenario})]
    voucher = call(*calls[-1])
    dates = ([voucher["departure_date"]] if voucher["air"] is not None else []) + [drive["date"] for drive in voucher["pov_drives"]]
    dates = list(dict.fromkeys(dates))
    regimes = {}
    if dates:
        calls.append(("get_rules_in_effect", {"dates": dates}))
        regimes = {row["date"]: row for row in call(*calls[-1])["rules"]}
    tenths = sum(drive["miles"] * regimes[drive["date"]]["pov_rate_tenth_cents"] for drive in voucher["pov_drives"])
    basis, per_night = lodging(voucher)
    meals = None
    if not voucher["overnight"]:
        needed = 660 if voucher["traveler"]["traveler_type"] == "employee" else 300
        meals = voucher["travel_status_minutes"] >= needed
    return calls, {
        "reimbursable_cabin": None if voucher["air"] is None else cabin(voucher, regimes[voucher["departure_date"]]),
        "mileage_cents": (tenths + 5) // 10,
        "lodging_basis": basis,
        "lodging_per_night_cents": per_night,
        "meals_eligible_same_day": meals,
    }
