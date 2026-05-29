"""SP542E MQTT <-> BLE bridge.

Runs on the (always-on) Mac. Maintains a BLE connection to the "BedRoof"
SP542E and exposes it to Home Assistant as an MQTT light using HA's MQTT
auto-discovery. HA needs NO Bluetooth and NO custom component — the entity
`light.bed_roof` simply appears.

    HA  <--MQTT-->  Mosquitto (on HA)  <--MQTT-->  this service  <--BLE-->  SP542E

Config via environment (.env, see .env.example):
    MQTT_HOST, MQTT_PORT, MQTT_USER, MQTT_PASS
    DEVICE_ADDRESS (optional override of the CoreBluetooth UUID)

Run:  ./run.sh        (sets up venv, loads .env, runs this)
"""
from __future__ import annotations

import asyncio
import json
import os
import signal

import aiomqtt
from bleak import BleakClient

import protocol as p

# --- config ---------------------------------------------------------------
MQTT_HOST = os.environ.get("MQTT_HOST", "homeassistant.local")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_USER = os.environ.get("MQTT_USER") or None
MQTT_PASS = os.environ.get("MQTT_PASS") or None
DEVICE_ADDRESS = os.environ.get("DEVICE_ADDRESS", p.DEVICE_ADDRESS)

UID = "sp542e_bedroof"
BASE = f"sp542e/{UID}"
T_SET = f"{BASE}/set"
T_STATE = f"{BASE}/state"
T_AVAIL = f"{BASE}/availability"
T_DISCOVERY = f"homeassistant/light/{UID}/config"

DISCOVERY = {
    "name": None,  # use the device name ("Bed Roof") -> entity_id light.bed_roof
    "unique_id": UID,
    "schema": "json",
    "command_topic": T_SET,
    "state_topic": T_STATE,
    "availability_topic": T_AVAIL,
    "brightness": True,
    "color_mode": True,
    "supported_color_modes": ["color_temp"],  # tunable white (CCT), no RGB
    "min_mireds": p.MIN_MIREDS,
    "max_mireds": p.MAX_MIREDS,
    "device": {
        "identifiers": [UID],
        "name": "Bed Roof",
        "manufacturer": "PAUTIX",
        "model": "SP542E",
    },
}

# Optimistic local state (device has no reliable state read).
state = {
    "state": "OFF",
    "brightness": 255,
    "color_mode": "color_temp",
    "color_temp": (p.MIN_MIREDS + p.MAX_MIREDS) // 2,
}


class BleLink:
    """Holds a BLE connection and reconnects when it drops."""

    def __init__(self, address: str):
        self.address = address
        self.client: BleakClient | None = None
        self._lock = asyncio.Lock()

    async def ensure(self) -> BleakClient:
        async with self._lock:
            if self.client and self.client.is_connected:
                return self.client
            print(f"[ble] connecting to {self.address} ...")
            self.client = BleakClient(self.address, timeout=20.0)
            await self.client.connect()
            print(f"[ble] connected (MTU={self.client.mtu_size})")
            return self.client

    async def write(self, frame: bytes):
        for attempt in (1, 2):
            try:
                client = await self.ensure()
                await client.write_gatt_char(p.CHAR_UUID, frame, response=p.WRITE_RESPONSE)
                print(f"[ble] wrote {p.hexstr(frame)}")
                return
            except Exception as e:
                print(f"[ble] write failed (attempt {attempt}): {e}")
                self.client = None
                await asyncio.sleep(1.0)
        print("[ble] giving up on this write")

    async def close(self):
        if self.client and self.client.is_connected:
            await self.client.disconnect()


async def apply_command(ble: BleLink, payload: dict):
    """Translate an HA JSON light command into BLE frames + update state."""
    turning_on = payload.get("state", "").upper() == "ON"
    turning_off = payload.get("state", "").upper() == "OFF"

    if turning_off:
        await ble.write(p.power(False))
        state["state"] = "OFF"
        return

    # Any non-OFF command implies the light should be on.
    if turning_on or "color_temp" in payload or "brightness" in payload:
        if state["state"] != "ON":
            await ble.write(p.power(True))
            # This is a CCT strip: lock it into static-white mode so the
            # color-temp (0x61) and white-brightness (0x51) commands apply.
            await ble.write(p.light_mode(p.MODE_STATIC_WHITE))
        state["state"] = "ON"

    if "color_temp" in payload:
        mireds = int(payload["color_temp"])
        await ble.write(p.cct(mireds))
        state["color_temp"] = mireds

    if "brightness" in payload:
        bri = int(payload["brightness"])
        await ble.write(p.brightness(bri, white_mode=True))
        state["brightness"] = bri


async def main():
    ble = BleLink(DEVICE_ADDRESS)
    stop = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        asyncio.get_running_loop().add_signal_handler(sig, stop.set)

    will = aiomqtt.Will(topic=T_AVAIL, payload="offline", qos=1, retain=True)
    while not stop.is_set():
        try:
            async with aiomqtt.Client(
                hostname=MQTT_HOST, port=MQTT_PORT,
                username=MQTT_USER, password=MQTT_PASS, will=will,
            ) as mqtt:
                print(f"[mqtt] connected to {MQTT_HOST}:{MQTT_PORT}")
                await mqtt.publish(T_DISCOVERY, json.dumps(DISCOVERY), qos=1, retain=True)
                await mqtt.publish(T_AVAIL, "online", qos=1, retain=True)
                await mqtt.publish(T_STATE, json.dumps(state), qos=1, retain=True)
                await mqtt.subscribe(T_SET)

                async for msg in mqtt.messages:
                    try:
                        payload = json.loads(msg.payload)
                    except Exception:
                        print(f"[mqtt] bad payload: {msg.payload!r}")
                        continue
                    print(f"[mqtt] <- {payload}")
                    await apply_command(ble, payload)
                    await mqtt.publish(T_STATE, json.dumps(state), qos=1, retain=True)
        except aiomqtt.MqttError as e:
            if stop.is_set():
                break
            print(f"[mqtt] error: {e}; reconnecting in 5s")
            await asyncio.sleep(5)

    print("shutting down ...")
    try:
        # best-effort offline + disconnect
        async with aiomqtt.Client(hostname=MQTT_HOST, port=MQTT_PORT,
                                  username=MQTT_USER, password=MQTT_PASS) as m:
            await m.publish(T_AVAIL, "offline", qos=1, retain=True)
    except Exception:
        pass
    await ble.close()


if __name__ == "__main__":
    asyncio.run(main())
