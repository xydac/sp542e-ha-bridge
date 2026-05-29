# SP542E MQTT ↔ BLE bridge

Controls the cloud-locked **SP542E "BedRoof" LED controller** from Home
Assistant with **no new hardware**. A small Python service on the always-on
Mac connects to the controller over BLE and exposes it to HA as an MQTT light.

```
HA (VirtualBox) ──MQTT──> Mosquitto (on HA) ──MQTT──> bridge.py (Mac) ──BLE──> SP542E
```

HA needs **no Bluetooth** and **no custom component** — the entity
`light.bed_roof` appears automatically via MQTT discovery. This works around
the VirtualBox VM having no usable Bluetooth.

## Files

| File | Purpose |
|---|---|
| `protocol.py` | BanlanX_6xx (`53 ..`) frame builders (power/CCT/brightness). Single source of truth. |
| `probe.py`    | One-shot: drives the strip directly to confirm the protocol. |
| `bridge.py`   | The service: MQTT light ↔ BLE. |
| `run.sh`      | Bootstraps `.venv` (via `uv`), loads `.env`, runs bridge or probe. |
| `.env.example`| MQTT credentials template → copy to `.env`. |
| `com.xydac.sp542e-bridge.plist` | launchd LaunchAgent for always-on auto-start. |

## ⚠️ macOS Bluetooth requirement

BLE only works from the Mac's **local GUI session**, never over SSH
(CoreBluetooth TCC restriction). Run everything from a Terminal sitting at the
Mac. First run will prompt to grant Bluetooth to the Python binary
(System Settings → Privacy & Security → Bluetooth).

## Setup

```bash
cd sp542e-ha-bridge
cp .env.example .env          # then fill in MQTT_USER / MQTT_PASS

# 1. Confirm the protocol actually drives the light (watch the strip):
./run.sh probe

# 2. Run the bridge in the foreground to test HA integration:
./run.sh
#    -> light.bed_roof should appear in Home Assistant automatically.

# 3. Make it always-on (auto-start at login, restart on crash):
cp com.xydac.sp542e-bridge.plist ~/Library/LaunchAgents/
launchctl load -w ~/Library/LaunchAgents/com.xydac.sp542e-bridge.plist
```

## Protocol (BanlanX_6xx, plaintext, over FFE0/FFE1)

This is a **CCT (tunable-white)** strip — HA exposes color-temp + brightness +
on/off, no RGB. The controller speaks the **BanlanX_6xx** family (SP630E-style),
*not* the LED-BLE `7E..EF` protocol and *not* idealLED AES (both were tried and
silently ignored). It advertises manufacturer id `0x5053` with advert data
`5d 10..` (model id `0x5d`).

Frames are plaintext on write characteristic **FFE1** (service FFE0), shaped
`53 <cmd> 00 01 00 <len> <payload>`. **Writes must be acknowledged**
(`response=True`) or the device ignores them — this was the key gotcha.

| Command | Bytes |
|---|---|
| Power ON / OFF | `53 50 00 01 00 01 01` / `53 50 00 01 00 01 00` |
| Static-white mode | `53 53 00 01 00 02 02 01` (set before CCT/white-brightness) |
| Color temp (static) | `53 61 00 01 00 02 <cold> <warm>` (`<cold>`/`<warm>` 0–255; `0x60` = dynamic) |
| Brightness | `53 51 00 01 00 02 <which> <level>` (`<which>` 0=color 1=white; `<level>` 0–255) |
| State query | `53 02 00 01 00 01 01` → device replies multi-packet status (fw, IP, name) |

`color_temp` is in **mireds**: `MAX_MIREDS`=370 (~2700K warm), `MIN_MIREDS`=153
(~6500K cool); `protocol.py:cct()` maps mireds → cold/warm bytes.

Protocol reference: [`monty68/uniled`](https://github.com/monty68/uniled)
`custom_components/uniled/lib/ble/banlanx_6xx.py` (the SP542E isn't in UniLED's
model list, but it's this family).

## Caveats

- **Availability = Mac uptime.** If the Mac sleeps/powers off, the light is
  uncontrollable and HA shows it unavailable. (Always-on desktop = fine.)
- **Optimistic state.** The controller has no reliable state read, so the
  bridge tracks state locally; changes made via the original app/remote won't
  reflect back in HA.
- **One BLE connection.** Keep the original phone app disconnected.
