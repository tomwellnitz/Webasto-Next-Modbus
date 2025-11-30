"""Utility script to probe a Webasto Next wallbox via Modbus TCP."""

from __future__ import annotations

import argparse
import asyncio
import logging
import inspect
from typing import Iterable, Any, cast

from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException

LOGGER = logging.getLogger("modbus_diagnostics")

LIFE_BIT_REGISTER = 6000
LIFE_BIT_VALUE = 1
DEFAULT_READ_REGISTERS: list[int] = [1000, 1001, 1002, 1004, 1006]


def parse_registers(raw: str | None) -> Iterable[int]:
    """Parse a comma separated list of register numbers."""

    if not raw:
        return DEFAULT_READ_REGISTERS
    values: list[int] = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            values.append(int(item, 0))
        except ValueError as exc:  # pragma: no cover - CLI validation only
            raise argparse.ArgumentTypeError(f"Invalid register '{item}'") from exc
    if not values:
        raise argparse.ArgumentTypeError("No registers provided")
    return tuple(values)


async def _invoke_with_unit(method, *args, unit_id: int, **kwargs: Any):
    """Call a pymodbus coroutine while handling different unit keywords."""

    last_error: TypeError | None = None
    for keyword in ("unit", "slave", "device_id"):
        if keyword in kwargs:
            continue
        try:
            current_kwargs = dict(kwargs)
            current_kwargs[keyword] = unit_id
            return await method(*args, **current_kwargs)
        except TypeError as err:
            message = str(err)
            if "unexpected keyword" in message or "multiple values" in message:
                last_error = err
                continue
            raise
    if last_error is not None:
        raise last_error
    return await method(*args, unit_id, **kwargs)


async def run_probe(args: argparse.Namespace) -> int:
    """Connect to the wallbox, read registers, and optionally send keepalive."""

    client = AsyncModbusTcpClient(
        args.host,
        port=args.port,
        timeout=args.timeout,
    )
    try:
        LOGGER.info("Connecting to %s:%s (unit %s)", args.host, args.port, args.unit)
        await client.connect()
        if not client.connected:
            LOGGER.error("Connection failed")
            return 1
        LOGGER.info("Connection established")

        registers = list(args.registers or DEFAULT_READ_REGISTERS)
        for iteration in range(args.iterations):
            for address in registers:
                try:
                    response = await _invoke_with_unit(
                        client.read_holding_registers,
                        address,
                        unit_id=args.unit,
                        count=1,
                    )
                except ModbusException as err:
                    LOGGER.error(
                        "Read of register %s failed on attempt %s/%s: %s",
                        address,
                        iteration + 1,
                        args.iterations,
                        err,
                    )
                    continue
                if response.isError():
                    LOGGER.error(
                        "Modbus exception for register %s: %s",
                        address,
                        response,
                    )
                else:
                    value = response.registers[0]
                    LOGGER.info(
                        "Read holding[%s]=0x%04X (%s)",
                        address,
                        value,
                        value,
                    )

            if args.keepalive:
                try:
                    write = await _invoke_with_unit(
                        client.write_register,
                        LIFE_BIT_REGISTER,
                        LIFE_BIT_VALUE,
                        unit_id=args.unit,
                    )
                except ModbusException as err:
                    LOGGER.error("Life Bit write failed: %s", err)
                else:
                    if write.isError():
                        LOGGER.error("Life Bit write returned Modbus error: %s", write)
                    else:
                        LOGGER.info(
                            "Life Bit write succeeded (register %s <- %s)",
                            LIFE_BIT_REGISTER,
                            LIFE_BIT_VALUE,
                        )

            if iteration + 1 < args.iterations:
                await asyncio.sleep(args.interval)
    finally:
        if client.connected:
            LOGGER.info("Closing connection")
        close_result = client.close()
        if inspect.isawaitable(close_result):  # type: ignore[arg-type]
            await cast(Any, close_result)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True, help="Wallbox IP address")
    parser.add_argument("--port", type=int, default=502, help="Modbus TCP port")
    parser.add_argument("--unit", type=int, default=255, help="Modbus unit identifier")
    parser.add_argument(
        "--registers",
        type=parse_registers,
        default=None,
        help="Comma separated holding registers to read (default 1000,1001,1002,1004,1006)",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=5,
        help="Number of read cycles to execute",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=5.0,
        help="Delay between read cycles in seconds",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=3.0,
        help="Socket timeout in seconds",
    )
    parser.add_argument(
        "--keepalive",
        action="store_true",
        help="Write the life bit register after each read cycle",
    )
    return parser


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = build_parser()
    args = parser.parse_args()
    return asyncio.run(run_probe(args))


if __name__ == "__main__":
    raise SystemExit(main())
