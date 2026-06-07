"""Daikin AC IR frame encoder.

Synthesizes a 19-byte Daikin state frame and wraps it in raw IR timings playable
by any 38 kHz IR transmitter. Supports both the 3-frame and 1-frame transports;
both use the same byte-level layout and checksum.
"""

from __future__ import annotations

from datetime import datetime, time

from ._constants import (
    FAN_SPEEDS,
    MODE_DRY,
    MODES,
    VARIANT_1FRAME,
    VARIANT_3FRAME,
)

# Timing constants (microseconds; negative = space)
_MARK = 454
_SHORT_SPACE = -413  # bit 0
_LONG_SPACE = -1280  # bit 1
_LEADER_MARK = 3500
_LEADER_SPACE = -1700
_PRE_LEADER_GAP = -25000
_INTER_FRAME_GAP = -35000
_TRAILING_GAP = -30000

# Invalid time-of-day (25h36) used as the timer "off" sentinel on ARC466A9.
_TIMER_DISABLED = 0x600


def _bits_lsb_first(data: bytes) -> list[int]:
    return [(byte >> b) & 1 for byte in data for b in range(8)]


def _bits_to_timings(bits: list[int]) -> list[int]:
    out: list[int] = []
    for bit in bits:
        out.append(_MARK)
        out.append(_LONG_SPACE if bit else _SHORT_SPACE)
    return out


def _preamble() -> list[int]:
    # 5 short pulse pairs followed by a trailing mark — confirmed by direct
    # capture inspection. Without the trailing mark the AC ignores the frame.
    return [_MARK, _SHORT_SPACE] * 5 + [_MARK]


def _build_identity_frame(comfort: bool = False) -> bytes:
    """Build the 8-byte identity frame (frame 0 of the 3-frame transport).

    Layout:
        bytes 0–4: ``11 DA 27 00 C5`` (constant)
        byte 5:    ``0x10`` (purpose undecoded; live remotes also emit ``0x20`` —
                   correlated with battery state, not with any user setting)
        byte 6 bit 4: comfort-mode indicator. The AC cannot otherwise
                   distinguish ``fan=comfort`` from ``fan=auto`` + V-swing off
                   (state-frame byte 8 is identical for both).
        byte 7:    ``sum(bytes[:7]) & 0xFF``
    """
    bs = bytearray([0x11, 0xDA, 0x27, 0x00, 0xC5, 0x10, 0x10 if comfort else 0x00, 0])
    bs[7] = sum(bs[:7]) & 0xFF
    return bytes(bs)


def _build_clock_frame(dt: datetime | None) -> bytes:
    """Build the 8-byte frame 2 carrying the remote's wall clock.

    Layout:
        bytes 0–4: ``11 DA 27 00 42`` (constant)
        byte 5:    ``minutes_since_midnight & 0xFF``
        byte 6:    ``(day_of_week << 3) | (minutes_since_midnight >> 8)``
                   day_of_week protocol values: Sun=1, Mon=2, … Sat=7
        byte 7:    ``sum(bytes[:7]) & 0xFF``

    ``dt`` defaults to ``datetime.now()`` so on-air frames carry a live clock.
    Pass an explicit ``datetime`` for deterministic output.
    """
    effective_dt = dt if dt is not None else datetime.now()
    minutes = effective_dt.hour * 60 + effective_dt.minute
    # datetime.weekday(): Mon=0..Sun=6  →  protocol Sun=1..Sat=7
    day = ((effective_dt.weekday() + 1) % 7) + 1
    bs = bytearray([0x11, 0xDA, 0x27, 0x00, 0x42, 0, 0, 0])
    bs[5] = minutes & 0xFF
    bs[6] = (day << 3) | (minutes >> 8)
    bs[7] = sum(bs[:7]) & 0xFF
    return bytes(bs)


