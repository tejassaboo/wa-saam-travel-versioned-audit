"""The verifier against hand-written submissions (no agent): the brief's section 7 matrix. Correct,
incorrect, missing, consistency and verifier-caught malformed cases run through verify_task; shape
problems are refused by build_output before any verifier runs, exactly as in NanoAgent."""

import json

import pytest
from helpers import SCENARIOS, TASK, arguments, case, reference, verdict
from slimconfig import build_output

import verifier
from contract import LodgingBasis, RulesInput, WaVoucherOutput
from plugin.fixtures import scenario as load_scenario
from plugin.fixtures import world
from plugin.rules import oracle
from verifier.audit import judge

ORDER = [
    "reference-matches-oracle",
    "cabin-matches-air",
    "mileage-matches-drives",
    "lodging-matches-claim",
    "meals-matches-trip",
    "total-matches-claims",
    "cabin-within-flown",
    "lodging-amount-fits-basis",
    "total-fits-parts",
    "cabin-correct",
    "mileage-correct",
    "lodging-basis-correct",
    "lodging-amount-correct",
    "total-correct",
    "meals-eligibility-correct",
]
BACKSTOPS = {"lodging-amount-correct", "total-correct"}  # pinned by earlier checks, so never the first failure
VENUE = "chicago-forum-lakeshore"
GOLD_VENUE = case(VENUE)["expected"]
LAZY = {  # the all-null answer: tourist, nothing paid, no lodging, overnight
    "reimbursable_cabin": "tourist",
    "mileage_cents": 0,
    "lodging_basis": None,
    "lodging_per_night_cents": 0,
    "meals_eligible_same_day": None,
    "total_reimbursable_cents": 0,
}


def nights(scenario):
    lodging = load_scenario(scenario)["lodging"]
    return 0 if lodging is None else lodging["nights"]


def consistent(scenario, submission):
    """The submission with its total recomputed from its own parts (C10), as an agent that errs upstream would submit."""
    return {**submission, "total_reimbursable_cents": nights(scenario) * submission["lodging_per_night_cents"] + submission["mileage_cents"]}


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_the_hand_written_answer_passes(scenario: str) -> None:
    result = verdict(scenario, case(scenario)["expected"])
    assert result["valid"] is True and result["score"] == 1.0, result["message"]
    assert [entry["id"] for entry in result["details"]["constraints"]] == ORDER
    assert all(entry["ok"] is True for entry in result["details"]["constraints"])


@pytest.mark.parametrize(
    ("scenario", "index"), [(scenario, index) for scenario in SCENARIOS for index in range(len(case(scenario)["broken"]))]
)
def test_each_broken_answer_fails_with_its_reason_code(scenario: str, index: int) -> None:
    broken = case(scenario)["broken"][index]
    result = verdict(scenario, {**case(scenario)["expected"], **broken["change"]})
    assert result["valid"] is False and 0.0 <= result["score"] < 1.0
    assert result["message"].split(":")[0] == broken["reason"], (broken["why"], result["message"])
    failing = [entry for entry in result["details"]["constraints"] if entry["ok"] is False]
    assert failing[0]["id"] == broken["reason"]


def test_every_reason_code_after_the_answer_key_is_exercised_by_some_case() -> None:
    reasons = {broken["reason"] for scenario in SCENARIOS for broken in case(scenario)["broken"]}
    assert reasons == set(ORDER[1:]) - BACKSTOPS
    # The two backstops can never be the first failure: once the stage-2 fits hold, the basis pins the nightly
    # amount and the submitted parts pin the total, so each fails only together with an earlier decision
    # (tested below). cabin-within-flown is exercised by the coach tickets of seattle-tokyo-robotics and
    # boston-licensing-hearing.


