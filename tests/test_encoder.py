"""Protocol-level tests for the Daikin IR encoder."""

from __future__ import annotations

from datetime import datetime, time

import pytest

from daikin_ir_encoder import (
    VARIANT_1FRAME,
    VARIANT_3FRAME,
    build,
    build_state_frame,
    encode_1frame,
    encode_3frame,
)
from daikin_ir_encoder._encoder import (
    _MARK,
    _SHORT_SPACE,
    _bits_lsb_first,
    _bits_to_timings,
    _build_clock_frame,
    _build_identity_frame,
    _preamble,
)


def _checksum(frame: bytes) -> int:
    return sum(frame[:18]) & 0xFF


def test_header_is_constant() -> None:
    assert build_state_frame()[:5] == bytes([0x11, 0xDA, 0x27, 0x00, 0x00])


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"mode": "heat", "temp": 24, "fan": "3"},
        {"powerful": True},
        {"variant": VARIANT_1FRAME},
    ],
)
def test_checksum_matches_sum_mod_256(kwargs: dict[str, object]) -> None:
    frame = build_state_frame(**kwargs)
    assert len(frame) == 19
    assert frame[18] == _checksum(frame)


def test_power_bit() -> None:
    assert build_state_frame(power=True)[5] & 0x01 == 0x01
    assert build_state_frame(power=False)[5] & 0x01 == 0x00


def test_mode_high_nibble() -> None:
    for mode, code in {"auto": 0x0, "dry": 0x2, "cool": 0x3, "heat": 0x4, "fan": 0x6}.items():
        assert (build_state_frame(mode=mode)[5] >> 4) == code


def test_dry_mode_uses_no_temp_marker() -> None:
    assert build_state_frame(mode="dry", temp=21)[6] == 0xC0


def test_powerful_clears_mutually_exclusive_flags() -> None:
    # Captures U/V (2026-06-07) proved: powerful clears econo + outdoor_quiet +
    # comfort, sets the powerful bit itself, and PRESERVES intelligent_eye.
    frame = build_state_frame(
        powerful=True,
        econo=True,
        outdoor_quiet=True,
        intelligent_eye=True,
        fan="comfort",
    )
    assert frame[13] & 0x01 == 0x01  # powerful set
    assert frame[13] & 0x20 == 0x00  # outdoor-quiet cleared
    assert frame[16] & 0x04 == 0x00  # econo cleared
    assert frame[16] & 0x02 == 0x02  # IE preserved (not cleared)


def test_variant_specific_bytes() -> None:
    f3 = build_state_frame(variant=VARIANT_3FRAME)
    f1 = build_state_frame(variant=VARIANT_1FRAME)
    assert f3[5] & 0x08 == 0x08
    assert f1[5] & 0x08 == 0x00
    assert f3[11:13] == bytes([0x06, 0x60])
    assert f1[11:13] == bytes([0x00, 0x00])
    assert f3[15] == 0xC1
    assert f1[15] == 0xC5


def test_3frame_edge_count() -> None:
    """preamble(11) + 3·(gap+leader(3) + data + stop_MARK(1)) + terminating_SPACE(1) = 584."""
    assert len(encode_3frame(build_state_frame(variant=VARIANT_3FRAME))) == 584


def test_1frame_edge_count() -> None:
    """preamble(11) + pre-leader+leader(3) + 19B·8b·2(304) + stop_MARK(1) + terminating_SPACE(1) = 320."""
    assert len(encode_1frame(build_state_frame(variant=VARIANT_1FRAME))) == 320


@pytest.mark.parametrize(
    ("variant", "expected_edges"),
    [(VARIANT_3FRAME, 584), (VARIANT_1FRAME, 320)],
)
def test_build_returns_timings(variant: str, expected_edges: int) -> None:
    timings = build(mode="cool", temp=21, fan="auto", variant=variant)
    assert len(timings) == expected_edges
    assert all(isinstance(t, int) and t != 0 for t in timings)


@pytest.mark.parametrize("temp", [18, 21, 24, 30])
def test_temperature_is_celsius_times_two(temp: int) -> None:
    assert build_state_frame(mode="cool", temp=temp)[6] == temp * 2


def test_fan_speed_high_nibble() -> None:
    expected = {"1": 0x3, "2": 0x4, "3": 0x5, "4": 0x6, "5": 0x7,
                "auto": 0xA, "night": 0xB, "comfort": 0xA}
    for fan, code in expected.items():
        assert (build_state_frame(fan=fan)[8] >> 4) == code


def test_v_swing_bits() -> None:
    assert build_state_frame(v_swing=True)[8] & 0x0F == 0x0F
    assert build_state_frame(v_swing=False)[8] & 0x0F == 0x00


