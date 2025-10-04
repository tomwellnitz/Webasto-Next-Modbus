"""Virtual Webasto Next wallbox simulator utilities."""

from .server import VirtualWallboxDataBlock, build_identity, build_server_context, serve_tcp
from .simulator import (
    FakeAsyncModbusTcpClient,
    FakeModbusException,
    Scenario,
    VirtualWallboxState,
    build_default_scenario,
    register_virtual_wallbox,
    registry,
)

__all__ = [
    "FakeAsyncModbusTcpClient",
    "FakeModbusException",
    "Scenario",
    "VirtualWallboxState",
    "VirtualWallboxDataBlock",
    "build_default_scenario",
    "build_identity",
    "build_server_context",
    "register_virtual_wallbox",
    "registry",
    "serve_tcp",
]