def test_the_signature_flight_gets_different_verdicts_across_2025_01_01() -> None:
    old = verdict("seattle-tokyo-seafood", case("seattle-tokyo-buyers")["expected"])
    assert old["valid"] is False and old["message"].startswith(
        "cabin-correct: business instead of tourist, because scheduled one-way 600 min is not > 840 (regime R2024"
    )
    new = verdict("seattle-tokyo-buyers", case("seattle-tokyo-seafood")["expected"])
    assert new["valid"] is False and new["message"].startswith("cabin-correct: tourist instead of business, because")
    assert "600 min is > 480 (regime R2025, in effect on departure 2025-01-15)" in new["message"]


def test_messages_name_the_rule_and_the_numbers() -> None:
    late = verdict("seattle-tokyo-apples", {**case("seattle-tokyo-apples")["expected"], "reimbursable_cabin": "business"})
    assert "business class approved 2025-02-18, not before departure 2025-02-10" in late["message"]
    miles = verdict("seattle-tokyo-health", {**case("seattle-tokyo-health")["expected"], "reimbursable_cabin": "business"})
    assert "40000 state frequent-flyer miles remain unspent" in miles["message"]
    drive = verdict("spokane-arena-inspection", {**case("spokane-arena-inspection")["expected"], "mileage_cents": 44940, "total_reimbursable_cents": 44940})
    assert "321 mi on 2025-12-31 x 700 tenth-cents (R2025) = 224700" in drive["message"]
    assert "321 mi on 2026-01-01 x 725 tenth-cents (R2026A) = 232725" in drive["message"]
    meals = verdict("yakima-plot-followup", {**case("yakima-plot-followup")["expected"], "meals_eligible_same_day": True})
    assert meals["message"] == "meals-eligibility-correct: 659 min in travel status is not at least 660 for an employee"
    room = verdict("chicago-forum-tower", {**case("chicago-forum-tower")["expected"], "lodging_per_night_cents": 48600})
    assert "basis above_150_conference pays 48601 cents a night for this room, not 48600" in room["message"]
    assert "150% cap 48600 = 150% x (23200 + 9200)" in room["message"]
    venue = verdict(VENUE, {**GOLD_VENUE, "lodging_per_night_cents": 48600})
    assert "basis exception_150 pays 41000 cents a night for this room, not 48600" in venue["message"]
    clipped = verdict("chicago-forum-tower", {**case("chicago-forum-tower")["expected"], "lodging_basis": "exception_150", "lodging_per_night_cents": 48600, "total_reimbursable_cents": 194400})
    assert clipped["message"].startswith("lodging-basis-correct: exception_150 instead of above_150_conference: rate 48601, maximum 23200, 150% cap 48600")
    assert "lowest advertised 48601; 10.30.20.b holds True" in clipped["message"]
    total = verdict("spokane-crane-audit", {**case("spokane-crane-audit")["expected"], "total_reimbursable_cents": 61392})
    assert total["message"] == "total-fits-parts: 2 night(s) x 12600 cents + mileage 48792 cents = 73992, not the 61392 submitted (C10)"
    nothing = verdict("seattle-tokyo-seafood", {**case("seattle-tokyo-seafood")["expected"], "total_reimbursable_cents": 50000})
    assert nothing["message"] == "total-matches-claims: the voucher claims neither lodging nor a drive, so total_reimbursable_cents must be 0, not 50000"


def test_the_success_message_names_each_part_without_a_python_none() -> None:
    with_air = verdict("seattle-tokyo-buyers", case("seattle-tokyo-buyers")["expected"])["message"]
    assert with_air == "the audit is correct: cabin business, mileage 0 cents, no lodging, overnight, total 0 cents"
    without_air = verdict("chicago-forum-king", case("chicago-forum-king")["expected"])["message"]
    assert without_air == (
        "the audit is correct: no airfare, mileage 0 cents, lodging exception_150 at 48600 cents a night, overnight, total 194400 cents"
    )
    same_day = verdict("yakima-plot-followup", case("yakima-plot-followup")["expected"])["message"]
    assert same_day == "the audit is correct: no airfare, mileage 23636 cents, no lodging, same-day meals False, total 23636 cents"
    for scenario in SCENARIOS:
        assert "None" not in verdict(scenario, case(scenario)["expected"])["message"]


