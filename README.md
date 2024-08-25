# Bluetooth Energy Monitor client
This is the result of my investigations into the WLS-MVAxxx battery monitor devices. They have a Bluetooth interface, which is provided by a CH9141 Bluetooth to serial bridge.

So far the result are two python scripts:

## sensor.py
This is an emulator of the protocol to test host software (and the original Android client) against.
You can run this in Thonny on a controller of your choice (I'm using an Wemos D1 Mini ESP32 – ESP-WROOM board) and see the comunication with a host application.

## host.py
This is a simple command line client to read data and modify the configuration.

# BTW, why does Bluetooth on Android require the "location" permission?
I was wondering about that. Scanning for Bluetooth devices could be used to estimate the user's position, by triangulating
against the signal strength and MAC of several devices. So while "normal" apps won't make actual use of this, it is there as a warning.

# Hardware notes:
|  |IC       |                        |
|--|---------|------------------------|
|U2|TM1622   |LCD driver                |
|U1|MS51FC0AE|8051 based microcontroller|
|U1|CH9141K  |UART to BLE bridge        |

