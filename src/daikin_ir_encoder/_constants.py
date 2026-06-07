"""Protocol-level constants for Daikin AC IR frames."""

from __future__ import annotations

CARRIER_HZ = 38000

VARIANT_3FRAME = "3frame"
VARIANT_1FRAME = "1frame"
VARIANTS: tuple[str, ...] = (VARIANT_3FRAME, VARIANT_1FRAME)

MODE_AUTO = "auto"
MODE_DRY = "dry"
MODE_COOL = "cool"
MODE_HEAT = "heat"
MODE_FAN = "fan"

MODES: dict[str, int] = {
    MODE_AUTO: 0x0,
    MODE_DRY: 0x2,
    MODE_COOL: 0x3,
    MODE_HEAT: 0x4,
    MODE_FAN: 0x6,
}

FAN_SPEEDS: dict[str, int] = {
    "1": 0x3,
    "2": 0x4,
    "3": 0x5,
    "4": 0x6,
    "5": 0x7,
    "auto": 0xA,
    "night": 0xB,
    "comfort": 0xA,
}

# Per-mode valid temperature ranges, °C.
# DRY and FAN have no controllable temperature.
TEMP_RANGES: dict[str, tuple[int, int]] = {
    MODE_COOL: (18, 32),
    MODE_HEAT: (10, 30),
    MODE_AUTO: (18, 30),
}