def test_the_150_percent_twins_differ_by_one_cent_and_change_basis() -> None:
    """chicago-forum-king ($486.00) and chicago-forum-tower ($486.01) share every other lodging fact, so the
    one cent decides between 10.30.20.a (exception_150 at the cap) and 10.30.20.b (above_150_conference)."""
    king, tower = load_scenario("chicago-forum-king")["lodging"], load_scenario("chicago-forum-tower")["lodging"]
    assert {key: value for key, value in king.items() if key not in ("nightly_rate_cents", "lowest_advertised_rate_cents")} == {
        key: value for key, value in tower.items() if key not in ("nightly_rate_cents", "lowest_advertised_rate_cents")
    }
    assert (king["nightly_rate_cents"], king["lowest_advertised_rate_cents"]) == (48600, 48600)
    assert (tower["nightly_rate_cents"], tower["lowest_advertised_rate_cents"]) == (48601, 48601)
    assert case("chicago-forum-king")["expected"]["lodging_basis"] == "exception_150"
    assert case("chicago-forum-tower")["expected"]["lodging_basis"] == "above_150_conference"
    # each twin's answer fails on the other
    swapped = verdict("chicago-forum-king", case("chicago-forum-tower")["expected"])
    assert swapped["message"].startswith("lodging-amount-fits-basis: basis above_150_conference cannot apply to a 48600-cent room")
    swapped = verdict("chicago-forum-tower", case("chicago-forum-king")["expected"])
    assert swapped["message"].startswith("lodging-basis-correct: exception_150 instead of above_150_conference")


def test_a_failed_stage_leaves_later_stages_unchecked() -> None:
    result = verdict(VENUE, {**GOLD_VENUE, "reimbursable_cabin": None, "mileage_cents": 1})
    states = {entry["id"]: entry["ok"] for entry in result["details"]["constraints"]}
    assert states["cabin-matches-air"] is False
    assert all(states[identifier] is None for identifier in ORDER[6:])
    assert result["message"].startswith("cabin-matches-air")


def test_a_message_counts_the_other_failures() -> None:
    wrong = {**GOLD_VENUE, "reimbursable_cabin": "business", "mileage_cents": 4636, "lodging_basis": "capped_at_max", "lodging_per_night_cents": 23200}
    result = verdict(VENUE, consistent(VENUE, wrong))
    assert result["message"].startswith("cabin-correct: business instead of tourist")
    assert result["message"].endswith("(+4 more)")  # mileage, basis, amount and total too
    assert result["score"] == 0.0  # every live share is wrong


def test_cabin_within_flown_catches_business_paid_on_a_tourist_ticket() -> None:
    facts = load_scenario("seattle-tokyo-buyers")
    facts = {**facts, "air": {**facts["air"], "cabin_flown": "tourist"}}
    key = oracle(world(), facts)
    assert key["reimbursable_cabin"] == "tourist"  # C6: never above what was flown
    result = judge(world(), facts, key, None, {**key, "reimbursable_cabin": "business"})
    assert result["message"] == "cabin-within-flown: reimburses business but the traveler flew tourist"


def test_lodging_amount_correct_is_a_backstop_after_the_basis_checks() -> None:
    """Once the basis is right and the amount fits it, the amount is pinned; lodging-amount-correct still runs
    (and holds) so that a future basis rule with a free amount cannot slip through unchecked."""
    for scenario in SCENARIOS:
        entries = {entry["id"]: entry for entry in verdict(scenario, case(scenario)["expected"])["details"]["constraints"]}
        assert entries["lodging-amount-correct"]["ok"] is True