def test_h_swing_bits() -> None:
    assert build_state_frame(h_swing=True)[9] & 0x0F == 0x0F
    assert build_state_frame(h_swing=False)[9] & 0x0F == 0x00


def test_econo_bit() -> None:
    assert build_state_frame(econo=True)[16] & 0x04 == 0x04
    assert build_state_frame(econo=False)[16] & 0x04 == 0x00


def test_outdoor_quiet_bit() -> None:
    assert build_state_frame(outdoor_quiet=True)[13] & 0x20 == 0x20
    assert build_state_frame(outdoor_quiet=False)[13] & 0x20 == 0x00


def test_intelligent_eye_bit() -> None:
    assert build_state_frame(intelligent_eye=True)[16] & 0x02 == 0x02
    assert build_state_frame(intelligent_eye=False)[16] & 0x02 == 0x00


def test_powerful_bit() -> None:
    assert build_state_frame(powerful=True)[13] & 0x01 == 0x01
    assert build_state_frame(powerful=False)[13] & 0x01 == 0x00


def test_bits_lsb_first() -> None:
    assert _bits_lsb_first(bytes([0x01])) == [1, 0, 0, 0, 0, 0, 0, 0]
    assert _bits_lsb_first(bytes([0x80])) == [0, 0, 0, 0, 0, 0, 0, 1]
    assert _bits_lsb_first(bytes([0x11])) == [1, 0, 0, 0, 1, 0, 0, 0]


def test_preamble_shape() -> None:
    assert _preamble() == [_MARK, _SHORT_SPACE] * 5 + [_MARK]


def test_3frame_carries_identity_frames_and_state() -> None:
    state = build_state_frame(variant=VARIANT_3FRAME)
    dt = datetime(2026, 6, 7, 13, 50)
    timings = encode_3frame(state, dt=dt)
    # Layout: preamble(11) + [gap, leader_mark, leader_space, bits..., stop_MARK] per frame.
    # FRAME1 bits at 14:142, FRAME2 bits at 146:274, state bits at 278:582.
    assert timings[14:142] == _bits_to_timings(_bits_lsb_first(_build_identity_frame()))
    assert timings[146:274] == _bits_to_timings(_bits_lsb_first(_build_clock_frame(dt)))
    assert timings[278:582] == _bits_to_timings(_bits_lsb_first(state))


def test_golden_frame_3frame_cool_21_auto() -> None:
    expected = bytes([
        0x11, 0xDA, 0x27, 0x00, 0x00,
        0x39, 0x2A, 0x00, 0xA0, 0x00, 0x00,
        0x06, 0x60, 0x00, 0x00,
        0xC1, 0x80, 0x00, 0xBC,
    ])
    assert build_state_frame(
        power=True, mode="cool", temp=21, fan="auto", variant=VARIANT_3FRAME,
    ) == expected


def test_golden_frame_1frame_cool_21_auto() -> None:
    expected = bytes([
        0x11, 0xDA, 0x27, 0x00, 0x00,
        0x31, 0x2A, 0x00, 0xA0, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00,
        0xC5, 0x00, 0x00, 0xD2,
    ])
    assert build_state_frame(
        power=True, mode="cool", temp=21, fan="auto", variant=VARIANT_1FRAME,
    ) == expected


def test_frame2_default_uses_current_wall_clock() -> None:
    # _build_clock_frame(None) should resolve to ~now. Verify the encoded minutes
    # are within 2 of the current wall clock (allows for a midnight rollover
    # or scheduler hiccup mid-test without false flakes).
    from datetime import datetime as _dt
    before_minutes = _dt.now().hour * 60 + _dt.now().minute
    frame = _build_clock_frame(None)
    after_minutes = _dt.now().hour * 60 + _dt.now().minute
    encoded = frame[5] | ((frame[6] & 0x07) << 8)
    # Encoded value must be within the [before, after] window (handle rollover).
    if before_minutes <= after_minutes:
        assert before_minutes <= encoded <= after_minutes
    else:  # midnight rollover during the test
        assert encoded >= before_minutes or encoded <= after_minutes


def test_frame2_captured_sunday_1350() -> None:
    # Captured 2026-06-07 with remote set to Sunday 13:50.
    dt = datetime(2026, 6, 7, 13, 50)  # 2026-06-07 is a Sunday
    assert _build_clock_frame(dt) == bytes([0x11, 0xDA, 0x27, 0x00, 0x42, 0x3E, 0x0B, 0x9D])


def test_frame2_captured_friday_1134() -> None:
    # Captured 2026-06-07 with remote set to Friday 11:34.
    dt = datetime(2026, 6, 5, 11, 34)  # 2026-06-05 is a Friday
    assert _build_clock_frame(dt) == bytes([0x11, 0xDA, 0x27, 0x00, 0x42, 0xB6, 0x32, 0x3C])


