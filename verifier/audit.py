"""The audit-wa-travel-voucher verdict, and the checks of its reference tool compute_wa_voucher.

The verifier computes the correct audit itself (rules.oracle over the bundled fixtures) and checks the
submitted one against it in stages, each a list of constraints with stable ids (the reason codes):

0. answer key: the pinned reference equals the verifier's own oracle (else the plugin is broken);
1. referential integrity: each output field is null or zero exactly when the voucher has no such part;
2. internal consistency: the cabin is not above the one flown, the nightly amount is what the stated basis
   pays for this room, the total is nights x the nightly amount plus the mileage as submitted;
3. policy decision against the oracle: cabin, mileage, lodging basis, lodging amount, total;
4. flags: the same-day meal eligibility.

A stage is checked only when every earlier stage holds. The message names the first failing constraint
and how many more fail. Shape problems (types, Enum values, missing or extra fields) never get here:
NanoAgent's build_output refuses them first.

valid is strict: true only when every constraint holds. score is partial credit in [0, 1]: each output
field the voucher makes live is one share (reimbursable_cabin when a flight is claimed, mileage_cents when
a drive is, lodging_basis and lodging_per_night_cents when lodging is, meals_eligible_same_day on a same-day
trip, total_reimbursable_cents when a drive or lodging is), and the score is the fraction of shares that
equal the oracle exactly. A field the voucher leaves dead (null or 0 is its only consistent value) earns
nothing, so a lazy all-null answer scores by the live fields it got right, usually none. Any stage-1
failure (a value where the voucher has no such part, or a null or 0 where it has one) describes another
voucher, and zeroes the score; so does a broken answer key. score == 1.0 exactly when valid.

lodging-amount-correct and total-correct are backstops: once the stage-2 fits hold, the stated basis pins
the nightly amount and the submitted parts pin the total, so each can fail only together with an earlier
decision (tests check this) and never decides a verdict on its own. They stay so that a basis rule with a
free amount could not slip through unchecked.
"""

from .checks import UNEXPECTED, fixtures, plain, result
from .rules import (
    FLOWN_LADDER,
    LISTED_REASONS,
    MEAL_MINUTES,
    above_150_holds,
    basis_amount,
    business_conditions,
    drive_tenth_cents,
    exception_cap_cents,
    oracle,
)
from .world import is_before, regime_on

TEXT = {
    "reference-matches-oracle": "The pinned answer key equals the verifier's own oracle",
    "cabin-matches-air": "reimbursable_cabin is null exactly when the voucher claims no airfare",
    "mileage-matches-drives": "mileage_cents is 0 exactly when the voucher claims no drive, else positive",
    "lodging-matches-claim": "lodging_basis is null and lodging_per_night_cents 0 exactly when no lodging is claimed",
    "meals-matches-trip": "meals_eligible_same_day is null exactly when the trip is overnight",
    "total-matches-claims": "total_reimbursable_cents is 0 exactly when neither lodging nor a drive is claimed, else positive",
    "cabin-within-flown": "The reimbursed cabin is not above the cabin actually flown",
    "lodging-amount-fits-basis": "The nightly amount is what the stated lodging basis pays for this room",
    "total-fits-parts": "The total is lodging nights x the submitted nightly amount plus the submitted mileage",
    "cabin-correct": "The reimbursed cabin follows C1 and C3-C6",
    "mileage-correct": "The mileage follows C1 and C8",
    "lodging-basis-correct": "The lodging basis follows C7",
    "lodging-amount-correct": "The nightly lodging amount follows C7",
    "total-correct": "The voucher total follows C10",
    "meals-eligibility-correct": "The same-day meal eligibility follows C9",
}
# Stage 0 and 1: a failure here means the answer describes another voucher (or the plugin is broken), so the score is 0.
ZEROING = frozenset(
    ("reference-matches-oracle", "cabin-matches-air", "mileage-matches-drives", "lodging-matches-claim", "meals-matches-trip", "total-matches-claims")
)
# The output fields the score shares out, and the voucher part that makes each one live.
SHARES = (
    ("reimbursable_cabin", "air"),
    ("mileage_cents", "drives"),
    ("lodging_basis", "lodging"),
    ("lodging_per_night_cents", "lodging"),
    ("meals_eligible_same_day", "same-day"),
    ("total_reimbursable_cents", "total"),
)


