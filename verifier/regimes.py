from .checks import DATA, UNEXPECTED, compared, plain, result
from .world import day_number, load_world, regime_view

MAX_DATES = 6


def verify_input(value):
    try:
        dates = plain(value)["dates"]
        if not 1 <= len(dates) <= MAX_DATES or len(set(dates)) != len(dates):
            return result(False, f"dates must name 1 to {MAX_DATES} dates, each once")
        for date in dates:
            day_number(date)
    except UNEXPECTED as error:
        return result(False, f"not a valid date list: {error}")
    return result(True, "input is valid")


def verify_output(input_value, output_value, workspace):
    try:
        world = load_world(DATA)
        wanted = {"rules": [regime_view(world, date) for date in plain(input_value)["dates"]]}
        return compared("get_rules_in_effect", plain(output_value), wanted)
    except UNEXPECTED as error:
        return result(False, f"verifier-error: {error!r}")