@pytest.mark.parametrize(
    ("date", "expected_day_code"),
    [
        (datetime(2026, 6, 7, 0, 0), 1),   # Sunday
        (datetime(2026, 6, 1, 0, 0), 2),   # Monday
        (datetime(2026, 6, 2, 0, 0), 3),   # Tuesday
        (datetime(2026, 6, 3, 0, 0), 4),   # Wednesday
        (datetime(2026, 6, 4, 0, 0), 5),   # Thursday
        (datetime(2026, 6, 5, 0, 0), 6),   # Friday
        (datetime(2026, 6, 6, 0, 0), 7),   # Saturday
    ],
)
def test_frame2_day_of_week_encoding(date: datetime, expected_day_code: int) -> None:
    frame = _build_clock_frame(date)
    assert (frame[6] >> 3) == expected_day_code


def test_frame2_encodes_full_minutes_range() -> None:
    last = datetime(2026, 6, 1, 23, 59)  # 1439 min since midnight
    frame = _build_clock_frame(last)
    minutes = frame[5] | ((frame[6] & 0x07) << 8)
    assert minutes == 1439


def test_frame2_checksum_holds() -> None:
    dt = datetime(2026, 6, 7, 13, 50)
    frame = _build_clock_frame(dt)
    assert frame[7] == sum(frame[:7]) & 0xFF


def test_encode_3frame_dt_threads_through() -> None:
    state = build_state_frame(variant=VARIANT_3FRAME)
    dt = datetime(2026, 6, 5, 11, 34)
    timings = encode_3frame(state, dt=dt)
    expected_frame2_bits = _bits_to_timings(_bits_lsb_first(_build_clock_frame(dt)))
    assert timings[146:274] == expected_frame2_bits


def test_build_dt_passes_to_3frame_only() -> None:
    dt = datetime(2026, 6, 5, 11, 34)
    timings_3 = build(variant=VARIANT_3FRAME, dt=dt)
    timings_1 = build(variant=VARIANT_1FRAME, dt=dt)  # dt ignored on 1-frame
    # 3-frame includes the dt-encoded frame 2
    assert timings_3[146:274] == _bits_to_timings(_bits_lsb_first(_build_clock_frame(dt)))
    # 1-frame is unaffected by dt — equals the dt-less build
    assert timings_1 == build(variant=VARIANT_1FRAME)


def test_timer_disabled_default_3frame() -> None:
    # No timer args → variant default bytes preserved (regression for clock+timer
    # change not breaking the legacy "00 06 60" baseline).
    frame = build_state_frame(variant=VARIANT_3FRAME)
    assert frame[10:13] == bytes([0x00, 0x06, 0x60])
    assert frame[5] & 0x06 == 0x00  # both timer-enable bits clear


def test_timer_disabled_default_1frame() -> None:
    frame = build_state_frame(variant=VARIANT_1FRAME)
    assert frame[10:13] == bytes([0x00, 0x00, 0x00])
    assert frame[5] & 0x06 == 0x00


def test_on_timer_only_matches_capture_J() -> None:
    # Capture J (2026-06-07): power-on, mode=auto, on-timer=15:10, no off-timer.
    frame = build_state_frame(
        power=True, mode="auto", fan="auto",
        on_timer=time(15, 10), variant=VARIANT_3FRAME,
    )
    assert frame[5] == 0x0B  # bits: id=1, on-tmr-en=1, off-tmr-en=0, power=1
    assert frame[10:13] == bytes([0x8E, 0x03, 0x60])  # ON=910, OFF=disabled


def test_off_timer_only() -> None:
    frame = build_state_frame(
        power=True, mode="auto", fan="auto",
        off_timer=time(21, 50), variant=VARIANT_3FRAME,
    )
    assert frame[5] == 0x0D  # off-tmr-en=1, on-tmr-en=0, power=1, id=1
    # OFF=1310=0x51E → byte12=0x51, byte11 high nibble=0xE; ON unset → low nibble=0x6, byte10=0
    assert frame[10:13] == bytes([0x00, 0xE6, 0x51])


def test_both_timers_matches_capture_K() -> None:
    # Capture K: power-on, mode=auto, on-timer=15:10, off-timer=21:50.
    frame = build_state_frame(
        power=True, mode="auto", fan="auto",
        on_timer=time(15, 10), off_timer=time(21, 50),
        variant=VARIANT_3FRAME,
    )
    assert frame[5] == 0x0F  # both timer enables set, power, id
    assert frame[10:13] == bytes([0x8E, 0xE3, 0x51])


