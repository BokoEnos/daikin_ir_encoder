"""Synthesize Daikin AC IR frames from scratch.

Public API:
    build(...)                  one-shot helper returning raw timings
    build_state_frame(...)      19-byte protocol frame
    encode_3frame(frame)        wraps a frame in the 3-frame transport
    encode_1frame(frame)        wraps a frame in the 1-frame transport
    VARIANT_3FRAME / VARIANT_1FRAME / VARIANTS
    MODES, FAN_SPEEDS, TEMP_RANGES
    MODE_AUTO, MODE_DRY, MODE_COOL, MODE_HEAT, MODE_FAN
    CARRIER_HZ
"""

from ._constants import (
    CARRIER_HZ,
    FAN_SPEEDS,
    MODE_AUTO,
    MODE_COOL,
    MODE_DRY,
    MODE_FAN,
    MODE_HEAT,
    MODES,
    TEMP_RANGES,
    VARIANT_1FRAME,
    VARIANT_3FRAME,
    VARIANTS,
)
from ._encoder import (
    build,
    build_state_frame,
    encode_1frame,
    encode_3frame,
)

__version__ = "0.1.0"

__all__ = [
    "CARRIER_HZ",
    "FAN_SPEEDS",
    "MODE_AUTO",
    "MODE_COOL",
    "MODE_DRY",
    "MODE_FAN",
    "MODE_HEAT",
    "MODES",
    "TEMP_RANGES",
    "VARIANT_1FRAME",
    "VARIANT_3FRAME",
    "VARIANTS",
    "build",
    "build_state_frame",
    "encode_1frame",
    "encode_3frame",
    "__version__",
]
