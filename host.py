import asyncio
import struct
from bleak import BleakScanner
from bleak import BleakClient
from bleak import uuids

uart_uuid = uuids.normalize_uuid_16(0xFFF0)
uart_receive_uuid = uuids.normalize_uuid_16(0xFFF1)
uart_write_uuid = uuids.normalize_uuid_16(0xFFF2)

def calc_crc(message):
    crc = 255
    for x in message:
        crc -= x
    crc &= 0xFF
    return crc

async def listDevices():
    devices = await BleakScanner.discover(return_adv=True)
    for device, adv in devices.values():
        # The manufacturer ID seems to change randomly, so let's just look at the data:
        values = list(adv.manufacturer_data.values())
        manufacturer_data = values[0] if len(values) > 0 else bytes()
        if manufacturer_data == bytes([0x31,0x00,0x00,0x00,0x00,0x00]):
            async with BleakClient(device) as client:
                # Have a look if we have a UART channel:
                hasUartChannel = False
                for service in client.services:
                    if service.uuid == uart_uuid:
                        for char in service.characteristics:
                            if char.uuid == uart_receive_uuid and "read" in char.properties:
                                hasUartChannel = True

                if hasUartChannel:
                    # try to receive a message and check the header and checksum are correct:
                    message = await client.read_gatt_char(uart_receive_uuid)
                    # print ("".join(["%2.2x" % x for x in message]))

                    if struct.unpack_from(">H", message, 0)[0] == 0xB55B:
                        crc = calc_crc(message[0:len(message)-1])
                        if crc == message[-1]:
                            print (device)

async def main():
    await listDevices()

asyncio.run(main())