def test_lodging_amount_correct_fails_only_together_with_the_basis() -> None:
    """The reason code is reachable, as a second failure: the king's answer on the tower's voucher fits its
    stated basis (exception_150 pays the cap, 48600), so stage 2 holds and stage 3 fails on both the basis
    and the amount. Over every basis and the amounts a submission could plausibly name, it never fails while
    lodging-basis-correct holds, and is never the headline."""
    result = verdict("chicago-forum-tower", case("chicago-forum-king")["expected"])
    states = {entry["id"]: entry for entry in result["details"]["constraints"]}
    assert result["message"].startswith("lodging-basis-correct:") and result["message"].endswith("(+2 more)")  # amount and total
    assert states["lodging-basis-correct"]["ok"] is False and states["lodging-amount-correct"]["ok"] is False
    assert states["lodging-amount-correct"]["message"].startswith("48600 cents a night instead of 48601 under above_150_conference")
    assert states["total-correct"]["message"] == "194400 cents instead of 194404: 4 night(s) x 48601 + mileage 0 (C10)"
    for scenario in SCENARIOS:
        lodging = load_scenario(scenario)["lodging"]
        if lodging is None:
            continue
        gold = case(scenario)["expected"]
        cap = (lodging["max_lodging_cents"] + lodging["mie_cents"]) * 3 // 2
        amounts = {0, lodging["nightly_rate_cents"], lodging["max_lodging_cents"], cap, lodging["lowest_advertised_rate_cents"] or 0}
        amounts |= {amount + delta for amount in list(amounts) for delta in (-1, 1)}
        for basis in (member.value for member in LodgingBasis):
            for amount in amounts:
                result = verdict(scenario, consistent(scenario, {**gold, "lodging_basis": basis, "lodging_per_night_cents": amount}))
                states = {entry["id"]: entry["ok"] for entry in result["details"]["constraints"]}
                if states["lodging-amount-correct"] is False:
                    assert states["lodging-basis-correct"] is False, (scenario, basis, amount)
                    assert not result["message"].startswith("lodging-amount-correct"), (scenario, basis, amount)


def test_total_correct_is_a_backstop_that_fails_only_with_a_wrong_part() -> None:
    """A total that fits the submitted parts (stage 2) can be wrong only when the mileage or the nightly amount
    is, so total-correct never headlines; a total that does not fit its parts is caught at stage 2 instead."""
    for scenario in SCENARIOS:
        gold = case(scenario)["expected"]
        changes = [{"mileage_cents": gold["mileage_cents"] + delta} for delta in (-1, 1, 100)]
        changes += [{"lodging_per_night_cents": gold["lodging_per_night_cents"] + delta} for delta in (-1, 1, 100)]
        for change in changes:
            result = verdict(scenario, consistent(scenario, {**gold, **change}))
            states = {entry["id"]: entry["ok"] for entry in result["details"]["constraints"]}
            if states["total-correct"] is False:
                assert states["mileage-correct"] is False or states["lodging-amount-correct"] is False, (scenario, change)
                assert not result["message"].startswith("total-correct"), (scenario, change)
        if gold["total_reimbursable_cents"]:
            misfit = verdict(scenario, {**gold, "total_reimbursable_cents": gold["total_reimbursable_cents"] + 1})
            assert misfit["message"].startswith("total-fits-parts:"), misfit["message"]


def test_a_wrong_answer_key_is_caught_before_the_submission() -> None:
    gold = case("seattle-tokyo-buyers")["expected"]
    wrong_key = build_output({**gold, "reimbursable_cabin": "tourist"}, WaVoucherOutput)
    result = verifier.verify_task(TASK, arguments("seattle-tokyo-buyers"), build_output(gold, WaVoucherOutput), wrong_key, ".")
    assert result["valid"] is False and result["message"].startswith("reference-matches-oracle")


