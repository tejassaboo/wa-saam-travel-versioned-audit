from slimconfig import build_output

from contract import RulesInput, RulesOutput
from plugin.fixtures import world
from plugin.world import regime_view

MAX_DATES = 6


def get_rules_in_effect(given: RulesInput) -> RulesOutput:
    """The rule regime in effect on each date asked about. It applies no policy: which date governs is the
    agent's call (handbook C1)."""
    if not 1 <= len(given.dates) <= MAX_DATES or len(set(given.dates)) != len(given.dates):
        raise ValueError(f"dates must name 1 to {MAX_DATES} dates, each once")
    return build_output({"rules": [regime_view(world(), date) for date in given.dates]}, RulesOutput)
