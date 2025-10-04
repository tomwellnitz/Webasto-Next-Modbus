"""Command line interface for the virtual wallbox simulator."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .server import serve_tcp
from .simulator import Scenario, VirtualWallboxState, build_default_scenario

_LOGGER = logging.getLogger(__name__)


def _coerce_value(raw: str) -> Any:
    """Convert command-line overrides into numbers when possible."""

    try:
        return int(raw)
    except ValueError:
        pass

    try:
        return float(raw)
    except ValueError:
        return raw


def _parse_overrides(pairs: Sequence[str] | None) -> dict[str, Any]:
    """Parse ``key=value`` pairs into a dictionary."""

    overrides: dict[str, Any] = {}
    if not pairs:
        return overrides

    for pair in pairs:
        if "=" not in pair:
            raise ValueError(f"Invalid override '{pair}'. Expected format key=value")
        key, value = pair.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError("Override keys cannot be empty")
        overrides[key] = _coerce_value(value.strip())
    return overrides


def _load_scenario(path: Path) -> Scenario:
    """Load a scenario definition from a JSON file."""

    text = path.read_text(encoding="utf-8")
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("Scenario file must contain a JSON object")
    unit_id = int(data.get("unit_id", 255))
    values = data.get("values", {})
    write_actions = data.get("write_actions", {})
    if not isinstance(values, dict) or not isinstance(write_actions, dict):
        raise ValueError("Scenario 'values' and 'write_actions' must be objects")
    return Scenario(unit_id=unit_id, values=values, write_actions=write_actions)


def _build_state(
	scenario: Scenario,
	overrides: dict[str, Any],
	*,
	unit_id: int | None,
) -> VirtualWallboxState:
	"""Create a mutable state from the scenario and apply overrides."""

	state = scenario.create_state()
	if unit_id is not None:
		state.unit_id = unit_id
	if overrides:
		state.apply_values(overrides)
	return state


def _build_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(
		description="Run a virtual Webasto Next Modbus wallbox",
	)
	parser.add_argument(
		"--host",
		default="127.0.0.1",
		help="Host/IP address to bind (default: %(default)s)",
	)
	parser.add_argument(
		"--port",
		type=int,
		default=15020,
		help="TCP port to expose (default: %(default)s)",
	)
	parser.add_argument(
		"--unit",
		type=int,
		default=None,
		help="Unit ID to advertise (overrides scenario)",
	)
	parser.add_argument(
		"--scenario",
		type=Path,
		help="Path to a JSON scenario definition",
	)
	parser.add_argument(
		"--set",
		action="append",
		metavar="KEY=VALUE",
		help="Override a register value before starting the server (may be repeated)",
	)
	parser.add_argument(
		"--zero-mode",
		action="store_true",
		help="Use zero-based addressing (advanced; defaults to 1-based Modbus addresses)",
	)
	parser.add_argument(
		"--log-level",
		default="INFO",
		choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"],
		help="Set logging verbosity",
	)
	return parser


async def _async_main(args: argparse.Namespace) -> None:
    """Entrypoint executed inside the asyncio loop."""

    scenario = _load_scenario(args.scenario) if args.scenario else build_default_scenario()
    overrides = _parse_overrides(args.set)
    state = _build_state(scenario, overrides, unit_id=args.unit)
    await serve_tcp(state, host=args.host, port=args.port, zero_mode=args.zero_mode)


def main(argv: Sequence[str] | None = None) -> None:
    """Run the command line interface."""

    parser = _build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=getattr(logging, args.log_level))

    try:
        asyncio.run(_async_main(args))
    except KeyboardInterrupt:  # pragma: no cover - manual interruption
        _LOGGER.info("Virtual wallbox stopped by user")
    except FileNotFoundError as err:
        parser.error(str(err))
    except ValueError as err:
        parser.error(str(err))


if __name__ == "__main__":  # pragma: no cover
    main()
