"""Check the outcome of scripts/ha-smoke.sh.

Reads the Home Assistant log and the recorder database of the smoke run and
exits non-zero when the integration did not work.
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from pathlib import Path

DOMAIN = "webasto_next_modbus"
# Buttons have no state until pressed; everything else must have a value.
STATELESS_DOMAINS = ("button.",)
SUCCESSFUL_POLL = re.compile(r"Finished fetching Webasto Next.*success: True")
# The start of a log record ("2026-11-03 05:04:09.173+00:00 WARNING ...").
LOG_RECORD = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")
# Lines that mention the integration but are expected on every start.
EXPECTED = ("We found a custom integration",)


def _problems_in_log(log: str) -> list[str]:
    """Errors and warnings logged by, or about, the integration."""

    problems = []
    lines = log.splitlines()
    for index, line in enumerate(lines):
        if " ERROR " not in line and " WARNING " not in line and " CRITICAL " not in line:
            continue
        if any(expected in line for expected in EXPECTED):
            continue
        # A traceback names our files in the lines that follow its header,
        # up to the next log record.
        continuation = []
        for following in lines[index + 1 :]:
            if LOG_RECORD.match(following):
                break
            continuation.append(following)
        if DOMAIN in line or f"custom_components/{DOMAIN}" in "\n".join(continuation):
            problems.append(line)
    return problems


def _entity_states(database: Path) -> dict[str, str]:
    if not database.exists():
        return {}
    with sqlite3.connect(database) as connection:
        try:
            rows = connection.execute(
                """
                SELECT meta.entity_id, states.state
                FROM states JOIN states_meta AS meta ON states.metadata_id = meta.metadata_id
                WHERE states.state_id IN (SELECT MAX(state_id) FROM states GROUP BY metadata_id)
                """
            ).fetchall()
        except sqlite3.OperationalError:
            # The recorder had not created its tables yet.
            return {}
    return {entity_id: state for entity_id, state in rows if ".wallbox_" in entity_id}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--polls", type=int, default=3)
    args = parser.parse_args()

    log = args.log.read_text(encoding="utf-8", errors="replace")
    failures = []

    polls = len(SUCCESSFUL_POLL.findall(log))
    print(f"   successful polls: {polls}")
    if polls < args.polls:
        failures.append(f"only {polls} successful polls, expected at least {args.polls}")

    problems = _problems_in_log(log)
    for problem in problems:
        print(f"   log: {problem}")
    if problems:
        failures.append(f"{len(problems)} error/warning line(s) from the integration")

    states = _entity_states(args.config / "home-assistant_v2.db")
    missing = sorted(
        entity_id
        for entity_id, state in states.items()
        if state in ("unavailable", "unknown") and not entity_id.startswith(STATELESS_DOMAINS)
    )
    print(f"   entities: {len(states)}, without a value: {len(missing)}")
    for entity_id in sorted(states):
        if any(key in entity_id for key in ("charge_point_state", "charging_state", "energy")):
            print(f"   {entity_id} = {states[entity_id]}")
    if not states:
        failures.append("no wallbox entities were recorded")
    if missing:
        failures.append(f"entities without a value: {', '.join(missing)}")

    if failures:
        for failure in failures:
            print(f"❌ {failure}", file=sys.stderr)
        return 1
    print("✅ The integration works in this Home Assistant version")
    return 0


if __name__ == "__main__":
    sys.exit(main())