def verify_input(value):
    return result(True, "input is valid")  # a scenario Enum member is all the input there is


def verify_output(input_value, output_value, workspace):
    try:
        world, scenario = fixtures(plain(input_value)["scenario"])
        key = oracle(world, scenario)
    except UNEXPECTED as error:
        return result(False, f"verifier-error: {error!r}")
    if plain(output_value) != key:
        return result(False, "compute_wa_voucher differs from the verifier's oracle", expected=key)
    return result(True, "the answer key matches the verifier's oracle")


def verify_task(arguments, output, reference, workspace):
    try:
        world, scenario = fixtures(plain(arguments)["scenario"])
        key = oracle(world, scenario)
        pinned = None if reference is None else plain(reference)
        return judge(world, scenario, key, pinned, plain(output))
    except UNEXPECTED as error:
        return result(False, f"verifier-error: {error!r}")


def judge(world, scenario, key, pinned, given):
    stages = [
        [("reference-matches-oracle", lambda: reference_problem(key, pinned))],
        [
            ("cabin-matches-air", lambda: cabin_part_problem(scenario, given)),
            ("mileage-matches-drives", lambda: mileage_part_problem(scenario, given)),
            ("lodging-matches-claim", lambda: lodging_part_problem(scenario, given)),
            ("meals-matches-trip", lambda: meals_part_problem(scenario, given)),
            ("total-matches-claims", lambda: total_part_problem(scenario, given)),
        ],
        [
            ("cabin-within-flown", lambda: flown_problem(scenario, given)),
            ("lodging-amount-fits-basis", lambda: basis_problem(scenario, given)),
            ("total-fits-parts", lambda: total_fits_problem(scenario, given)),
        ],
        [
            ("cabin-correct", lambda: cabin_problem(world, scenario, key, given)),
            ("mileage-correct", lambda: mileage_problem(world, scenario, key, given)),
            ("lodging-basis-correct", lambda: lodging_basis_problem(scenario, key, given)),
            ("lodging-amount-correct", lambda: lodging_amount_problem(scenario, key, given)),
            ("total-correct", lambda: total_problem(scenario, key, given)),
        ],
        [("meals-eligibility-correct", lambda: meals_problem(world, scenario, key, given))],
    ]
    constraints, blocked = [], None
    for stage in stages:
        for identifier, check in stage:
            if blocked is not None:
                constraints.append(entry(identifier, None, None, None, f"not checked: {blocked} failed"))
                continue
            problem = check()
            if problem is None:
                constraints.append(entry(identifier, True, None, None, ""))
            else:
                constraints.append(entry(identifier, False, *problem))
        failed = [item for item in constraints if item["ok"] is False]
        if failed and blocked is None:
            blocked = failed[0]["id"]
    failed = [item for item in constraints if item["ok"] is False]
    score, shares = partial_score(scenario, key, given, constraints)
    if not failed:
        return result(True, f"the audit is correct: {summary(given)}", score=score, constraints=constraints, expected=key, shares=shares)
    more = f" (+{len(failed) - 1} more)" if len(failed) > 1 else ""
    return result(
        False, f"{failed[0]['id']}: {failed[0]['message']}{more}", score=score, constraints=constraints, expected=key, shares=shares
    )


def live_parts(scenario):
    """Which voucher parts this scenario has, so which output fields are live (see SHARES)."""
    has_drives, has_lodging = bool(scenario["pov_drives"]), scenario["lodging"] is not None
    return {
        "air": scenario["air"] is not None,
        "drives": has_drives,
        "lodging": has_lodging,
        "same-day": not scenario["overnight"],
        "total": has_drives or has_lodging,
    }


def partial_score(scenario, key, given, constraints):
    """(score, shares): the fraction of live output fields that equal the oracle, 0.0 after a stage-0 or
    stage-1 failure. shares lists each live field with whether it was right, for the verdict's details."""
    live = live_parts(scenario)
    shares = [{"field": field, "ok": given[field] == key[field]} for field, part in SHARES if live[part]]
    if not shares or any(item["ok"] is False and item["id"] in ZEROING for item in constraints):
        return 0.0, shares
    return sum(share["ok"] for share in shares) / len(shares), shares


def entry(identifier, ok, expected, actual, message):
    return {"id": identifier, "constraint": TEXT[identifier], "ok": ok, "expected": expected, "actual": actual, "message": message}


