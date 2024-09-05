import asyncio
import argparse
import struct
import platform
import json
import xml.etree.ElementTree as ET
from bleak import BleakScanner
from bleak import BleakClient
from bleak import uuids

uart_uuid = uuids.normalize_uuid_16(0xFFF0)
uart_receive_uuid = uuids.normalize_uuid_16(0xFFF1)
uart_write_uuid = uuids.normalize_uuid_16(0xFFF2)
uart_ble_config_uuid = uuids.normalize_uuid_16(0xFFF3)

message_size = {
    1:21,
    2:22,
    4:9,
    5:9,
    6:9,
    7:9,
    8:9,
    9:9,
    10:9,
    11:9,
    12:9,
    13:9,
    14:9,
    15:9,
    16:9
}

backlight_modes = {
    0: "Normally on",
    1: "Normally off",
    2: "Auto"
}

def calc_crc(message):
    crc = 255
    for x in message:
        crc -= x
    crc &= 0xFF
    return crc

def dump_message(data):
    if data != None:
        print (len(data), "".join(["%2.2x" % x for x in data]))

async def list_devices():
    print ("scanning...")
    devices = await BleakScanner.discover(return_adv=True)
    for device, adv in devices.values():
        # The manufacturer ID seems to change randomly, so let's just look at the data:
        values = list(adv.manufacturer_data.values())
        manufacturer_data = values[0] if len(values) > 0 else bytes()
        # print(device)
        # dump_message(manufacturer_data)
        if manufacturer_data == bytes([0x31,0x00,0x00,0x00,0x00,0x00]):
            local_name = adv.local_name
            print (f"potential client: {device.address} {local_name}")
            async with BleakClient(device) as client:
                # Have a look if we have a UART channel:
                hasUartChannel = False
                for service in client.services:
                    if service.uuid == uart_uuid:
                        for char in service.characteristics:
                            if char.uuid == uart_receive_uuid and "read" in char.properties:
                                hasUartChannel = True
                print ("hasUartChannel", hasUartChannel)
                if hasUartChannel:
                    # try to receive a message and check the header and checksum are correct:
                    await send_request(client, 1)

                    def isValidMessage(data):
                        if len(message) >= 5 and struct.unpack_from(">H", message, 0)[0] == 0xB55B:
                            crc = calc_crc(message[0:len(message)-1])
                            if crc == message[-1]:
                                return True
                        return False

                    if False:
                        message = await client.read_gatt_char(uart_receive_uuid)
                        dump_message(message)

                        if isValidMessage(message):
                            print (f"{device.address} {local_name}")
                            complete = True
                    else:
                        queue = asyncio.Queue()

                        async def callback(x,data):
                            await queue.put(data)

                        await client.start_notify(uart_receive_uuid, callback)

                        count = 0
                        complete = False
                        while not complete and count < 5.0:
                            try:
                                message = queue.get_nowait()
                                dump_message(message)

                                if isValidMessage(message):
                                    print (f"{device.address} {local_name}")
                                    complete = True
                            except asyncio.QueueEmpty:
                                await asyncio.sleep(1.0)
                                count += 1

                        await client.stop_notify(uart_receive_uuid)                    

async def send_request(client : BleakClient, msg : int):
    data = struct.pack(">HBBII", 0xA55A, 0, msg, 0, 0)
    data += bytes([calc_crc(data)])
    await client.write_gatt_char(uart_write_uuid, data, response=False)

def output_json(info):
    print(json.dumps(info))

def output_xml(root, info):
    doc = ET.Element(root)
    for key, value in info.items():
        ET.SubElement(doc, key).text = str(value)
    print (ET.tostring(doc, encoding='utf-8', xml_declaration=True).decode())

def output_text(info):
    for key, value in info.items():
        print ("%s: %s" % (key, value))

async def get_device(args):
    device = None
    if platform.system() != 'Darwin' and args.mac != None:
        device = await BleakScanner.find_device_by_address(args.mac)
    elif platform.system() == 'Darwin' and args.uuid != None:
        device = await BleakScanner.find_device_by_address(args.uuid)
    elif args.name != None:
        device = await BleakScanner.find_device_by_name(args.name)
    if device == None:
        print ("Device not found")
    return device

