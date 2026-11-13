"""Virtual Webasto Next wallbox simulator utilities."""

from .simulator import (
    FakeModbusException,
    Scenario,
    VirtualWallboxState,
    VirtualWallboxUnit,
    build_default_scenario,
    register_virtual_wallbox,
    registry,
)

try:  # pragma: no cover - optional dependency
    from .server import VirtualWallboxDataBlock, build_identity, build_server_context, serve_tcp
except ModuleNotFoundError:  # pragma: no cover - pymodbus missing
    _IMPORT_MESSAGE = (
        "virtual_wallbox.server requires the 'pymodbus' dependency. Install the project "
        "with the 'dev' extra or run: pip install 'pymodbus>=3.11.2,<3.12'"
    )

    def _raise_missing(*_args, **_kwargs):  # pragma: no cover - helper
        raise ModuleNotFoundError(_IMPORT_MESSAGE)

    VirtualWallboxDataBlock = None  # type: ignore[assignment]
    build_identity = _raise_missing  # type: ignore[assignment]
    build_server_context = _raise_missing  # type: ignore[assignment]
    serve_tcp = _raise_missing  # type: ignore[assignment]

__all__ = [
    "FakeModbusException",
    "Scenario",
    "VirtualWallboxDataBlock",
    "VirtualWallboxState",
    "VirtualWallboxUnit",
    "build_default_scenario",
    "build_identity",
    "build_server_context",
    "register_virtual_wallbox",
    "registry",
    "serve_tcp",
]
