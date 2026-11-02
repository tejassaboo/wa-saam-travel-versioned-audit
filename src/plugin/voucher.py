from slimconfig import build_output

from contract import ScenarioInput, VoucherOutput
from plugin.fixtures import scenario, world
from plugin.rules import voucher


def get_voucher(given: ScenarioInput) -> VoucherOutput:
    """The scenario's travel voucher: the traveler's note and the structured facts, never an answer."""
    return build_output(voucher(world(), scenario(given.scenario.value)), VoucherOutput)
