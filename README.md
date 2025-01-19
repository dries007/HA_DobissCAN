# Home Assistant DobissCAN

Home Assistant custom component for Dobiss via CAN bus controls.

This project is tested with the Waveshare RS485 CAN HAT and a Dobiss Ambiance Pro system without a CAN programmer present.

The integration currently only supports lights. In theory this should be easy to adjust to more general toggleable devices, or even dimmers.

## Hardware

The project requires that your Home Assistant installation has a functional CAN bus interface connected to the CAN bus of your Dobiss installation.

When using a Raspberry Pi I recommend either a USB to CAN adapter or a CAN HAT.

The CAN bus goes over the black RJ12 connector in the center of the unit, make sure you disable the terminator resistor if you add a cable. You can use an RJ11 (telephone) cable as well, since you only need 3 conductors and the outermost pins are not used.

This is the pinout for an RJ12 cable:

3. CAN H
4. GND (don't forget!)
5. CAN L

This is how to count:

![Pinout of the RJ12 cable](https://github.com/tvdbroeck/HA_DobissCAN/blob/main/pinout%20RJ12.png)

In my setup, I connected these via an unshielded hand twisted cable to the CAN screw terminals of a RS485/CAN HAT from Waveshare + I tried to ground to one of the GND pins of the Pi's GPIO connector.

The CAN bus speed is 125kbit/s (sometimes known as "low speed can").
You must set up your Pi's OS to configure the bus correctly. As CAN is a network protocol, there are a few options but this generally works:

```
# ip link set can0 type can bitrate 125000
# ip link set can0 up
```

These steps must be run every reboot, so I suggest adding them to a script that runs at startup time. 
If you are using Home Assistant OS, you can use [this addon](https://github.com/dries007/HA_EnableCAN).

The Dobiss protocol is explained more [here](https://gist.github.com/dries007/436fcd0549a52f26137bca942fef771a).

## Software

This is an addon for Home Assistant in the form of a custom component that can be installed via [HACS](https://hacs.xyz/).

If you are using a Home Assistant Operating System installation and you are using a CAN hat that requires you add lines to your /boot/config.txt, you may need to [log into the OS](https://developers.home-assistant.io/docs/operating-system/debugging/).

The lines that need to be added to the config.txt file can be found on the website of the manufacturer of your CAN adapter. If you are using the Waveshare RS485 CAN HAT, for example, the following lines need to be added:
```
dtparam=spi=on
dtoverlay=mcp2515-can0,oscillator=12000000,interrupt=25,spimaxfrequency=2000000
```
