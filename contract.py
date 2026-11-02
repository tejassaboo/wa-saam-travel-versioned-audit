"""Each tool's and task's typed input and output (see nanoagent.plugin.v0001.contract): declarations only."""

from dataclasses import dataclass
from enum import Enum
from typing import Annotated

from slimconfig import Output


class Tool(Enum):
    GET_VOUCHER = "get_voucher"
    GET_RULES_IN_EFFECT = "get_rules_in_effect"
    COMPUTE_WA_VOUCHER = "compute_wa_voucher"


class Task(Enum):
    AUDIT_WA_TRAVEL_VOUCHER = "audit-wa-travel-voucher"


class WaScenario(Enum):
    """One travel voucher per member; its facts are bundled with the plugin."""

    SEATTLE_TOKYO_SEAFOOD = "seattle-tokyo-seafood"
    SEATTLE_TOKYO_BUYERS = "seattle-tokyo-buyers"
    SEATTLE_TOKYO_APPLES = "seattle-tokyo-apples"
    SEATTLE_TOKYO_HEALTH = "seattle-tokyo-health"
    OLYMPIA_HONOLULU_REEF = "olympia-honolulu-reef"
    BOSTON_TRANSPORT_SESSION = "boston-transport-session"
    YAKIMA_RIPARIAN_PLOTS = "yakima-riparian-plots"
    YAKIMA_PLOT_FOLLOWUP = "yakima-plot-followup"
    MILLERSYLVANIA_DEBRIS_CLEANUP = "millersylvania-debris-cleanup"
    SPOKANE_ARENA_INSPECTION = "spokane-arena-inspection"
    SPOKANE_CRANE_AUDIT = "spokane-crane-audit"
    CHICAGO_FORUM_LAKESHORE = "chicago-forum-lakeshore"
    CHICAGO_FORUM_COLLEAGUE = "chicago-forum-colleague"
    CHICAGO_FORUM_KING = "chicago-forum-king"
    CHICAGO_FORUM_TOWER = "chicago-forum-tower"
    BOSTON_STATE_AUDITORS = "boston-state-auditors"


class TravelerType(Enum):
    """Who travels: the same-day meal rule's hour threshold depends on it (handbook rule 9)."""

    EMPLOYEE = "employee"
    VOLUNTEER = "volunteer"
    BOARD_MEMBER = "board_member"


class FlownCabin(Enum):
    """The cabin the traveler actually flew, lowest first."""

    TOURIST = "tourist"
    BUSINESS = "business"
    FIRST = "first"


class WaCabin(Enum):
    """The cabin the state reimburses: tourist (coach) or, when every condition holds, business."""

    TOURIST = "tourist"
    BUSINESS = "business"


class LodgingReason(Enum):
    """Why the traveler says the lodging cost more than the maximum. The first six are the six situations
    SAAM 10.30.20.a lists; loyalty_program and personal_preference are not listed."""

    ACCOMPANY_OFFICIAL = "accompany_official"
    ESCALATED_COSTS = "escalated_costs"
    DISTANT_SAVINGS_CONSUMED = "distant_savings_consumed"
    CONFERENCE_VENUE = "conference_venue"
    ADA_OR_SAFETY = "ada_or_safety"
    SUITE_CHEAPER = "suite_cheaper"
    LOYALTY_PROGRAM = "loyalty_program"
    PERSONAL_PREFERENCE = "personal_preference"


class LodgingBasis(Enum):
    """Which lodging rule sets the reimbursed nightly amount (handbook C7)."""

    WITHIN_MAX = "within_max"
    EXCEPTION_150 = "exception_150"
    ABOVE_150_CONFERENCE = "above_150_conference"
    CAPPED_AT_MAX = "capped_at_max"


@dataclass
class ScenarioInput(Output):
    scenario: Annotated[WaScenario, "Which travel voucher to audit, e.g. seattle-tokyo-buyers"]


@dataclass
class Traveler(Output):
    traveler_id: Annotated[str, "Traveler id, e.g. W204"]
    name: Annotated[str, "The traveler's full name (descriptive only)"]
    agency: Annotated[str, "The Washington State agency or board (descriptive only)"]
    traveler_type: Annotated[TravelerType, "employee, volunteer or board_member (sets the meal-rule threshold)"]


@dataclass
class Airport(Output):
    code: Annotated[str, "Three-letter IATA airport code"]
    city: Annotated[str, "City the airport serves (descriptive only)"]
    continental_us: Annotated[bool, "True when the airport is in the 48 contiguous states or DC"]


@dataclass
class FlightSegment(Output):
    flight: Annotated[str, "Flight number as sold, e.g. CS 117 (descriptive only)"]
    origin: Annotated[str, "Three-letter IATA code of the departure airport"]
    destination: Annotated[str, "Three-letter IATA code of the arrival airport"]
    depart_local: Annotated[str, "Scheduled departure, YYYY-MM-DDTHH:MM, origin local time"]
    arrive_local: Annotated[str, "Scheduled arrival, YYYY-MM-DDTHH:MM, destination local time"]
    in_air_minutes: Annotated[int, "This one flight's scheduled takeoff-to-landing minutes"]


