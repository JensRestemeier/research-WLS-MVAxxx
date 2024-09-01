# Sensor emulator for ESP32 (or similar) in MicroPython.

# Write this to a Bluetooth capable controller of your choice to develop and test your
# host software against, without messing with real batteries.

# (No warranty that this is the "correct" way to write BLE apps in MicroPython... The documentation could use a few more
# explanations, you already need to know a lot about BLE before you can use aioble...)

import sys

# ruff: noqa: E402
sys.path.append("")

from micropython import const
from machine import Pin

import asyncio
import aioble
import bluetooth
import struct

_ENV_DEVICE_INFO_UUID = bluetooth.UUID(0x180a)
_ENV_UART_UUID = bluetooth.UUID(0xFFF0)
_ENV_UART2_UUID = bluetooth.UUID(0xFFE0)

_ENV_SYSTEM_ID_UUID = bluetooth.UUID(0x2a23)
_ENV_MODEL_NUMBER_UUID = bluetooth.UUID(0x2a24)
_ENV_SERIAL_NUMBER_UUID = bluetooth.UUID(0x2a25)
_ENV_FIRMWARE_REV_UUID = bluetooth.UUID(0x2a26)
_ENV_HARDWARE_REV_UUID = bluetooth.UUID(0x2a27)
_ENV_SOFTWARE_REV_UUID = bluetooth.UUID(0x2a28)
_ENV_MANUFACTURER_NAME_UUID = bluetooth.UUID(0x2a29)
_PNP_ID_UUID = bluetooth.UUID(0x2a50)

_ENV_UART_DATA_UUID = bluetooth.UUID(0xFFF1)
_ENV_BLE_DATA_UUID = bluetooth.UUID(0xFFF2)
_ENV_BLE_CONFIG_UUID = bluetooth.UUID(0xFFF3)

_ENV_UART_DATA2_UUID = bluetooth.UUID(0xFFE1)
_ENV_BLE_DATA2_UUID = bluetooth.UUID(0xFFE2)

# How frequently to send advertising beacons.
_ADV_INTERVAL_MS = 250_000
_ADV_APPEARENCE_ENVIRONMENT_SENSOR = const(0x140) # => generic display icon

# Register GATT server.
# this is a copy of the advertising data of the CH9141 chip - not sure if the android app is using all of it.
device_info_service = aioble.Service(_ENV_DEVICE_INFO_UUID)
system_id_characteristic = aioble.Characteristic(device_info_service, _ENV_SYSTEM_ID_UUID, read=True, initial=struct.pack("<BBBBBBBB", 0x13, 0xDE, 0x79, 0, 0, 0x10, 0x53, 0x5C))    # 13de79000010535c = OIU 5C5310	Nanjing Qinheng Microelectronics Co., Ltd.
model_number_characteristic = aioble.Characteristic(device_info_service, _ENV_MODEL_NUMBER_UUID, read=True, initial=b"CH9141")
serial_number_characteristic = aioble.Characteristic(device_info_service, _ENV_SERIAL_NUMBER_UUID, read=True, initial=b"190420000000")
firmware_rev_characteristic = aioble.Characteristic(device_info_service, _ENV_FIRMWARE_REV_UUID, read=True, initial=b"VER1.0")
hardware_rev_characteristic = aioble.Characteristic(device_info_service, _ENV_HARDWARE_REV_UUID, read=True, initial=b"VER1.0")
software_rev_characteristic = aioble.Characteristic(device_info_service, _ENV_SOFTWARE_REV_UUID, read=True, initial=b"VER1.0")
manufacturer_name_characteristic = aioble.Characteristic(device_info_service, _ENV_MANUFACTURER_NAME_UUID, read=True, initial=b"WCH")
pnp_id_characteristic = aioble.Characteristic(device_info_service, _PNP_ID_UUID, read=True, initial=struct.pack("<BHHH", 1, 0x0739, 0x0000, 0x0110)) # 01390700001001

uart_service = aioble.Service(_ENV_UART_UUID)
uart_data_characteristic = aioble.Characteristic(uart_service, _ENV_UART_DATA_UUID, read=True, notify=True)
ble_data_characteristic = aioble.Characteristic(uart_service, _ENV_BLE_DATA_UUID, write=True, write_no_response=True)
uart_config_characteristic = aioble.Characteristic(uart_service, _ENV_BLE_CONFIG_UUID, read=True, write=True, notify=True)

uart2_service = aioble.Service(_ENV_UART2_UUID)
uart2_read_characteristic = aioble.Characteristic(uart2_service, _ENV_UART_DATA2_UUID, read=True, notify=True)
uart2_write_characteristic = aioble.Characteristic(uart2_service, _ENV_BLE_DATA2_UUID, write=True, write_no_response=True)

aioble.register_services(device_info_service, uart_service, uart2_service)

messages = []

device_name = "esp32-energy" # TODO: Different simulation modes based on name, for example different charge/discharge curves and voltage levels.

percentage = 90
backlight_mode = 0 # NO, NC, AUTO = normally on, normally off, auto
full_battery_voltage = 20
low_voltage_alarm = 100
high_voltage_alarm = 300
over_current_alarm = 40
rated_capacity = 50 
under_battery_voltage = 50
device_address = 4

voltage = 720
capacity = 3000
temperature = 220
charge_energy = 2000
discharge_energy = 2000
current = 100

def set_backlight(mode : int):
    # My ESP32-WROOM board has a LED connector on pin 2:
    p = Pin(2, Pin.OUT)
    if mode == 0:
        p.on()
    else:
        p.off()

