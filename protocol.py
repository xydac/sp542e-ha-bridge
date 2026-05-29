"""SP542E / BanlanX_6xx (SP630E-family) protocol frame builders.

The "BedRoof" SP542E is a BanlanX device. Its BLE advertisement manufacturer
data was `5d 10 b0 16 ...` with manufacturer id 0x5053 (20563). BanlanX_6xx
devices advertise manufacturer data `[model_id, 0x10]` -> model id 0x5d, second
byte 0x10: this is the **BanlanX_6xx** protocol family (not BanlanX2's `A0..`
nor the LED-BLE `7e..ef`, both of which this device ignored).

Wire format (plaintext, key byte = 0):

    53 <cmd> 00 01 00 <len> <payload...>
    |  |     |  |  |  |     payload (len bytes)
    |  |     |  |  |  payload length
    |  |     |  |  reserved 0x00
    |  |     |  reserved 0x01
    |  |     message key (0 = unencoded)
    |  command
    header 'S' (0x53)

Writes MUST be acknowledged (write WITH response). Confirmed in
monty68/uniled custom_components/uniled/lib/ble/{banlanx_6xx,device}.py.
"""
from __future__ import annotations

# BLE addressing -----------------------------------------------------------
# macOS CoreBluetooth hides the MAC and uses a host-stable UUID (from scan.py).
DEVICE_ADDRESS = "C3CEFC39-CF21-3DBB-9A11-35B4EA1DA194"
DEVICE_NAME = "BedRoof"

SERVICE_UUID = "0000ffe0-0000-1000-8000-00805f9b34fb"
CHAR_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"

# BanlanX writes are acknowledged: bleak write_gatt_char(..., response=True)
WRITE_RESPONSE = True

HEADER = 0x53

# Light modes / effects
MODE_STATIC_WHITE = 0x02
WHITE_EFFECT = 0x01  # first static-white effect


def _encode(cmd: int, payload: list[int]) -> bytes:
    """Wrap a command per BanlanX_6xx: 53 <cmd> 00 01 00 <len> <payload>."""
    body = [v & 0xFF for v in payload]
    return bytes([HEADER, cmd & 0xFF, 0x00, 0x01, 0x00, len(body) & 0xFF, *body])


# --- commands -------------------------------------------------------------
def state_query() -> bytes:
    """Ask the device for its status; it replies via FFE1 notify:  cmd 0x02."""
    return _encode(0x02, [0x01])


def power(on: bool) -> bytes:
    """Power on/off:  cmd 0x50."""
    return _encode(0x50, [0x01 if on else 0x00])


def light_mode(mode: int, effect: int = WHITE_EFFECT) -> bytes:
    """Set light mode (e.g. MODE_STATIC_WHITE):  cmd 0x53."""
    return _encode(0x53, [mode, effect])


def brightness(level: int, white_mode: bool = True) -> bytes:
    """Brightness 0-255:  cmd 0x51 [which, level].  which: 0=color, 1=white."""
    return _encode(0x51, [0x01 if white_mode else 0x00, _clamp(level, 0, 255)])


def rgb(r: int, g: int, b: int, level: int = 0xFF) -> bytes:
    """Static RGB color:  cmd 0x52 [r, g, b, level]."""
    return _encode(0x52, [r, g, b, _clamp(level, 0, 255)])


def cct_raw(cold: int, warm: int, static: bool = True) -> bytes:
    """Set color temperature by cold/warm channel levels (0-255 each).
    Static white -> cmd 0x61, dynamic -> cmd 0x60.
    """
    return _encode(0x61 if static else 0x60, [_clamp(cold, 0, 255), _clamp(warm, 0, 255)])


# --- Color temperature helpers (Home Assistant mireds) --------------------
# HA color_temp in mireds: HIGH mired = warm (2700K->370), LOW = cool (6500K->153).
MIN_MIREDS = 153
MAX_MIREDS = 370


def cct(mireds: int) -> bytes:
    """Build a static-white CCT frame from an HA mireds value."""
    m = _clamp(mireds, MIN_MIREDS, MAX_MIREDS)
    warm_frac = (m - MIN_MIREDS) / (MAX_MIREDS - MIN_MIREDS)
    warm = round(warm_frac * 255)
    cold = round((1 - warm_frac) * 255)
    return cct_raw(cold, warm, static=True)


def _clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, int(v)))


def hexstr(frame: bytes) -> str:
    return " ".join(f"{b:02x}" for b in frame)