def test_without_a_pinned_reference_the_oracle_still_decides() -> None:
    assert verdict(VENUE, GOLD_VENUE, pinned=False)["valid"] is True
    assert verdict(VENUE, {**GOLD_VENUE, "mileage_cents": 9273}, pinned=False)["valid"] is False


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"reimbursable_cabin": None}, "cabin-matches-air"),  # missing: null where the voucher has a flight
        ({"mileage_cents": 0}, "mileage-matches-drives"),
        ({"mileage_cents": -9272}, "mileage-matches-drives"),
        ({"lodging_basis": None}, "lodging-matches-claim"),
        ({"meals_eligible_same_day": True}, "meals-matches-trip"),
        ({"lodging_basis": "within_max"}, "lodging-amount-fits-basis"),
        ({"lodging_basis": "above_150_conference"}, "lodging-amount-fits-basis"),
        ({"lodging_per_night_cents": 0}, "lodging-amount-fits-basis"),
        ({"lodging_per_night_cents": 41001}, "lodging-amount-fits-basis"),
        ({"total_reimbursable_cents": 0}, "total-matches-claims"),  # nothing paid although drives and lodging are claimed
        ({"total_reimbursable_cents": -173272}, "total-matches-claims"),
        ({"mileage_cents": 9271}, "total-fits-parts"),  # the mileage changed but the total did not
        ({"total_reimbursable_cents": 173271}, "total-fits-parts"),
        ({"mileage_cents": 9271, "total_reimbursable_cents": 173271}, "mileage-correct"),  # one cent either side
        ({"mileage_cents": 9273, "total_reimbursable_cents": 173273}, "mileage-correct"),
        ({"reimbursable_cabin": "business"}, "cabin-correct"),
    ],
)
def test_incorrect_missing_and_inconsistent_answers(change: dict, reason: str) -> None:
    result = verdict(VENUE, {**GOLD_VENUE, **change})
    assert result["valid"] is False and result["message"].split(":")[0] == reason, result["message"]


@pytest.mark.parametrize(
    "raw",
    [
        {**GOLD_VENUE, "mileage_cents": "9272"},  # cents as a string
        {**GOLD_VENUE, "mileage_cents": 92.72},  # dollars as a float
        {**GOLD_VENUE, "mileage_cents": 9272.0},
        {**GOLD_VENUE, "lodging_per_night_cents": True},
        {**GOLD_VENUE, "reimbursable_cabin": "Tourist"},  # wrong case
        {**GOLD_VENUE, "reimbursable_cabin": "first"},  # first is never a reimbursable cabin
        {**GOLD_VENUE, "reimbursable_cabin": "economy"},  # another policy's word
        {**GOLD_VENUE, "lodging_basis": "exception"},  # unknown Enum value
        {**GOLD_VENUE, "meals_eligible_same_day": "no"},
        {key: value for key, value in GOLD_VENUE.items() if key != "mileage_cents"},  # missing field
        {key: value for key, value in GOLD_VENUE.items() if key != "meals_eligible_same_day"},  # nullable still required
        {**GOLD_VENUE, "notes": "approved"},  # extra field
        {**GOLD_VENUE, "mileage_cents": None},  # null for a non-optional field
        {**GOLD_VENUE, "total_reimbursable_cents": "173272"},  # the total as a string
        {**GOLD_VENUE, "total_reimbursable_cents": 1732.72},  # the total in dollars
        {key: value for key, value in GOLD_VENUE.items() if key != "total_reimbursable_cents"},  # missing total
        ["tourist", 9272],  # not an object
    ],
)
def test_malformed_outputs_are_refused_before_the_verifier(raw) -> None:
    with pytest.raises(ValueError):
        build_output(raw, WaVoucherOutput)


def test_non_json_output_never_parses() -> None:
    with pytest.raises(json.JSONDecodeError):
        json.loads("{reimbursable_cabin: tourist, mileage_cents: 9272}")


@pytest.mark.parametrize(
    ("arguments_value", "output_value"),
    [(None, None), ("nonsense", 7), (arguments(VENUE), None), (arguments(VENUE), {"reimbursable_cabin": "tourist"})],
)
def test_the_verifier_never_raises(arguments_value, output_value) -> None:
    result = verifier.verify_task(TASK, arguments_value, output_value, None, ".")
    assert result["valid"] is False and result["message"].startswith("verifier-error")


