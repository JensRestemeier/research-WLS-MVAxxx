import asyncio
import struct
from bleak import BleakScanner
from bleak import BleakClient
from bleak import uuids

def calccrc(message):
    crc = 255
    for x in message:
        crc -= x
    crc &= 0xFF
    return crc

"""
52C2E87B-536B-2008-4047-36041D4415B4: CH9141BLE2U
AdvertisementData(local_name='device ', manufacturer_data={48652: b'1\x00\x00\x00\x00\x00'}, tx_power=0, rssi=-47)
"""

"""
PNP ID: Hex:		01390700001001
System Id: Hex:		13DE79000010535C
"""

async def main():
    uart_uuid = uuids.normalize_uuid_16(0xFFF0)
    uart_receive_uuid = uuids.normalize_uuid_16(0xFFF1)
    uart_write_uuid = uuids.normalize_uuid_16(0xFFF2)

    energy_monitors = []
    devices = await BleakScanner.discover(return_adv=True)
    for device, adv in devices.values():
        print (device)
        print (adv)
        if uart_uuid in adv.service_uuids:
            print (f"potential energy monitor {adv.local_name}")

            # try to receive a message and check the header and checksum are correct:
            async with BleakClient(device) as client:
                pnp_id = await client.read_gatt_char("2a50")
                print("PNP ID: %s" % "".join(["%2.2x" % x for x in pnp_id]))

                system_id = await client.read_gatt_char("2a23")
                print("System ID: %s" % "".join(["%2.2x" % x for x in system_id]))

                message = await client.read_gatt_char(uart_receive_uuid)
                print ("".join(["%2.2x" % x for x in message]))

                if struct.unpack_from(">H", message, 0)[0] == 0xB55B:
                    crc = calccrc(message[0:len(message)-1])
                    if crc == message[-1]:
                        print ("energy monitor found!")
                        energy_monitors.append(device)

asyncio.run(main())
