"""Expose the virtual wallbox state via a Modbus TCP server."""

from __future__ import annotations

import logging
from collections.abc import Iterable

from pymodbus.datastore import (
    ModbusDeviceContext,
    ModbusServerContext,
    ModbusSparseDataBlock,
)
from pymodbus.pdu.device import ModbusDeviceIdentification
from pymodbus.server import StartAsyncTcpServer

from custom_components.webasto_next_modbus.const import REGISTER_TYPE

from .simulator import VirtualWallboxState

_LOGGER = logging.getLogger(__name__)


class VirtualWallboxDataBlock(ModbusSparseDataBlock):
    """Modbus data block backed by :class:`VirtualWallboxState`."""

    def __init__(
        self,
        state: VirtualWallboxState,
        register_type: REGISTER_TYPE,
        *,
        zero_mode: bool,
    ) -> None:
        super().__init__({})
        self._state = state
        self._register_type = register_type
        self._zero_mode = zero_mode

    def validate(self, address: int, count: int = 1) -> bool:  # noqa: N802 - pymodbus API
        """Always allow the request; out-of-range addresses yield zeroed values."""

        return count >= 0

    def getValues(self, address: int, count: int = 1) -> list[int]:  # noqa: N802 - pymodbus API
        """Return a contiguous block of register values."""

        start = self._normalize_address(address)
        values = self._state.read_block(self._register_type, start, count)
        return list(values)

    def setValues(  # noqa: N802 - pymodbus API
        self,
        address: int,
        values: Iterable[int],
        use_as_default: bool = False,
    ) -> None:
        """Persist holding register writes back into the virtual wallbox state."""

        if self._register_type != "holding":
            return

        start = self._normalize_address(address)
        for offset, value in enumerate(list(values)):
            self._state.write_register(start + offset, int(value))

    def _normalize_address(self, address: int) -> int:
        """Resolve Modbus context offsets based on zero-mode configuration."""

        if self._zero_mode:
            return address
        return address + 1


class VirtualWallboxDeviceContext(ModbusDeviceContext):
    """Device context that preserves legacy zero-mode behaviour."""

    def __init__(
        self,
        *,
        zero_mode: bool,
        input_block: ModbusSparseDataBlock,
        holding_block: ModbusSparseDataBlock,
    ) -> None:
        super().__init__(
            di=ModbusSparseDataBlock({}),
            co=ModbusSparseDataBlock({}),
            ir=input_block,
            hr=holding_block,
        )

    def getValues(self, func_code, address, count=1):  # type: ignore[override]
        block = self.store[self.decode(func_code)]
        return block.getValues(address, count)

    def setValues(self, func_code, address, values):  # type: ignore[override]
        block = self.store[self.decode(func_code)]
        return block.setValues(address, values)

    def validate(self, func_code, address, count=1):  # type: ignore[override]
        block = self.store[self.decode(func_code)]
        if hasattr(block, "validate"):
            return block.validate(address, count)
        return True


def build_server_context(
    state: VirtualWallboxState,
    *,
    zero_mode: bool = False,
) -> ModbusServerContext:
    """Create a Modbus server context exposing the virtual wallbox state."""

    input_block = VirtualWallboxDataBlock(state, "input", zero_mode=zero_mode)
    holding_block = VirtualWallboxDataBlock(state, "holding", zero_mode=zero_mode)
    device = VirtualWallboxDeviceContext(
        zero_mode=zero_mode,
        input_block=input_block,
        holding_block=holding_block,
    )
    return ModbusServerContext(devices=device, single=True)


def build_identity() -> ModbusDeviceIdentification:
    """Return a basic Modbus device identification block for the simulator."""

    identity = ModbusDeviceIdentification()
    identity.VendorName = "Webasto Next"
    identity.ProductCode = "WALLBOX"
    identity.ProductName = "Virtual Webasto Next"
    identity.MajorMinorRevision = "0.1"
    return identity


async def serve_tcp(
    state: VirtualWallboxState,
    *,
    host: str = "127.0.0.1",
    port: int = 15020,
    zero_mode: bool = False,
) -> None:
    """Run an asynchronous Modbus TCP server until cancelled."""

    context = build_server_context(state, zero_mode=zero_mode)
    identity = build_identity()
    _LOGGER.info("Starting virtual wallbox on %s:%s (unit %s)", host, port, state.unit_id)
    await StartAsyncTcpServer(context=context, identity=identity, address=(host, port))