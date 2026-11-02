"""The deterministic verifier: each tool's checks live in its own module, on contract instances."""

from contract import Task, Tool

from . import audit, regimes, voucher
from .checks import result

TOOLS = {Tool.GET_VOUCHER: voucher, Tool.GET_RULES_IN_EFFECT: regimes, Tool.COMPUTE_WA_VOUCHER: audit}
# task -> its output's check, verify_task(arguments, output, reference, workspace)
TASKS = {Task.AUDIT_WA_TRAVEL_VOUCHER: audit.verify_task}


def verify_input(tool, value):
    try:
        module = TOOLS[Tool(tool)]
    except ValueError as error:
        return result(False, f"verifier-error: {error}")
    return module.verify_input(value)


def verify_output(tool, input_value, output_value, workspace):
    try:
        module = TOOLS[Tool(tool)]
    except ValueError as error:
        return result(False, f"verifier-error: {error}")
    return module.verify_output(input_value, output_value, workspace)


def verify_task(task, arguments, output, reference, workspace):
    try:
        check = TASKS[Task(task)]
    except ValueError as error:
        return result(False, f"verifier-error: {error}")
    return check(arguments, output, reference, workspace)
