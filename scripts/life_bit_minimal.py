#!/usr/bin/env python3
"""
Minimal script to test Webasto Next Modbus "Life Bit" (Keepalive).

This script attempts to write to the keepalive register (6000) and read the
failsafe timeout register (2002) to verify communication.
"""

import asyncio
import argparse
import inspect
import logging

from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S"
)
_LOGGER = logging.getLogger("life_bit_minimal")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Webasto Next Modbus keepalive (life bit) minimal test")
    parser.add_argument("host", nargs="?", default="192.168.178.109")
    parser.add_argument("--port", type=int, default=502)
    parser.add_argument("--device-id", type=int, default=255, dest="device_id")
    parser.add_argument("--keepalive-reg", type=int, default=6000, dest="keepalive_reg")
    parser.add_argument("--failsafe-reg", type=int, default=2002, dest="failsafe_reg")
    parser.add_argument("--interval", type=float, default=5.0, help="Seconds between keepalive writes")
    parser.add_argument("--cycles", type=int, default=30, help="Number of keepalive cycles to run")
    parser.add_argument("--timeout", type=float, default=3.0, help="Modbus TCP socket timeout")
    parser.add_argument(
        "--reconnect-delay",
        type=float,
        default=2.0,
        dest="reconnect_delay",
        help="Seconds to wait before reconnecting after an error",
    )
    return parser.parse_args()


async def _maybe_close(client: AsyncModbusTcpClient) -> None:
    close_result = client.close()
    if inspect.isawaitable(close_result):
        await close_result


async def run() -> int:
    """Run a keepalive loop with reconnects.

    pymodbus 3.11+ uses `device_id` (not `unit`).
    """

    args = _parse_args()
    _LOGGER.info(
        "Target %s:%s (device_id=%s), keepalive_reg=%s, failsafe_reg=%s",
        args.host,
        args.port,
        args.device_id,
        args.keepalive_reg,
        args.failsafe_reg,
    )

    keepalive_value = 0
    successful_writes = 0
    cycle = 0

    client = AsyncModbusTcpClient(args.host, port=args.port, timeout=args.timeout)
    try:
        while cycle < args.cycles:
            try:
                if not getattr(client, "connected", False):
                    _LOGGER.info("Connecting...")
                    await client.connect()
                    if not client.connected:
                        raise ConnectionError("connect() returned not connected")

                    rr = await client.read_holding_registers(
                        args.failsafe_reg,
                        count=1,
                        device_id=args.device_id,
                    )
                    if rr.isError():
                        _LOGGER.warning("Failsafe read error: %r", rr)
                    else:
                        _LOGGER.info("Failsafe Timeout: %s s", rr.registers[0])

                keepalive_value = 1 - keepalive_value
                wr = await client.write_register(
                    args.keepalive_reg,
                    keepalive_value,
                    device_id=args.device_id,
                )
                if wr.isError():
                    raise ModbusException(f"write_register error: {wr!r}")

                successful_writes += 1
                cycle += 1
                _LOGGER.info(
                    "Keepalive write ok (%s/%s): wrote %s",
                    cycle,
                    args.cycles,
                    keepalive_value,
                )
                await asyncio.sleep(args.interval)

            except (ConnectionError, OSError, ModbusException) as exc:
                _LOGGER.error("Communication error: %s", exc)
                await _maybe_close(client)
                await asyncio.sleep(args.reconnect_delay)

    finally:
        _LOGGER.info("Closing connection...")
        await _maybe_close(client)

    _LOGGER.info("Done. Successful keepalive writes: %s", successful_writes)
    return 0 if successful_writes else 2

if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(run()))
    except KeyboardInterrupt:
        raise SystemExit(130)