def build_state_frame(
    *,
    power: bool = True,
    mode: str = "cool",
    temp: int = 21,
    fan: str = "auto",
    v_swing: bool = False,
    h_swing: bool = False,
    intelligent_eye: bool = False,
    econo: bool = False,
    outdoor_quiet: bool = False,
    powerful: bool = False,
    on_timer: time | None = None,
    off_timer: time | None = None,
    weekly_active: bool = False,
    variant: str = VARIANT_3FRAME,
) -> bytes:
    """Build the 19-byte Daikin state frame.

    Applies the mutual-exclusion rules the AC itself enforces — ``powerful``
    auto-disables econo / outdoor_quiet and downgrades comfort fan to plain
    auto. ``intelligent_eye`` is preserved (the real remote keeps it on
    when powerful is pressed; verified by capture).

    ``on_timer`` / ``off_timer`` are wall-clock times-of-day. When provided,
    they pack into bytes 10–12 (11-bit minutes-since-midnight each, sharing
    byte 11) and the corresponding enable bit in byte 5 is set.
    """
    mode_lc = mode.lower()
    fan_lc = str(fan).lower()
    is_3frame = variant == VARIANT_3FRAME

    if powerful:
        econo = False
        outdoor_quiet = False
        if FAN_SPEEDS.get(fan_lc, 0) == 0xA:
            fan_lc = "auto"

    # Timer packing: 11-bit minutes per timer, sharing byte 11.
    #   ON  minutes = ((byte11 & 0x0F) << 8) | byte10
    #   OFF minutes = (byte12 << 4) | (byte11 >> 4)
    # Integer is minutes-since-midnight on 3-frame (clocked remote) and
    # minutes-of-duration on 1-frame (clockless remote). The "disabled"
    # sentinel is 0x600 (=25h36, invalid wall-time) on 3-frame and 0x000 on
    # 1-frame.
    disabled = _TIMER_DISABLED if is_3frame else 0x000
    on_min = on_timer.hour * 60 + on_timer.minute if on_timer is not None else disabled
    off_min = off_timer.hour * 60 + off_timer.minute if off_timer is not None else disabled

    bs = bytearray(19)

    # Bytes 0–4: constant header.
    bs[0:5] = bytes([0x11, 0xDA, 0x27, 0x00, 0x00])

    # Byte 5: mode (4–7) | variant id (3) | off-tmr-en (2) | on-tmr-en (1) | power (0)
    bs[5] = (
        (MODES[mode_lc] << 4)
        | (0x08 if is_3frame else 0x00)
        | (0x04 if off_timer is not None else 0x00)
        | (0x02 if on_timer is not None else 0x00)
        | (0x01 if power else 0x00)
    )

    # Byte 6: temp × 2, or 0xC0 marker for dry mode.
    bs[6] = 0xC0 if mode_lc == MODE_DRY else (temp * 2)

    # Byte 8: fan high nibble | V-swing low nibble.
    bs[8] = (FAN_SPEEDS[fan_lc] << 4) | (0xF if v_swing else 0x0)

    # Byte 9: H-swing low nibble.
    bs[9] = 0xF if h_swing else 0x0

    # Bytes 10–12: packed ON-timer and OFF-timer.
    bs[10] = on_min & 0xFF
    bs[11] = ((off_min & 0x0F) << 4) | (on_min >> 8)
    bs[12] = off_min >> 4

    # Byte 13: powerful (bit 0) | outdoor-quiet (bit 5).
    bs[13] = (0x01 if powerful else 0x00) | (0x20 if outdoor_quiet else 0x00)

    # Byte 15: remote-ID region (meaning undecoded; differs between variants).
    bs[15] = 0xC1 if is_3frame else 0xC5

    # Byte 16: weekly-disable (bit 7) | econo (bit 2) | IE (bit 1).
    # Bit 7 = "weekly timer disabled" on ARC466A9. The weekly schedule itself
    # is programmed via a separate command not supported by this library;
    # weekly_active=True tells the AC to use a previously-programmed schedule
    # rather than the state in this frame. ARC480A11 has no weekly feature —
    # the bit is unused there and weekly_active is ignored.
    weekly_disable_bit = 0x80 if (is_3frame and not weekly_active) else 0x00
    bs[16] = (
        weekly_disable_bit
        | (0x04 if econo else 0x00)
        | (0x02 if intelligent_eye else 0x00)
    )

    # Byte 18: checksum (sum of all preceding bytes, mod 256).
    bs[18] = sum(bs[:18]) & 0xFF
    return bytes(bs)


def encode_3frame(
    state_frame: bytes,
    *,
    dt: datetime | None = None,
    comfort: bool = False,
) -> list[int]:
    """3-frame transport: preamble + identity + clock(dt) + state_frame.

    ``dt`` populates the clock bytes inside the clock frame and defaults to
    ``datetime.now()``; pass an explicit ``datetime`` for deterministic output.

    ``comfort`` sets the comfort-mode indicator in the identity frame. The AC
    cannot otherwise distinguish ``fan=comfort`` from ``fan=auto`` + V-swing
    off — the state frame is identical for both. ``build()`` derives this
    automatically from the ``fan`` argument.

    Each frame's data bits are followed by a stop MARK that terminates the
    last bit's space before the inter-frame gap, otherwise the receiver sees
    one merged off-period and rejects the frame.
    """
    out = _preamble()
    for frame, gap in (
        (_build_identity_frame(comfort), _PRE_LEADER_GAP),
        (_build_clock_frame(dt), _INTER_FRAME_GAP),
        (state_frame, _INTER_FRAME_GAP),
    ):
        out.extend([gap, _LEADER_MARK, _LEADER_SPACE])
        out.extend(_bits_to_timings(_bits_lsb_first(frame)))
        out.append(_MARK)
    out.append(_TRAILING_GAP)
    return out


def encode_1frame(state_frame: bytes) -> list[int]:
    """1-frame transport: preamble + state_frame + stop mark + terminating gap."""
    out = _preamble()
    out.extend([_PRE_LEADER_GAP, _LEADER_MARK, _LEADER_SPACE])
    out.extend(_bits_to_timings(_bits_lsb_first(state_frame)))
    out.append(_MARK)
    out.append(_TRAILING_GAP)
    return out


def build(
    *,
    power: bool = True,
    mode: str = "cool",
    temp: int = 21,
    fan: str = "auto",
    v_swing: bool = False,
    h_swing: bool = False,
    intelligent_eye: bool = False,
    econo: bool = False,
    outdoor_quiet: bool = False,
    powerful: bool = False,
    on_timer: time | None = None,
    off_timer: time | None = None,
    weekly_active: bool = False,
    variant: str = VARIANT_3FRAME,
    dt: datetime | None = None,
) -> list[int]:
    """One-shot helper: build a state frame and return its raw IR timings.

    ``dt`` only affects the 3-frame transport (frame 2 carries the clock).
    """
    state = build_state_frame(
        power=power,
        mode=mode,
        temp=temp,
        fan=fan,
        v_swing=v_swing,
        h_swing=h_swing,
        intelligent_eye=intelligent_eye,
        econo=econo,
        outdoor_quiet=outdoor_quiet,
        powerful=powerful,
        on_timer=on_timer,
        off_timer=off_timer,
        weekly_active=weekly_active,
        variant=variant,
    )
    if variant == VARIANT_3FRAME:
        comfort = str(fan).lower() == "comfort" and not powerful
        return encode_3frame(state, dt=dt, comfort=comfort)
    return encode_1frame(state)
