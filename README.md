# daikin-ir-encoder

Synthesizes Daikin air-conditioner IR command frames and returns raw mark/space
timings (microseconds, positive = mark, negative = space) playable by any 38 kHz
IR transmitter: Broadlink, XIAO IR Mate

Reverse-engineered from two Daikin remotes (ARC466A9 and ARC480A11). 
Both remotes use the same 19-byte state frame and `sum-mod-256` checksum; 
they differ only in the IR transport that carries the frame (3-frame vs 1-frame). 
Some AC can accepts either.

## Install

```bash
pip install daikin-ir-encoder
```

No runtime dependencies. Pure Python, 3.11–3.14 tested.

## Quick start

```python
from daikin_ir_encoder import build, VARIANT_3FRAME

timings = build(
    power=True,
    mode="cool",          # auto | dry | cool | heat | fan
    temp=21,              # °C; ignored in dry/fan
    fan="auto",           # 1..5 | auto | night | comfort
    v_swing=False,
    h_swing=False,
    econo=False,
    outdoor_quiet=False,  # outdoor-unit quiet mode (not indoor fan)
    intelligent_eye=False,
    powerful=False,       # turbo; AC clears after 20 min
    variant=VARIANT_3FRAME,
)
```

To schedule the AC to switch on or off at a specific time of day, pass
`on_timer` / `off_timer` as `datetime.time` values:

```python
from datetime import time
timings = build(mode="cool", temp=21,
                on_timer=time(7, 30),     # turn ON at 07:30
                off_timer=time(22, 0))    # turn OFF at 22:00
```

Hand the list to whatever transmitter you have. With an ESPHome
`remote_transmitter`:

```yaml
- remote_transmitter.transmit_raw:
    carrier_frequency: 38kHz
    code: [3500, -1700, 454, -413, 454, -1280, ...]
```

With the Home Assistant `infrared` integration, pass it as `Command.timings`
with `modulation=38000`. Broadlink and LIRC accept the same raw timing list.

## Constants exposed

```python
from daikin_ir_encoder import (
    CARRIER_HZ,           # 38000
    VARIANT_3FRAME,       # "3frame"
    VARIANT_1FRAME,       # "1frame"
    VARIANTS,             # tuple of the above
    MODES,                # {"auto": 0x0, "dry": 0x2, "cool": 0x3, "heat": 0x4, "fan": 0x6}
    MODE_AUTO, MODE_DRY, MODE_COOL, MODE_HEAT, MODE_FAN,
    FAN_SPEEDS,           # {"1": 0x3, ..., "5": 0x7, "auto": 0xA, "night": 0xB, "comfort": 0xA}
    TEMP_RANGES,          # {"cool": (18, 32), "heat": (10, 30), "auto": (18, 30)}
)
```

`TEMP_RANGES` is informational — the encoder doesn't clamp. Out-of-range
temps raise `ValueError` (`temp × 2` overflows the byte).

## Protocol

| | |
|---|---|
| Carrier | 38 kHz |
| Encoding | PPM, LSB-first; ~454 µs mark; ~413 µs space = 0; ~1280 µs space = 1 |
| Frame | 19 bytes — header `11 da 27 00 00`, payload, checksum `sum(bytes[:18]) & 0xFF` |
| Statefulness | Absolute. Every press carries the full state (mode/temp/fan/swing/power/features). Not a toggle. |
| 3-frame transport | preamble + identity frame + clock frame + state frame; 584 edges, ~450 ms on air.|
| 1-frame transport | preamble + state frame only; 320 edges, ~220 ms on air.|

If you don't know which remote your unit shipped with, the AC accepts either —
try `VARIANT_3FRAME` first.

State-frame layout:

