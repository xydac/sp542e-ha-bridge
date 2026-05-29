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
| `protocol.py` | LED-BLE `7E..EF` frame builders (power/RGB/brightness). Single source of truth. |
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
cd sp542e
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

## Protocol (FFE1, plaintext, 9-byte frames)

This is a **CCT (tunable-white)** strip — HA exposes color-temp + brightness +
on/off, no RGB.

| Command | Bytes | Status |
|---|---|---|
| Power ON  | `7e ff 04 01 ff ff ff ff ef` | confirmed format |
| Power OFF | `7e ff 04 00 ff ff ff ff ef` | confirmed format |
| Brightness 0–100 | `7e ff 01 VV 00 ff ff ff ef` | confirmed format |
| Color temp | one of 3 candidates (see below) | **probe to confirm** |

The CCT byte format isn't reliably documented, so `probe.py` tries 3 candidate
formats and you report which GROUP shifts warm↔cool. Then point `cct` in
`protocol.py` at the winner (`cct_rgbslot` / `cct_sub02` / `cct_sub05`). Both
probe and bridge read from `protocol.py`, so it's a one-line change.

color_temp is in **mireds**: `MAX_MIREDS`=370 (~2700K warm), `MIN_MIREDS`=153 (~6500K cool).

## Caveats

- **Availability = Mac uptime.** If the Mac sleeps/powers off, the light is
  uncontrollable and HA shows it unavailable. (Always-on desktop = fine.)
- **Optimistic state.** The controller has no reliable state read, so the
  bridge tracks state locally; changes made via the original app/remote won't
  reflect back in HA.
- **One BLE connection.** Keep the original phone app disconnected.
