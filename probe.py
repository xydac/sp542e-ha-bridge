"""Drive the SP542E directly to confirm the BanlanX_6xx protocol.

RUN LOCALLY ON THE MAC (not over SSH — CoreBluetooth needs the GUI session):

    cd sp542e && ./run.sh probe

Confirmed working: power, static-white mode, CCT (cold/warm), brightness.
The state query elicits a multi-packet `53..` status dump (firmware, IP, name).
"""
import asyncio

from bleak import BleakClient

import protocol as p


def on_notify(_h, data: bytearray):
    print(f"  <- notify: {p.hexstr(bytes(data))}")


async def w(c, frame, label):
    print(f"  -> {label:<20} {p.hexstr(frame)}")
    await c.write_gatt_char(p.CHAR_UUID, frame, response=p.WRITE_RESPONSE)
    await asyncio.sleep(2.0)


async def main():
    print(f"Connecting to {p.DEVICE_NAME} ({p.DEVICE_ADDRESS}) ...")
    async with BleakClient(p.DEVICE_ADDRESS, timeout=20.0) as c:
        print(f"Connected. MTU={c.mtu_size}\n")
        try:
            await c.start_notify(p.CHAR_UUID, on_notify)
        except Exception as e:
            print(f"  (notify subscribe failed: {e})")

        await w(c, p.state_query(), "STATE QUERY")
        await w(c, p.power(True), "POWER ON")
        await w(c, p.light_mode(p.MODE_STATIC_WHITE), "STATIC WHITE MODE")
        await w(c, p.cct_raw(0, 255), "CCT WARM")
        await w(c, p.cct_raw(255, 0), "CCT COOL")
        await w(c, p.cct_raw(128, 128), "CCT MID")
        await w(c, p.brightness(51), "BRIGHTNESS 20%")
        await w(c, p.brightness(255), "BRIGHTNESS 100%")
        await w(c, p.power(False), "POWER OFF")
        print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