async def read_device(args):
    device = await get_device(args)
    if device != None:
        async with BleakClient(device) as client:
            success = False
            while not success:
                await send_request(client, 1)
                message = await client.read_gatt_char(uart_receive_uuid)
                while len(message) > 4 and not success:
                    dump_message(message)
                    magic, device_address, message_id = struct.unpack_from(">HBB", message, 0)
                    if magic == 0xB55B and len(message) >= message_size[message_id]:
                        if message_id == 1:
                            (magic, device_address, message_id, percentage, capacity, voltage, current, charge_energy_high, charge_energy_low, discharge_energy_high, discharge_energy_low, temperature, u1, crc) = struct.unpack_from(">HBBBHHHBHBHHBB", message, 0)
                            if calc_crc(message[0:message_size[message_id]-1]) == crc:
                                success = True
                                info = {
                                    "device_address":device_address,
                                    "percentage":percentage,
                                    "capacity":capacity/10,
                                    "voltage":voltage,
                                    "current":current/10,
                                    "charge_energy":(charge_energy_high << 16) + charge_energy_low,
                                    "discharge_energy":(discharge_energy_high << 16) + discharge_energy_low,
                                    "temperature":temperature/10,
                                    "u1":u1
                                }
                                if args.json:
                                    output_json(info)
                                elif args.xml:
                                    output_xml("info", info)
                                else:
                                    output_text(info)
                        message = message[message_size[message_id]:]
                    else:
                        message = message[1:]

async def log_device(args):
    device = await get_device(args)
    if device != None:
        async with BleakClient(device) as client:
            print(f"\"device_address\",\"percentage\",\"capacity\",\"voltage\",\"current\",\"charge_energy\",\"discharge_energy\",\"temperature\"")
            while True:
                await send_request(client, 1)
                message = await client.read_gatt_char(uart_receive_uuid)
                while len(message) > 4:
                    magic, device_address, message_id = struct.unpack_from(">HBB", message, 0)
                    if magic == 0xB55B and len(message) >= message_size[message_id]:
                        if message_id == 1:
                            (magic, device_address, message_id, percentage, capacity, voltage, current, charge_energy_high, charge_energy_low, discharge_energy_high, discharge_energy_low, temperature, u1, crc) = struct.unpack_from(">HBBBHHHBHBHHBB", message, 0)
                            if calc_crc(message[0:message_size[message_id]-1]) == crc:
                                info = {
                                    "device_address":device_address,
                                    "percentage":percentage,
                                    "capacity":capacity/10,
                                    "voltage":voltage,
                                    "current":current/10,
                                    "charge_energy":(charge_energy_high << 16) + charge_energy_low,
                                    "discharge_energy":(discharge_energy_high << 16) + discharge_energy_low,
                                    "temperature":temperature/10,
                                    "u1":u1
                                }
                                print(f"{info["device_address"]},{info["percentage"]},{info["capacity"]},{info["voltage"]},{info["current"]},{info["charge_energy"]},{info["discharge_energy"]},{info["temperature"]}")
                        message = message[message_size[message_id]:]
                    else:
                        message = message[1:]

async def read_device_configuration(args):
    device = await get_device(args)
    if device != None:
        async with BleakClient(device) as client:
            success = False
            while not success:
                await send_request(client, 2)
                message = await client.read_gatt_char(uart_receive_uuid)
                while len(message) > 4 and not success:
                    # dump_message(message)
                    magic, device_address, message_id = struct.unpack_from(">HBB", message, 0)
                    if magic == 0xB55B and len(message) >= message_size[message_id]:
                        if message_id == 2:
                            (magic, device_address, message_id, backlight_mode, full_battery_voltage, low_voltage_alarm, high_voltage_alarm, over_current_alarm, rated_capacity, u1, u2, under_battery_voltage, u3, u4, crc) = struct.unpack_from(">HBBBHHHHHBBHBBB", message, 0)
                            if calc_crc(message[0:message_size[message_id]-1]) == crc:
                                success = True
                                if not args.json and not args.xml:
                                    backlight_mode = "%i (%s)" % (backlight_mode, backlight_modes[backlight_mode])
                                else:
                                    backlight_mode = str(backlight_mode)
                                info = {
                                    "device_address":device_address,
                                    "backlight_mode":backlight_mode,
                                    "full_battery_voltage":full_battery_voltage/10,
                                    "low_voltage_alarm":low_voltage_alarm/10,
                                    "high_voltage_alarm":high_voltage_alarm/10,
                                    "over_current_alarm":over_current_alarm/10,
                                    "rated_capacity":rated_capacity/10,
                                    "under_battery_voltage":under_battery_voltage/10,
                                    "u1":u1,
                                    "u2":u2,
                                    "u3":u3,
                                    "u4":u4
                                }
                                if args.json:
                                    output_json(info)
                                elif args.xml:
                                    output_xml("info", info)
                                else:
                                    output_text(info)
                        message = message[message_size[message_id]:]
                    else:
                        message = message[1:]

async def set_byte(client : BleakClient, msg : int, value):
    data = struct.pack(">HBBBBHI", 0xA55A, 0, msg, value, 0, 0, 0)
    data += bytes([calc_crc(data)])
    await client.write_gatt_char(uart_write_uuid, data, response=False)