def summary(audit):
    lodging = (
        "no lodging"
        if audit["lodging_basis"] is None
        else f"lodging {audit['lodging_basis']} at {audit['lodging_per_night_cents']} cents a night"
    )
    meals = "overnight" if audit["meals_eligible_same_day"] is None else f"same-day meals {audit['meals_eligible_same_day']}"
    cabin = "no airfare" if audit["reimbursable_cabin"] is None else f"cabin {audit['reimbursable_cabin']}"
    return f"{cabin}, mileage {audit['mileage_cents']} cents, {lodging}, {meals}, total {audit['total_reimbursable_cents']} cents"


def reference_problem(key, pinned):
    if pinned is not None and pinned != key:
        return key, pinned, "the pinned answer key differs from the verifier's oracle, so the plugin itself is broken"
    return None


def cabin_part_problem(scenario, given):
    has_air, cabin = scenario["air"] is not None, given["reimbursable_cabin"]
    if has_air and cabin is None:
        return None, None, "the voucher claims a flight, so reimbursable_cabin must name a cabin"
    if not has_air and cabin is not None:
        return None, cabin, "the voucher claims no airfare, so reimbursable_cabin must be null"
    return None


def mileage_part_problem(scenario, given):
    drives, cents = scenario["pov_drives"], given["mileage_cents"]
    if not drives and cents != 0:
        return 0, cents, f"the voucher claims no drive, so mileage_cents must be 0, not {cents}"
    if drives and cents <= 0:
        return None, cents, f"the voucher claims {len(drives)} drive(s), so mileage_cents must be positive, not {cents}"
    return None


def lodging_part_problem(scenario, given):
    has_lodging, basis, cents = scenario["lodging"] is not None, given["lodging_basis"], given["lodging_per_night_cents"]
    if has_lodging and basis is None:
        return None, None, "the voucher claims lodging, so lodging_basis must name a basis"
    if not has_lodging and (basis is not None or cents != 0):
        return [None, 0], [basis, cents], "the voucher claims no lodging, so lodging_basis is null and lodging_per_night_cents 0"
    return None


def meals_part_problem(scenario, given):
    meals = given["meals_eligible_same_day"]
    if scenario["overnight"] and meals is not None:
        return None, meals, "the trip is overnight, so meals_eligible_same_day must be null (C9)"
    if not scenario["overnight"] and meals is None:
        return None, None, "the trip is same-day, so meals_eligible_same_day must be true or false (C9)"
    return None


def total_part_problem(scenario, given):
    total, nights = given["total_reimbursable_cents"], 0 if scenario["lodging"] is None else scenario["lodging"]["nights"]
    claimed = f"{len(scenario['pov_drives'])} drive(s) and {nights} night(s)"
    if not live_parts(scenario)["total"] and total != 0:
        return 0, total, f"the voucher claims neither lodging nor a drive, so total_reimbursable_cents must be 0, not {total}"
    if live_parts(scenario)["total"] and total <= 0:
        return None, total, f"the voucher claims {claimed}, so total_reimbursable_cents must be positive, not {total}"
    return None


def total_fits_problem(scenario, given):
    nights = 0 if scenario["lodging"] is None else scenario["lodging"]["nights"]
    fits, total = nights * given["lodging_per_night_cents"] + given["mileage_cents"], given["total_reimbursable_cents"]
    if fits != total:
        return fits, total, (
            f"{nights} night(s) x {given['lodging_per_night_cents']} cents + mileage {given['mileage_cents']} cents = {fits}, "
            f"not the {total} submitted (C10)"
        )
    return None


def flown_problem(scenario, given):
    cabin = given["reimbursable_cabin"]
    if cabin is None:
        return None
    flown = scenario["air"]["cabin_flown"]
    if FLOWN_LADDER.index(cabin) > FLOWN_LADDER.index(flown):
        return flown, cabin, f"reimburses {cabin} but the traveler flew {flown}"
    return None


def basis_problem(scenario, given):
    basis, lodging = given["lodging_basis"], scenario["lodging"]
    if basis is None:
        return None
    pays, cents = basis_amount(basis, lodging), given["lodging_per_night_cents"]
    if pays is None:
        return None, basis, f"basis {basis} cannot apply to a {lodging['nightly_rate_cents']}-cent room ({room_facts(lodging)})"
    if pays != cents:
        return pays, cents, f"basis {basis} pays {pays} cents a night for this room, not {cents} ({room_facts(lodging)})"
    return None