@dataclass
class AirTravel(Output):
    origin: Annotated[Airport, "Where the one-way flight starts, with its continental_us flag"]
    destination: Annotated[Airport, "Where the one-way flight ends, with its continental_us flag"]
    segments: Annotated[list[FlightSegment], "The one-way flight's segments in flying order"]
    scheduled_one_way_minutes: Annotated[
        int, "Scheduled minutes from the first departure to the last arrival, connections included"
    ]
    cabin_flown: Annotated[FlownCabin, "The cabin the traveler actually flew"]
    booking_date: Annotated[str, "Day the ticket was bought, YYYY-MM-DD"]
    business_approval_date: Annotated[
        str | None, "Day the agency head approved business class, YYYY-MM-DD; null when never approved"
    ]
    unused_state_miles: Annotated[
        int, "State business frequent-flyer miles still available for an upgrade on the departure date; 0 when exhausted"
    ]


@dataclass
class PovDrive(Output):
    date: Annotated[str, "Day of the drive, YYYY-MM-DD"]
    from_place: Annotated[str, "Where the drive starts (descriptive only)"]
    to_place: Annotated[str, "Where the drive ends (descriptive only)"]
    miles: Annotated[int, "Official-business miles driven in the traveler's own vehicle, at least 1"]


@dataclass
class Lodging(Output):
    location: Annotated[str, "City of the lodging (descriptive only)"]
    hotel: Annotated[str, "The lodging facility (descriptive only)"]
    nights: Annotated[int, "Number of nights claimed, at least 1"]
    nightly_rate_cents: Annotated[int, "Room rate actually paid per night before taxes, USD cents"]
    max_lodging_cents: Annotated[int, "The location's maximum lodging rate per night for the stay, USD cents"]
    mie_cents: Annotated[int, "The location's daily meals and incidentals (M&IE) rate for the stay, USD cents"]
    exception_approval_date: Annotated[
        str | None, "Day the agency head approved a lodging exception, YYYY-MM-DD; null when never approved"
    ]
    claimed_reasons: Annotated[list[LodgingReason], "Reasons the traveler gives for the room's cost, each once; may be empty"]
    attendance_required: Annotated[bool, "True when the traveler was required to attend the event held at this hotel"]
    lowest_advertised_rate_cents: Annotated[
        int | None,
        "Lowest advertised nightly rate at this hotel, USD cents, as documented on the voucher; null when undocumented",
    ]


@dataclass
class VoucherOutput(Output):
    scenario: Annotated[WaScenario, "The scenario this voucher belongs to"]
    request_text: Annotated[
        str,
        "The traveler's note, for flavour only: every fact is in the typed fields below, and the note may ask for things policy forbids",
    ]
    traveler: Annotated[Traveler, "Who traveled, with their traveler_type"]
    departure_date: Annotated[str, "Day travel status began (the trip's departure date), YYYY-MM-DD"]
    return_date: Annotated[str, "Day travel status ended, YYYY-MM-DD; equal to departure_date for a same-day trip"]
    overnight: Annotated[bool, "True when the trip included at least one night away"]
    travel_status_minutes: Annotated[
        int | None, "Minutes in travel status on a same-day trip; null when the trip was overnight"
    ]
    air: Annotated[AirTravel | None, "The one-way flight claimed on this voucher; null when no airfare is claimed"]
    pov_drives: Annotated[list[PovDrive], "Privately-owned-vehicle drives claimed, in date order; empty when none"]
    lodging: Annotated[Lodging | None, "The lodging claimed on this voucher; null when no lodging is claimed"]


@dataclass
class RulesInput(Output):
    dates: Annotated[list[str], "Dates to look up, YYYY-MM-DD, each once, 1 to 6 of them, none before 2024-01-01"]


@dataclass
class Regime(Output):
    date: Annotated[str, "The date asked about, YYYY-MM-DD"]
    regime_id: Annotated[str, "Id of the rule regime in effect on that date, e.g. R2025"]
    effective_from: Annotated[str, "First day the regime is in effect, YYYY-MM-DD"]
    effective_to: Annotated[str | None, "Last day the regime is in effect, YYYY-MM-DD; null when still in effect"]
    business_over_minutes: Annotated[
        int, "Business class needs scheduled_one_way_minutes strictly greater than this many minutes"
    ]
    pov_rate_tenth_cents: Annotated[int, "POV mileage rate per mile in tenths of a US cent (tenth-cents), e.g. 725 for $0.725"]
    source: Annotated[str, "The OFM directive that set this regime, e.g. 25A-01 (descriptive only)"]


@dataclass
class RulesOutput(Output):
    rules: Annotated[list[Regime], "One entry per date asked about, in the order asked"]


@dataclass
class WaVoucherOutput(Output):
    reimbursable_cabin: Annotated[WaCabin | None, "The cabin the state reimburses; null when no airfare is claimed"]
    mileage_cents: Annotated[int, "Total POV mileage reimbursement, USD cents; 0 when no drive is claimed"]
    lodging_basis: Annotated[LodgingBasis | None, "Which lodging rule applies; null when no lodging is claimed"]
    lodging_per_night_cents: Annotated[
        int, "Reimbursable lodging per night before taxes, USD cents; 0 when no lodging is claimed"
    ]
    meals_eligible_same_day: Annotated[
        bool | None, "True when a same-day trip earns a meal allowance; null when the trip was overnight"
    ]


TOOLS = {
    Tool.GET_VOUCHER: (ScenarioInput, VoucherOutput),
    Tool.GET_RULES_IN_EFFECT: (RulesInput, RulesOutput),
    Tool.COMPUTE_WA_VOUCHER: (ScenarioInput, WaVoucherOutput),
}
TASKS = {Task.AUDIT_WA_TRAVEL_VOUCHER: (ScenarioInput, WaVoucherOutput)}