def calc_crc(data : bytes) -> int:
    crc = 255
    for x in data:
        crc -= x
    return crc & 0xFF

# This would be periodically polling a hardware sensor.
async def sensor_task():
    while True:
        if len(messages) > 0:
            message = messages.pop(0)
        else:
            message = 0x01
        if message == 0x01:
            # main display data:
            data = struct.pack(">HBBBHHHBHBHHB", 0xB55B, device_address, 0x01, percentage, capacity, voltage, current, charge_energy >> 16, charge_energy & 0xFFFF, discharge_energy >> 16, discharge_energy & 0xFFFF, temperature,33)
        elif message == 0x02:
            # config data:
            data = struct.pack(">HBBBHHHHHBBHBB", 0xB55B, device_address, 0x02, backlight_mode, full_battery_voltage, low_voltage_alarm, high_voltage_alarm, over_current_alarm, rated_capacity, 5, 3, under_battery_voltage, 2, 6)
        else:
            # set config:
            # B55B010A000000A83C
            data = struct.pack(">HBBHBB", 0xB55B, device_address, message, 0, 0, 0xA8) # sometimes 0xE8

        if data != None:
            data += bytes([calc_crc(data)])
            uart_data_characteristic.write(data, send_update=True)

            print ("".join(["%2.2x" % x for x in data]))

        await asyncio.sleep_ms(200)

def handle_message(data : bytes):
    global full_battery_voltage, percentage, backlight_mode, full_battery_voltage, low_voltage_alarm, high_voltage_alarm, over_current_alarm, rated_capacity, under_battery_voltage, device_address
    global voltage, capacity, temperature, charge_energy, discharge_energy, current, device_name
    
    if data != None and len(data) >= 5:
        crc = calc_crc(data[0:len(data)-1])
        magic,_,cmd = struct.unpack_from(">HBB", data, 0)
        buf_crc, = struct.unpack_from(">B", data, len(data)-1)
        if magic == 0xA55A and crc == buf_crc:
            # a55a000100000000ff -> sent on main screen
            # a55a000200000000fe -> sent on setup screen
            # a55a000300000000fd -> sent for callibration?
            if cmd >= 4:
                messages.extend([cmd, 2])
            else: 
                messages.append(cmd)
            short_val = struct.unpack_from(">H", data, 4)[0]
            byte_val = struct.unpack_from(">B", data, 4)[0]
            if cmd == 0x04:
                calibrating_current = short_val
                print ("calibrating current: %i" % calibrating_current)
            elif cmd == 0x05:
                calibrating_voltage = short_val
                print ("calibrating voltage: %i" % calibrating_voltage)
            elif cmd == 0x06:
                full_battery_voltage = short_val
                print("full battery voltage: %i" % full_battery_voltage)
            elif cmd == 0x07:
                low_voltage_alarm = short_val
                print ("low voltage alarm: %i" % low_voltage_alarm)
            elif cmd == 0x08:
                high_voltage_alarm = short_val
                print ("high voltage alarm: %i" % high_voltage_alarm)
            elif cmd == 0x09:
                over_current_alarm = short_val
                print ("over current alarm: %i" % over_current_alarm)
            elif cmd == 0x0A:
                rated_capacity = short_val
                print ("rated capacity: %i" % rated_capacity)
            elif cmd == 0x0B:
                percentage = byte_val
                print ("percentage: %i" % percentage)
            elif cmd == 0x0C:
                device_address = byte_val
                print ("device address: %i" % device_address)
            elif cmd == 0x0D:
                backlight_mode = byte_val
                print ("back light mode: %i" % backlight_mode)
                set_backlight(backlight_mode)
            elif cmd == 0x0E:
                under_battery_voltage = short_val
                print ("under battery voltage: %i" % under_battery_voltage)
        elif magic == 0xA55A and cmd == 0x10:
            messages.append(cmd)
            l = 0
            while data[4+l] != 0 and l < len(data) - 4:
                l += 1
            device_name = struct.unpack_from(">%is" % l, data, 4)[0]
            print ("name: %s" % device_name)

        print ("".join(["%2.2x" % x for x in data]))

async def config_task():
    while True:
        await ble_data_characteristic.written()
        data = ble_data_characteristic.read()
        handle_message(data)
        await asyncio.sleep_ms(500)
        
async def uart_config_task():
    while True:
        await uart_config_characteristic.written()
        data = uart_config_characteristic.read()

        print ("uart_config %s" % "".join(["%2.2x" % x for x in data]))

        await asyncio.sleep_ms(500)

# Serially wait for connections. Don't advertise while a central is connected.
async def peripheral_task():
    while True:
        async with await aioble.advertise(
            _ADV_INTERVAL_MS,
            name=device_name,
            # services=[_ENV_DEVICE_INFO_UUID, _ENV_UART_UUID, _ENV_UART2_UUID],
            appearance=_ADV_APPEARENCE_ENVIRONMENT_SENSOR,
            manufacturer=(0xca0c, bytes([0x31,0x00,0x00,0x00,0x00,0x00]))
        ) as connection:
            print("Connection from", connection.device)
            messages.extend([1,2])
            await connection.disconnected(timeout_ms=None)

# Run tasks.
async def main():
    t1 = asyncio.create_task(sensor_task())
    t2 = asyncio.create_task(peripheral_task())
    t3 = asyncio.create_task(config_task())
    t4 = asyncio.create_task(uart_config_task())
    await asyncio.gather(t1, t2, t3, t4)

set_backlight(backlight_mode)
asyncio.run(main())