async def set_short(client : BleakClient, msg : int, value):
    data = struct.pack(">HBBHHI", 0xA55A, 0, msg, value, 0, 0)
    data += bytes([calc_crc(data)])
    await client.write_gatt_char(uart_write_uuid, data, response=False)

async def set_short_float(client : BleakClient, msg : int, value):
    await set_short(client, msg, round(value * 10.0))

async def set_byte_float(client : BleakClient, msg : int, value):
    await set_byte(client, msg, round(value * 10.0))

async def set_name(client : BleakClient, msg : int, name):
    buffer = bytearray(name, "utf-8") + bytearray([0] * 16)
    data = struct.pack(">HBB", 0xA55A, 0, msg) + buffer[0:16]
    await client.write_gatt_char(uart_write_uuid, data, response=False)

config_funcs = {
    "calibrating_current":(0x04, set_short_float),
    "calibrating_voltage":(0x05, set_short_float),
    "full_battery_voltage":(0x06, set_short_float),
    "low_voltage_alarm":(0x07, set_short_float),
    "high_voltage_alarm":(0x08, set_short_float),
    "over_current_alarm":(0x09, set_short_float),
    "rated_capacity":(0x0A, set_short_float),
    "percentage":(0x0B, set_byte),
    "device_address":(0x0C, set_byte),
    "backlight_mode":(0x0d, set_byte),
    "under_battery_voltage":(0x0E, set_short_float),
    "device_name":(0x10, set_name)
}

async def set_device_config(args):
    try:
        cmd, func = config_funcs[args.variable]
    except KeyError:
        print ("unknown value %s" % args.variable)
        print ("known options: %s" % ",".join(config_funcs.keys()))
        return

    if func == set_short_float or func == set_byte_float:
        value = float(args.value)
    elif func != set_name:
        value = int(args.value)
    else:
        value = args.value

    device = await get_device(args)
    if device != None:
        async with BleakClient(device) as client:
            success = False
            while not success:
                await func(client, cmd, value)

                message = await client.read_gatt_char(uart_receive_uuid)
                while len(message) > 4 and not success:
                    magic, _, message_id = struct.unpack_from(">HBB", message, 0)
                    if magic == 0xB55B and len(message) >= message_size[message_id]:
                        size = message_size[message_id]
                        if message_id == cmd and message[size-1] == calc_crc(message[0:size-1]):
                            success = True
                        message = message[message_size[message_id]:]
                    else:
                        message = message[1:]
            print ("success")

def main():
    parser = argparse.ArgumentParser(description='WLS-MVAxxx python client')

    subparsers = parser.add_subparsers(help='operation', dest='command', required=True)

    device_parser = argparse.ArgumentParser(add_help=False)
    device_parser_group = device_parser.add_mutually_exclusive_group(required=True)
    if platform.system() == 'Darwin':
        device_parser_group.add_argument('--uuid', help='device uuid')
    else:
        device_parser_group.add_argument('--mac', help='device MAC')
    device_parser_group.add_argument('--name', help='device name')

    output_parser = argparse.ArgumentParser(add_help=False)
    output_format_group = output_parser.add_mutually_exclusive_group()
    output_format_group.add_argument('--json', help='print json', action='store_true')
    output_format_group.add_argument('--xml', help='print xml', action='store_true')
    output_format_group.add_argument('--text', help='print text', action='store_true')

    parser_list = subparsers.add_parser('list', help='list WLS-MVAxxx detectable through bluetooth', parents=[])
    parser_list.set_defaults(func=lambda args: asyncio.run(list_devices()))

    parser_read = subparsers.add_parser('read', help='read data from the device', parents=[device_parser, output_parser])
    parser_read.set_defaults(func=lambda args: asyncio.run(read_device(args)))

    parser_config = subparsers.add_parser('configuration', help='read the configuration from the device', parents=[device_parser, output_parser])
    parser_config.set_defaults(func=lambda args: asyncio.run(read_device_configuration(args)))

    parser_setconfig = subparsers.add_parser('set', help='set a configuration value on the device', parents=[device_parser])
    parser_setconfig.add_argument("variable")
    parser_setconfig.add_argument("value")
    parser_setconfig.set_defaults(func=lambda args: asyncio.run(set_device_config(args)))

    parser_log = subparsers.add_parser('log', help='log data from the device to csv', parents=[device_parser])
    parser_log.set_defaults(func=lambda args: asyncio.run(log_device(args)))

    args = parser.parse_args()
    # print (args)
    try:
        args.func(args)
    except AttributeError:
        pass

if __name__ == "__main__":
    main()