def test_timer_threads_through_build() -> None:
    timings = build(
        mode="auto", fan="auto",
        on_timer=time(15, 10), off_timer=time(21, 50),
        variant=VARIANT_3FRAME,
    )
    # State frame begins at index 278 of the 584-edge 3-frame timing stream.
    expected_state = build_state_frame(
        mode="auto", fan="auto",
        on_timer=time(15, 10), off_timer=time(21, 50),
        variant=VARIANT_3FRAME,
    )
    assert timings[278:582] == _bits_to_timings(_bits_lsb_first(expected_state))


def test_timer_midnight_boundary() -> None:
    # 00:00 is a valid time-of-day — should encode as 0, distinct from disabled (0x600).
    frame = build_state_frame(
        on_timer=time(0, 0), variant=VARIANT_3FRAME,
    )
    assert frame[5] & 0x02 == 0x02  # on-tmr-en
    on_min = ((frame[11] & 0x0F) << 8) | frame[10]
    assert on_min == 0


def test_timer_last_minute_of_day() -> None:
    frame = build_state_frame(
        on_timer=time(23, 59), variant=VARIANT_3FRAME,
    )
    on_min = ((frame[11] & 0x0F) << 8) | frame[10]
    assert on_min == 23 * 60 + 59  # 1439


def test_identity_frame_default_no_comfort() -> None:
    # Same bytes as the legacy hard-coded _FRAME1.
    assert _build_identity_frame() == bytes([0x11, 0xDA, 0x27, 0x00, 0xC5, 0x10, 0x00, 0xE7])


def test_identity_frame_comfort_bit_set() -> None:
    # Capture S confirmed byte 6 bit 4 = 0x10 when comfort enabled. The
    # captured S frame 0 byte 5 was 0x20 (battery-state thing); the encoder
    # emits 0x10 for byte 5, but the comfort bit + checksum logic match.
    frame = _build_identity_frame(comfort=True)
    assert frame[6] == 0x10
    assert frame[7] == sum(frame[:7]) & 0xFF


def test_build_comfort_sets_identity_bit() -> None:
    # fan="comfort" must result in the identity frame's comfort bit set.
    timings = build(mode="cool", temp=21, fan="comfort", variant=VARIANT_3FRAME,
                    dt=datetime(2026, 6, 7, 13, 50))
    expected_identity = _bits_to_timings(_bits_lsb_first(_build_identity_frame(comfort=True)))
    assert timings[14:142] == expected_identity


def test_build_powerful_overrides_comfort_so_identity_bit_clears() -> None:
    # powerful=True downgrades fan="comfort" to fan="auto"; the comfort bit
    # in the identity frame must therefore NOT be set.
    timings = build(mode="cool", temp=21, fan="comfort", powerful=True,
                    variant=VARIANT_3FRAME, dt=datetime(2026, 6, 7, 13, 50))
    expected_identity = _bits_to_timings(_bits_lsb_first(_build_identity_frame(comfort=False)))
    assert timings[14:142] == expected_identity


def test_weekly_active_default_is_disabled_3frame() -> None:
    # Default: weekly_active=False → bit 7 of byte 16 is set (= disabled).
    frame = build_state_frame(variant=VARIANT_3FRAME)
    assert frame[16] & 0x80 == 0x80


def test_weekly_active_true_clears_disable_bit_3frame() -> None:
    frame = build_state_frame(weekly_active=True, variant=VARIANT_3FRAME)
    assert frame[16] & 0x80 == 0x00


def test_weekly_active_ignored_on_1frame() -> None:
    # ARC480A11 has no weekly feature — the bit stays 0 regardless.
    frame_off = build_state_frame(weekly_active=False, variant=VARIANT_1FRAME)
    frame_on  = build_state_frame(weekly_active=True,  variant=VARIANT_1FRAME)
    assert frame_off[16] & 0x80 == 0x00
    assert frame_on[16]  & 0x80 == 0x00


def test_1frame_off_timer_matches_capture_M() -> None:
    # Capture M (ARC480A11): power-on, mode=auto, intelligent_eye=True,
    # off-timer = 1 hour duration. Byte packing is identical to 3-frame;
    # the AC interprets the integer as a duration (not time-of-day) because
    # ARC480A11 has no clock.
    frame = build_state_frame(
        power=True, mode="auto", fan="auto",
        intelligent_eye=True,
        off_timer=time(1, 0),  # 60 min: encoded value is the same whether read as ToD or duration
        variant=VARIANT_1FRAME,
    )
    assert frame[5] == 0x05   # power=1, off-tmr-en=1, id=0 (ARC480A11), mode=auto
    assert frame[10:13] == bytes([0x00, 0xC0, 0x03])  # OFF = (0x03 << 4) | 0xC = 0x3C = 60
    assert frame == bytes([
        0x11, 0xDA, 0x27, 0x00, 0x00,
        0x05, 0x2A, 0x00, 0xA0, 0x00,
        0x00, 0xC0, 0x03, 0x00, 0x00,
        0xC5, 0x02, 0x00, 0x6B,
    ])
