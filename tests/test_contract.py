"""Structured input and structured output: every contract field is typed and described, every policy fact
reaches the agent in a typed field (never only in prose), and nothing the verifier grades is free text."""

import dataclasses
import typing
from enum import Enum

import contract
from contract import (
    AirTravel,
    FlownCabin,
    Lodging,
    LodgingReason,
    PovDrive,
    Regime,
    TravelerType,
    VoucherOutput,
    WaVoucherOutput,
)

CONTRACT_CLASSES = [
    value
    for value in vars(contract).values()
    if isinstance(value, type) and dataclasses.is_dataclass(value) and value.__module__ == contract.__name__
]
# str fields that carry no policy fact: ids, IATA codes, documented-format dates, and descriptive labels.
DESCRIPTIVE = {"request_text", "name", "agency", "city", "flight", "from_place", "to_place", "location", "hotel", "source"}


def annotated_fields(cls):
    """(name, type, description) for every field, from the class's Annotated hints."""
    hints = typing.get_type_hints(cls, include_extras=True)
    for field in dataclasses.fields(cls):
        hint = hints[field.name]
        assert typing.get_origin(hint) is typing.Annotated, f"{cls.__name__}.{field.name} is not Annotated"
        base, *metadata = typing.get_args(hint)
        yield field.name, base, metadata[0]


def strip_optional(base):
    """T for T | None, else the type itself."""
    args = typing.get_args(base)
    return next(arg for arg in args if arg is not type(None)) if type(None) in args else base


def test_every_field_is_annotated_with_a_description() -> None:
    assert len(CONTRACT_CLASSES) >= 12
    for cls in CONTRACT_CLASSES:
        for name, _, description in annotated_fields(cls):
            assert isinstance(description, str) and len(description.split()) >= 3, f"{cls.__name__}.{name}"


def test_every_policy_fact_reaches_the_agent_in_a_typed_field() -> None:
    voucher = {name: base for name, base, _ in annotated_fields(VoucherOutput)}
    air = {name: base for name, base, _ in annotated_fields(AirTravel)}
    drive = {name: base for name, base, _ in annotated_fields(PovDrive)}
    room = {name: base for name, base, _ in annotated_fields(Lodging)}
    regime = {name: base for name, base, _ in annotated_fields(Regime)}
    traveler = {name: base for name, base, _ in annotated_fields(contract.Traveler)}
    airport = {name: base for name, base, _ in annotated_fields(contract.Airport)}
    assert traveler["traveler_type"] is TravelerType and airport["continental_us"] is bool
    assert voucher["overnight"] is bool and voucher["travel_status_minutes"] == (int | None)
    assert voucher["departure_date"] is str and voucher["pov_drives"] == list[PovDrive]
    assert air["scheduled_one_way_minutes"] is int and air["cabin_flown"] is FlownCabin
    assert air["business_approval_date"] == (str | None) and air["unused_state_miles"] is int
    assert drive["miles"] is int and drive["date"] is str
    assert room["claimed_reasons"] == list[LodgingReason] and room["attendance_required"] is bool
    for name in ("nightly_rate_cents", "max_lodging_cents", "mie_cents"):
        assert room[name] is int
    assert room["lowest_advertised_rate_cents"] == (int | None)
    assert regime["business_over_minutes"] is int and regime["pov_rate_tenth_cents"] is int


def test_no_str_field_carries_a_policy_fact() -> None:
    """Every str is an id, an IATA code, a documented-format date, or a descriptive label named above."""
    for cls in CONTRACT_CLASSES:
        for name, base, description in annotated_fields(cls):
            if strip_optional(base) is not str:
                continue
            documented = "YYYY-MM-DD" in description or "IATA" in description or name.endswith("_id")
            assert documented or name in DESCRIPTIVE, f"{cls.__name__}.{name}"


def test_the_graded_output_has_no_free_text() -> None:
    for name, base, _ in annotated_fields(WaVoucherOutput):
        inner = strip_optional(base)
        assert inner in (int, bool) or (isinstance(inner, type) and issubclass(inner, Enum)), f"{name}: {base}"


def test_no_float_anywhere() -> None:
    for cls in CONTRACT_CLASSES:
        for name, base, _ in annotated_fields(cls):
            assert float not in (base, *typing.get_args(base)), f"{cls.__name__}.{name}"


def test_dates_say_their_format_amounts_their_unit_and_nulls_their_meaning() -> None:
    for cls in CONTRACT_CLASSES:
        for name, base, description in annotated_fields(cls):
            if name.endswith(("_date", "_local", "date", "dates", "effective_from", "effective_to")):
                assert "YYYY-MM-DD" in description, f"{cls.__name__}.{name}"
            if name.endswith("_cents"):
                assert "cents" in description, f"{cls.__name__}.{name}"
            if name.endswith("_minutes"):
                assert "minutes" in description.lower() or "min" in description, f"{cls.__name__}.{name}"
            if typing.get_origin(base) is not None and type(None) in typing.get_args(base):
                assert "null" in description, f"{cls.__name__}.{name} does not say what null means"
            if typing.get_origin(base) is list:
                assert any(word in description for word in ("order", "each once", "One entry")), f"{cls.__name__}.{name}"
