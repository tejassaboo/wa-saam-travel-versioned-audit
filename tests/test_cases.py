"""Every scenario end to end without an LLM: the oracle equals the hand-written expectation, the answer
is unique, and a scripted agent written from the handbook alone reaches it through the tools within the
step budget; each broken variant of its answer fails with the case's reason code."""

import pytest
from helpers import ROOT, SCENARIOS, case, verdict
from scripted_agent import run
from slimconfig import build_output, plain_output

from contract import TOOLS, LodgingBasis, Tool, WaCabin, WaScenario, WaVoucherOutput
from plugin import get_rules_in_effect, get_voucher
from plugin.fixtures import scenario as load_scenario
from plugin.fixtures import world
from plugin.rules import drive_tenth_cents, mileage_cents, oracle, round_half_up_tenths

IMPLEMENTATIONS = {Tool.GET_VOUCHER: get_voucher, Tool.GET_RULES_IN_EFFECT: get_rules_in_effect}
MAX_TOOL_CALLS = 4  # plus submit, within the hosted 6 steps whose last may not call tools


def call(tool, arguments):
    """A tool call as NanoAgent makes it: plain JSON in, built into the input class, plain JSON out."""
    given, made = TOOLS[Tool(tool)]
    output = IMPLEMENTATIONS[Tool(tool)](build_output(arguments, given))
    assert isinstance(output, made)
    return plain_output(output)


def alternatives(field, value):
    """Every other value a submission could put in ``field``: other Enum members and null, nearby cents."""
    if field == "reimbursable_cabin":
        return [other for other in [None, *(member.value for member in WaCabin)] if other != value]
    if field == "lodging_basis":
        return [other for other in [None, *(member.value for member in LodgingBasis)] if other != value]
    if field == "meals_eligible_same_day":
        return [other for other in (None, True, False) if other != value]
    return [value - 1, value + 1, value - 10, value + 10, 0 if value else 1]


def test_every_scenario_has_a_case() -> None:
    assert sorted(SCENARIOS) == sorted(path.stem for path in (ROOT / "tests" / "cases").glob("*.json"))


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_oracle_equals_the_hand_written_expectation(scenario: str) -> None:
    assert oracle(world(), load_scenario(scenario)) == case(scenario)["expected"]


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_the_answer_is_unique(scenario: str) -> None:
    """Exactly one submission passes: changing any one field of the expected answer to any other value fails."""
    expected = case(scenario)["expected"]
    for field, value in expected.items():
        for other in alternatives(field, value):
            result = verdict(scenario, {**expected, field: other})
            assert result["valid"] is False and result["score"] < 1.0, (field, other)


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_the_scripted_agent_reaches_the_gold_answer_within_budget(scenario: str) -> None:
    calls, submission = run(scenario, call)
    assert len(calls) <= MAX_TOOL_CALLS
    assert calls[0][0] == "get_voucher"
    built = build_output(submission, WaVoucherOutput)  # the submit tool's own shape check
    result = verdict(scenario, plain_output(built))
    assert result["valid"] is True, result["message"]
    assert submission == case(scenario)["expected"]


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_broken_variants_of_the_scripted_answer_fail_with_their_reason(scenario: str) -> None:
    _, submission = run(scenario, call)
    for broken in case(scenario)["broken"]:
        result = verdict(scenario, {**submission, **broken["change"]})
        assert result["valid"] is False and result["message"].split(":")[0] == broken["reason"], (broken["why"], result["message"])


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_request_text_is_flavour_only(scenario: str) -> None:
    """The structured fields alone decide the answer (C2): the oracle ignores request_text, and the scripted
    agent reaches the same submission when the words are blanked out."""
    facts = load_scenario(scenario)
    assert oracle(world(), {**facts, "request_text": ""}) == oracle(world(), facts)

    def muted(tool, arguments):
        output = call(tool, arguments)
        return {**output, "request_text": ""} if tool == "get_voucher" else output

    assert run(scenario, muted)[1] == run(scenario, call)[1]


def test_the_signature_pair_differs_only_by_departure_date() -> None:
    """The same flight, approval lead time and miles: only the departure date's regime changes the verdict."""
    old, new = load_scenario("seattle-tokyo-seafood"), load_scenario("seattle-tokyo-buyers")
    keep = ("origin", "destination", "scheduled_one_way_minutes", "cabin_flown", "unused_state_miles")
    assert {key: old["air"][key] for key in keep} == {key: new["air"][key] for key in keep}
    assert [segment["in_air_minutes"] for segment in old["air"]["segments"]] == [segment["in_air_minutes"] for segment in new["air"]["segments"]]
    assert case("seattle-tokyo-seafood")["expected"]["reimbursable_cabin"] == "tourist"
    assert case("seattle-tokyo-buyers")["expected"]["reimbursable_cabin"] == "business"


def test_no_scenario_id_names_a_graded_value() -> None:
    """Ids describe the trip, never the verdict: no Enum value of the graded output, nor the words the
    lodging bases are built from, appears in any id (facts may; they are in the typed fields anyway)."""
    verdict_words = [member.value for member in LodgingBasis] + [member.value for member in WaCabin]
    verdict_words += ["above-150", "within-max", "capped", "exception", "eligible"]
    for member in WaScenario:
        for word in verdict_words:
            assert word.replace("_", "-") not in member.value, (member.value, word)


def test_rounding_once_after_the_sum_differs_from_rounding_each_drive_only_on_the_honolulu_twins() -> None:
    """C8 rounds once after summing. Only the Honolulu twins have two drives that each end in a half cent
    (61 mi x 72.5 cents = 4422.5 twice): once gives 8845, each-drive would give 4423 + 4423 = 8846. Every
    other bundled voucher gives the same answer under both readings."""
    differing = []
    for scenario in SCENARIOS:
        facts = load_scenario(scenario)
        tenths = [drive_tenth_cents(world(), drive) for drive in facts["pov_drives"]]
        once, each = round_half_up_tenths(sum(tenths)), sum(round_half_up_tenths(part) for part in tenths)
        assert mileage_cents(world(), facts) == once == case(scenario)["expected"]["mileage_cents"]
        if once != each:
            differing.append((scenario, once, each))
    assert differing == [("seattle-honolulu-fisheries", 8845, 8846), ("seattle-honolulu-aquaculture", 8845, 8846)]
