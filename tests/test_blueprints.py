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
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

BLUEPRINT_DIR = (
    Path(__file__).resolve().parents[1]
    / "blueprints"
    / "automation"
    / "webasto_next_modbus"
)
BLUEPRINT_PATHS = sorted(BLUEPRINT_DIR.glob("*.yaml"))


class _BlueprintLoader(yaml.SafeLoader):
    """SafeLoader that tolerates the blueprint-only ``!input`` tag."""


# Map ``!input <name>`` to its scalar name so the files parse with a plain loader.
_BlueprintLoader.add_constructor(
    "!input", lambda loader, node: loader.construct_scalar(node)
)

# ``inputs.foo`` / ``inputs['foo']`` -- the namespace does not exist in templates.
_INPUTS_NAMESPACE = re.compile(r"\binputs\s*[.\[]")
# ``i(...)`` -- not a Home Assistant template function.
_INPUT_SHORTHAND = re.compile(r"(?<![\w.])i\s*\(")


def _load(path: Path) -> dict[str, Any]:
    return yaml.load(path.read_text(encoding="utf-8"), Loader=_BlueprintLoader)


def _iter_templates(node: Any):
    """Yield every Jinja template string found anywhere in the structure."""

    if isinstance(node, str):
        if "{{" in node or "{%" in node:
            yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from _iter_templates(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_templates(item)


def test_blueprints_present() -> None:
    assert BLUEPRINT_PATHS, "expected at least one automation blueprint to validate"


@pytest.mark.parametrize("path", BLUEPRINT_PATHS, ids=lambda p: p.name)
def test_blueprint_has_metadata(path: Path) -> None:
    data = _load(path)
    assert data.get("blueprint", {}).get("name")
    assert data["blueprint"].get("domain") == "automation"


@pytest.mark.parametrize("path", BLUEPRINT_PATHS, ids=lambda p: p.name)
def test_templates_do_not_reference_inputs_directly(path: Path) -> None:
    data = _load(path)
    for text in _iter_templates(data):
        assert not _INPUTS_NAMESPACE.search(text), (
            f"{path.name}: template references an 'inputs' namespace that is not "
            f"available at runtime; expose the input via a variables: block with "
            f"!input instead -> {text!r}"
        )
        assert not _INPUT_SHORTHAND.search(text), (
            f"{path.name}: template uses i(...), which is not a Home Assistant "
            f"template function -> {text!r}"
        )