def test_an_unknown_task_or_tool_id_is_a_failed_verdict_not_an_exception() -> None:
    gold = build_output(GOLD_VENUE, WaVoucherOutput)
    for result in (
        verifier.verify_task("audit-voucher", arguments(VENUE), gold, None, "."),
        verifier.verify_input("get_rates", arguments(VENUE)),
        verifier.verify_output("get_rates", None, None, "."),
    ):
        assert result["valid"] is False and result["message"].startswith("verifier-error")


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_verdicts_are_deterministic_plain_json(scenario: str) -> None:
    broken = {**case(scenario)["expected"], **case(scenario)["broken"][0]["change"]}
    for output in (case(scenario)["expected"], broken):
        first, second = verdict(scenario, output), verdict(scenario, output)
        assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)  # no default=: plain JSON only
        assert isinstance(first["score"], float) and 0.0 <= first["score"] <= 1.0


def another_value(field, value):
    """Some other value of the field's type: the other cabin, another basis, the other flag, one more cent."""
    if field == "reimbursable_cabin":
        return "business" if value == "tourist" else "tourist"
    if field == "lodging_basis":
        return "capped_at_max" if value != "capped_at_max" else "within_max"
    if field == "meals_eligible_same_day":
        return not value
    return value + 1


def live_fields(scenario):
    facts = load_scenario(scenario)
    live = []
    if facts["air"] is not None:
        live.append("reimbursable_cabin")
    if facts["pov_drives"]:
        live.append("mileage_cents")
    if facts["lodging"] is not None:
        live += ["lodging_basis", "lodging_per_night_cents"]
    if not facts["overnight"]:
        live.append("meals_eligible_same_day")
    if facts["pov_drives"] or facts["lodging"] is not None:
        live.append("total_reimbursable_cents")
    return live


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_the_score_is_the_fraction_of_live_fields_that_are_right(scenario: str) -> None:
    """Each output field the voucher makes live is one share; a dead field (null or 0 is its only consistent
    value) earns nothing. The shares are listed in details."""
    gold = case(scenario)["expected"]
    live = live_fields(scenario)
    assert [share["field"] for share in verdict(scenario, gold)["details"]["shares"]] == live
    for field in live:
        if field == "total_reimbursable_cents":
            continue  # a wrong total alone fails total-fits-parts, tested elsewhere
        result = verdict(scenario, consistent(scenario, {**gold, field: another_value(field, gold[field])}))
        wrong = {share["field"] for share in result["details"]["shares"] if not share["ok"]}
        assert field in wrong and wrong <= {field, "total_reimbursable_cents", "lodging_per_night_cents"}, (field, result["message"])
        assert result["valid"] is False and result["score"] == pytest.approx((len(live) - len(wrong)) / len(live))
        assert 0.0 <= result["score"] < 1.0


def test_wrong_in_either_direction_scores_the_same() -> None:
    gold = case(VENUE)["expected"]
    under = verdict(VENUE, consistent(VENUE, {**gold, "mileage_cents": 9271}))
    over = verdict(VENUE, consistent(VENUE, {**gold, "mileage_cents": 9273}))
    far = verdict(VENUE, consistent(VENUE, {**gold, "mileage_cents": 1}))
    assert under["score"] == over["score"] == far["score"] == 0.6  # cabin, basis and amount right; mileage and total wrong
    one_way = verdict(VENUE, consistent(VENUE, {**gold, "mileage_cents": 4636}))
    assert one_way["score"] == 0.6 and one_way["message"].startswith("mileage-correct")
    cabin = verdict(VENUE, {**gold, "reimbursable_cabin": "business"})
    assert cabin["score"] == 0.8


def test_lazy_answers_score_zero_unless_they_are_the_gold_answer() -> None:
    """The all-null answer is the gold audit of a flight-only voucher that refuses business; everywhere else it
    scores 0: it fails referential integrity on any voucher with a drive, lodging or a same-day trip, and names
    the wrong cabin on the business-class vouchers."""
    all_null = {**LAZY, "reimbursable_cabin": None}
    for scenario in SCENARIOS:
        gold = case(scenario)["expected"]
        lazy = verdict(scenario, LAZY)
        if gold == LAZY:
            assert lazy["valid"] is True and lazy["score"] == 1.0
        else:
            assert lazy["valid"] is False and lazy["score"] == 0.0, (scenario, lazy["message"])
        nothing = verdict(scenario, all_null)
        assert nothing["valid"] is False and nothing["score"] == 0.0, (scenario, nothing["message"])
    assert sorted(scenario for scenario in SCENARIOS if case(scenario)["expected"] == LAZY) == ["seattle-tokyo-ceramics", "seattle-tokyo-seafood"]


