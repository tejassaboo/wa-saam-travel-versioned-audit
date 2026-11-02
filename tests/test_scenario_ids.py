"""Scenario ids are visible to the agent (the task input is the id), so an id must not leak the answer:
no graded output value, no boundary number or date, no informal rule term, and no category that by itself
fixes the answer. A place plus a neutral persona or event noun is flavour only. Modelled on T1's test."""

import re

import contract

# The graded output's Enums, and the input categories whose value alone settles part of the answer: the
# traveler type sets the same-day meal threshold, the cabin flown caps the cabin, and the claimed lodging
# reasons and approvals pick the lodging basis. The departure date picks the rule regime, so no date parts.
SCENARIO_ENUMS = [contract.WaScenario]
GRADED_ENUMS = [contract.WaCabin, contract.LodgingBasis]
CATEGORY_ENUMS = [contract.TravelerType, contract.FlownCabin, contract.LodgingReason]
CATEGORY_TERMS = {
    # rule-7 and regime words
    "meeting", "conference", "venue", "regime", "version", "directive", "rate", "mileage", "miles", "unspent",
    "points", "loyalty", "platinum", "late", "early", "advance", "approval", "unapproved", "no", "not",
    "day", "trip", "same", "connection", "connecting", "nonstop", "direct", "drive", "car", "pov",
    "coach", "upgrade", "suite", "escalated", "official", "dignitary", "ada", "safety",
    # date words (the date picks the regime)
    "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec",
    "january", "february", "march", "april", "june", "july", "august", "september", "october", "november",
    "december", "new", "year", "eve",
}

UNIVERSAL_TERMS = {
    # informal rule terms (never rule terms in a handbook)
    "red", "eye", "redeye", "long", "haul", "longhaul", "short", "overnight",
    # boundary and threshold words
    "boundary", "threshold", "limit", "cap", "edge", "exact", "exactly", "over", "under", "max", "min",
    "minutes", "hours", "days", "cents", "dollars",
    # decision and verdict words
    "approve", "approved", "deny", "denied", "reject", "rejected", "compliant", "noncompliant", "violation",
    "exception", "upgrade", "downgrade", "valid", "invalid", "pass", "fail", "allowed", "disallowed",
    "cheap", "cheapest", "trap",
    # spelled-out numbers
    "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
    "sixteen", "twenty", "hundred",
}


def enum_tokens(enums):
    """Every underscore-separated word of every member value, lower-cased."""
    return {word for enum in enums for member in enum for word in str(member.value).lower().split("_")}


FORBIDDEN = UNIVERSAL_TERMS | enum_tokens(GRADED_ENUMS) | enum_tokens(CATEGORY_ENUMS) | CATEGORY_TERMS
IDS = [member.value for enum in SCENARIO_ENUMS for member in enum]


def test_ids_are_kebab_case_without_numbers():
    for scenario in IDS:
        assert re.fullmatch(r"[a-z]+(-[a-z]+)*", scenario), f"{scenario}: lower-case words only, no digits"


def test_ids_leak_no_answer_term():
    for scenario in IDS:
        leaked = sorted(set(scenario.split("-")) & FORBIDDEN)
        assert not leaked, f"{scenario} leaks {leaked}"


def test_ids_are_unique():
    assert len(IDS) == len(set(IDS))


OLD_IDS = (
    "boston-first-class", "chicago-conference-venue", "chicago-loyalty-points", "seattle-tokyo-2024-12",
    "seattle-tokyo-2025-01", "seattle-tokyo-late-approval", "seattle-tokyo-miles-unspent",
    "spokane-escalated-no-approval", "spokane-new-year-drive", "volunteer-day-trip-dec31", "yakima-day-trip-jun30",
    "yakima-day-trip-jul01", "olympia-honolulu-connection", "boston-auditors-meeting",
)


def test_the_old_leaky_ids_would_have_been_caught():
    """The ids renamed in the Tier-2 integration pass each fail the digit or the word check."""
    for old in OLD_IDS:
        assert re.search(r"\d", old) or set(old.split("-")) & FORBIDDEN, old
