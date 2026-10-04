"""Lint the shipped automation blueprints for template footguns.

The blueprints under ``blueprints/`` are example assets that ship with the
integration. Nothing else in the suite loads them and ``hassfest`` does not
validate a custom integration's blueprints, so they were previously untested.

This module closes that gap for the most common breakage: referencing blueprint
inputs inside Jinja templates. Per the Home Assistant blueprint schema, inputs
are only usable in templates once exposed via a ``variables:`` block with
``!input``. Referencing them directly -- through an ``inputs.<name>`` namespace
or the non-existent ``i(...)`` shorthand -- is valid Jinja syntax (so the schema
accepts it) but raises "... is undefined" at runtime. Both anti-patterns are
independent of the Home Assistant version.

Every blueprint is also validated against Home Assistant's own blueprint
schema, which rejects the whole blueprint on a single invalid key. What the
solar optimizer actually does is tested by running it as an automation in
``tests/test_solar_blueprint.py``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

BLUEPRINT_DIR = (
    Path(__file__).resolve().parents[1] / "blueprints" / "automation" / "webasto_next_modbus"
)
BLUEPRINT_PATHS = sorted(BLUEPRINT_DIR.glob("*.yaml"))

# Jinja template spans: {{ ... }} and {% ... %}.
_TEMPLATE = re.compile(r"\{\{.*?\}\}|\{%.*?%\}", re.DOTALL)
# ``inputs.foo`` / ``inputs['foo']`` -- the namespace does not exist in templates.
_INPUTS_NAMESPACE = re.compile(r"\binputs\s*[.\[]")
# ``i(...)`` -- not a Home Assistant template function.
_INPUT_SHORTHAND = re.compile(r"(?<![\w.])i\s*\(")


def _templates(text: str) -> list[str]:
    return _TEMPLATE.findall(text)


def test_blueprints_present() -> None:
    assert BLUEPRINT_PATHS, "expected at least one automation blueprint to validate"


@pytest.mark.parametrize("path", BLUEPRINT_PATHS, ids=lambda p: p.name)
def test_blueprint_has_metadata(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    assert re.search(r"^\s*name:\s*\S", text, re.MULTILINE), f"{path.name}: missing name"
    assert "domain: automation" in text, f"{path.name}: not an automation blueprint"


@pytest.mark.parametrize("path", BLUEPRINT_PATHS, ids=lambda p: p.name)
def test_templates_do_not_reference_inputs_directly(path: Path) -> None:
    for template in _templates(path.read_text(encoding="utf-8")):
        assert not _INPUTS_NAMESPACE.search(template), (
            f"{path.name}: template references an 'inputs' namespace that is not "
            f"available at runtime; expose the input via a variables: block with "
            f"!input instead -> {template!r}"
        )
        assert not _INPUT_SHORTHAND.search(template), (
            f"{path.name}: template uses i(...), which is not a Home Assistant "
            f"template function -> {template!r}"
        )


@pytest.mark.parametrize("path", BLUEPRINT_PATHS, ids=lambda p: p.name)
def test_blueprint_passes_home_assistant_schema(path: Path) -> None:
    """Home Assistant rejects the whole blueprint on a single invalid key.

    For example ``unit_of_measurement`` is not an option of the entity
    selector; three blueprints shipped with it and could not be used at all.
    """

    from homeassistant.components.blueprint.models import Blueprint
    from homeassistant.components.blueprint.schemas import BLUEPRINT_SCHEMA
    from homeassistant.util.yaml import load_yaml_dict

    Blueprint(load_yaml_dict(path), expected_domain="automation", schema=BLUEPRINT_SCHEMA)