| Byte | Bits | Field | Notes |
|---|---|---|---|
| 0–4 | all | Header | constant `11 da 27 00 00` |
| 5 | 0 | Power | |
| 5 | 1 | ON-timer enable | |
| 5 | 2 | OFF-timer enable | |
| 5 | 3 | Variant ID | `1` for ARC466A9 (3-frame), `0` for ARC480A11 (1-frame) |
| 5 | 4–7 | Mode | `0`=auto, `2`=dry, `3`=cool, `4`=heat, `6`=fan |
| 6 | all | Temperature | °C × 2; `0xC0` in dry mode |
| 8 | 4–7 | Fan | `3`–`7` = L1–L5; `0xA` = auto/comfort; `0xB` = night |
| 8 | 0–3 | V-swing | `0xF` on, `0x0` off |
| 9 | 0–3 | H-swing | `0xF` on, `0x0` off |
| 10 | all | ON-timer, low 8 bits | minutes-since-midnight |
| 11 | 0–3 | ON-timer, high 4 bits | (11-bit minutes total) |
| 11 | 4–7 | OFF-timer, low 4 bits | |
| 12 | all | OFF-timer, high 8 bits | (11-bit minutes total) |
| 13 | 0 | Powerful | |
| 13 | 5 | Outdoor quiet | |
| 16 | 1 | Intelligent Eye | |
| 16 | 2 | Econo | |
| 16 | 7 | Weekly-timer disable | `1` = weekly schedule inactive, `0` = weekly active. 3-frame only — 1-frame has no clock so no weekly. Set via the `weekly_active` argument; the schedule itself is programmed via a separate command not handled by this library. |
| 18 | all | Checksum | `sum(bytes[:18]) & 0xFF` |

Timer fields hold 11-bit minutes. The AC interprets them as **time-of-day**
on devices shipped with ARC466A9 (it has a clock — sentinel `0x600` for "disabled") and as a
**countdown duration** on devices shipped with ARC480A11 (no clock — sentinel `0x000`). The
`on_timer`/`off_timer` arguments take a `datetime.time` either way; the
encoder picks the right sentinel. Caller decides what `time(7, 30)` means
on 1-frame (literal time vs "fire in 7h30m").

### Clock (3-frame transport only)

The second frame in the 3-frame transport carries the remote's wall clock:

| Byte | Bits | Field | Encoding |
|---|---|---|---|
| 0–4 | all | Header | constant `11 da 27 00 42` |
| 5 | all | Minutes since midnight, low 8 bits | |
| 6 | 0–2 | Minutes since midnight, high 3 bits | 11-bit total, 0–1439 |
| 6 | 3–7 | Day of week | `1`=Sun, `2`=Mon, `3`=Tue, `4`=Wed, `5`=Thu, `6`=Fri, `7`=Sat |
| 7 | all | Checksum | `sum(bytes[:7]) & 0xFF` |

```python
from datetime import datetime
from daikin_ir_encoder import build

timings = build(mode="cool", temp=21, dt=datetime.now())
```

`dt` defaults to `datetime.now()`. Pass an explicit `datetime` for
deterministic output. The AC ignores the clock for normal commands — only
timer features depend on it.

## Mutual-exclusion rules

The encoder mirrors the rules the AC enforces, so the byte stream stays
self-consistent:

- `powerful=True` forces `econo`, `outdoor_quiet`, and `comfort` off and
  downgrades `fan="comfort"` to `fan="auto"` (the real remote reverts to the
  user's last manual fan; we can't reproduce that without state, so `auto`
  is the safest stand-in). **`intelligent_eye` is preserved** — verified by
  capture. The AC itself clears the powerful bit after ~20 minutes;
  retransmit if you want the new state.
- `fan="comfort"` is signaled in the identity frame (3-frame transport only).
  The state frame can't distinguish it from `fan="auto"` + V-swing off.
  Combining `v_swing=True` with `fan="comfort"` is a contradiction — pick one.
- Outdoor quiet is silently ignored by the AC in `dry` and `fan` modes (the
  bit still goes on the wire).

## Tested against

- Daikin FTXS35/42/50 K2V1B split units (R410A)
- Remotes ARC466A9 (3-frame) and ARC480A11 (1-frame)
- ESPHome 2026.5.2 on an XIAO IR Mate (ESP32-C3) as the transmitter

Run the suite with `uv run pytest`.

## Related work

- [blafois/Daikin-IR-Reverse](https://github.com/blafois/Daikin-IR-Reverse)

Further refinements over the blafois doc:

- byte 5 timer-enable bits are **swapped** — bit 1 is the ON-timer enable,
  bit 2 is the OFF-timer enable
- byte 16 bit 7 is Weekly-timer disable bit
- frame 2 of the 3-frame transport is documented as a fixed
  `11 da 27 00 42 00 00 54` constant; in our captures it carries the
  remote's wall clock (day-of-week + minutes-since-midnight + its own
  checksum). See the [Clock](#clock-3-frame-transport-only) section above.

## License

Apache-2.0. See [LICENSE](LICENSE).

This library is an independent reverse-engineering effort and is not affiliated
with or endorsed by Daikin Industries, Ltd. "Daikin" is a trademark of its
respective owner; the name is used here solely to describe interoperability.
