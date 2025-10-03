"""Tests for Modbus bridge decoding helpers."""

from __future__ import annotations

from custom_components.webasto_next_modbus.const import RegisterDefinition
from custom_components.webasto_next_modbus.hub import _decode_register


def _build_string_register(count: int = 3) -> RegisterDefinition:
    return RegisterDefinition(
        key="serial_number",
        name="Serial Number",
        address=100,
        count=count,
        register_type="input",
        data_type="string",
        entity="sensor",
        encoding="utf-8",
    )


def test_decode_register_string_trims_trailing_nulls() -> None:
    """String register decoding should drop padding and decode text."""

    definition = _build_string_register()
    raw = b"BOX1\x00\x00"
    data = [int.from_bytes(raw[i : i + 2], "big") for i in range(0, len(raw), 2)]

    decoded = _decode_register(definition, data)

    assert decoded == "BOX1"