def room_facts(lodging):
    return (
        f"rate {lodging['nightly_rate_cents']}, maximum {lodging['max_lodging_cents']}, "
        f"150% cap {exception_cap_cents(lodging)} = 150% x ({lodging['max_lodging_cents']} + {lodging['mie_cents']})"
    )


def cabin_problem(world, scenario, key, given):
    if given["reimbursable_cabin"] == key["reimbursable_cabin"]:
        return None
    conditions = business_conditions(world, scenario)
    failing = [words for holds, words in conditions.values() if not holds]
    flown = scenario["air"]["cabin_flown"]
    if failing:
        why = "tourist, because " + "; ".join(failing)
    elif flown == "tourist":
        why = "tourist, because tourist was flown"
    else:
        why = "business, because " + "; ".join(words for _, words in conditions.values())
    return key["reimbursable_cabin"], given["reimbursable_cabin"], f"{given['reimbursable_cabin']} instead of {why}"


def mileage_problem(world, scenario, key, given):
    if given["mileage_cents"] == key["mileage_cents"]:
        return None
    parts = []
    for drive in scenario["pov_drives"]:
        regime = regime_on(world, drive["date"])
        parts.append(
            f"{drive['miles']} mi on {drive['date']} x {regime['pov_rate_tenth_cents']} tenth-cents ({regime['regime_id']}) "
            f"= {drive_tenth_cents(world, drive)}"
        )
    return key["mileage_cents"], given["mileage_cents"], (
        f"{given['mileage_cents']} cents instead of {key['mileage_cents']}: {'; '.join(parts)} tenth-cents, "
        "summed and rounded half up to cents"
    )


def lodging_reasoning(scenario):
    lodging, departure = scenario["lodging"], scenario["departure_date"]
    approval = lodging["exception_approval_date"]
    listed = sorted(reason for reason in lodging["claimed_reasons"] if reason in LISTED_REASONS)
    approved = (
        "no exception approval"
        if approval is None
        else f"exception approved {approval}, {'before' if is_before(approval, departure) else 'not before'} departure {departure}"
    )
    lowest = lodging["lowest_advertised_rate_cents"]
    return (
        f"{room_facts(lodging)}; {approved}; listed reasons claimed: {', '.join(listed) or 'none'}; "
        f"attendance required {lodging['attendance_required']}; lowest advertised "
        f"{'undocumented' if lowest is None else lowest}; 10.30.20.b holds {above_150_holds(lodging, departure)}"
    )


def lodging_basis_problem(scenario, key, given):
    if given["lodging_basis"] == key["lodging_basis"]:
        return None
    return key["lodging_basis"], given["lodging_basis"], (
        f"{given['lodging_basis']} instead of {key['lodging_basis']}: {lodging_reasoning(scenario)}"
    )


def lodging_amount_problem(scenario, key, given):
    if given["lodging_per_night_cents"] == key["lodging_per_night_cents"]:
        return None
    return key["lodging_per_night_cents"], given["lodging_per_night_cents"], (
        f"{given['lodging_per_night_cents']} cents a night instead of {key['lodging_per_night_cents']} "
        f"under {key['lodging_basis']}: {lodging_reasoning(scenario)}"
    )


def total_problem(scenario, key, given):
    if given["total_reimbursable_cents"] == key["total_reimbursable_cents"]:
        return None
    nights = 0 if scenario["lodging"] is None else scenario["lodging"]["nights"]
    return key["total_reimbursable_cents"], given["total_reimbursable_cents"], (
        f"{given['total_reimbursable_cents']} cents instead of {key['total_reimbursable_cents']}: {nights} night(s) x "
        f"{key['lodging_per_night_cents']} + mileage {key['mileage_cents']} (C10)"
    )


def meals_problem(world, scenario, key, given):
    if given["meals_eligible_same_day"] == key["meals_eligible_same_day"]:
        return None
    kind = world["travelers"][scenario["traveler_id"]]["traveler_type"]
    minutes, needed = scenario["travel_status_minutes"], MEAL_MINUTES[kind]
    return key["meals_eligible_same_day"], given["meals_eligible_same_day"], (
        f"{minutes} min in travel status is {'' if minutes >= needed else 'not '}at least {needed} for "
        f"{'an' if kind == 'employee' else 'a'} {kind}"
    )