def test_another_scenarios_answer_never_passes_and_a_fabricated_part_zeroes_the_score() -> None:
    for scenario in SCENARIOS:
        for other in SCENARIOS:
            answer = case(other)["expected"]
            if other == scenario or answer == case(scenario)["expected"]:
                continue
            result = verdict(scenario, answer)
            assert result["valid"] is False and result["score"] < 1.0, (scenario, other)
    # the twins' answers differ in the cabin only: of the three live shares (cabin, mileage, total) the cabin is lost
    assert verdict("seattle-honolulu-fisheries", case("seattle-honolulu-aquaculture")["expected"])["score"] == pytest.approx(2 / 3)
    # inventing a part the voucher lacks zeroes the score, however right the rest is
    invented = verdict(VENUE, {**GOLD_VENUE, "meals_eligible_same_day": True})
    assert invented["message"].startswith("meals-matches-trip") and invented["score"] == 0.0
    forgotten = verdict(VENUE, {**GOLD_VENUE, "reimbursable_cabin": None})
    assert forgotten["message"].startswith("cabin-matches-air") and forgotten["score"] == 0.0


def test_a_broken_answer_key_zeroes_the_score() -> None:
    gold = case(VENUE)["expected"]
    wrong_key = build_output({**gold, "mileage_cents": 1, "total_reimbursable_cents": 164001}, WaVoucherOutput)
    result = verifier.verify_task(TASK, arguments(VENUE), build_output(gold, WaVoucherOutput), wrong_key, ".")
    assert result["valid"] is False and result["score"] == 0.0 and result["message"].startswith("reference-matches-oracle")


@pytest.mark.parametrize(
    ("dates", "valid"),
    [
        (["2025-01-15"], True),
        (["2024-12-31", "2025-01-01", "2026-06-30", "2026-07-01"], True),
        ([], False),
        (["2025-01-15", "2025-01-15"], False),
        (["2025-02-30"], False),
        (["2025-1-5"], False),
        (["2024-01-01", "2024-06-01", "2025-01-01", "2025-06-01", "2026-01-01", "2026-07-01", "2026-08-01"], False),
        (["2023-12-31"], False),  # before the regime table starts
        (["2024-01-01"], True),  # its first day
        (["2025-01-01", "2023-06-30", "2022-01-01"], False),
    ],
)
def test_rules_input_checks(dates: list, valid: bool) -> None:
    assert verifier.verify_input("get_rules_in_effect", build_output({"dates": dates}, RulesInput))["valid"] is valid


def test_dates_before_the_regime_table_are_refused_by_name_and_never_raise() -> None:
    early = build_output({"dates": ["2025-01-01", "2023-06-30", "2022-01-01"]}, RulesInput)
    refused = verifier.verify_input("get_rules_in_effect", early)
    assert refused["valid"] is False and refused["message"] == "2022-01-01, 2023-06-30 before 2024-01-01, where the regime table starts"
    from contract import RulesOutput

    checked = verifier.verify_output("get_rules_in_effect", early, build_output({"rules": []}, RulesOutput), ".")
    assert checked["valid"] is False and checked["message"].startswith("verifier-error")
    json.dumps(refused), json.dumps(checked)


def test_the_reference_tool_output_is_checked_against_the_oracle() -> None:
    good = verifier.verify_output("compute_wa_voucher", arguments(VENUE), reference(VENUE), ".")
    bad = verifier.verify_output("compute_wa_voucher", arguments(VENUE), reference("chicago-forum-colleague"), ".")
    assert good["valid"] is True and bad["valid"] is False
