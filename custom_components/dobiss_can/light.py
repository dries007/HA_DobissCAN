"""
Dobiss CAN bus light integration
Documentation of protocol: https://gist.github.com/dries007/436fcd0549a52f26137bca942fef771a
The CAN bus must be enabled by the system before this module is loaded.
systemd-networkd can do this for you, as CAN is a supported network.

Author: Dries007 - 2021
Licence: MIT
"""
import asyncio
import logging
from typing import Any

import can
import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components.light import LightEntity, PLATFORM_SCHEMA
from homeassistant.const import CONF_HOST, CONF_LIGHTS, CONF_NAME
from homeassistant.core import HomeAssistant


_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.DEBUG)

CONF_BUSTYPE = 'bustype'
CONF_MODULE = 'module'
CONF_RELAY = 'relay'

"""
light:
  - platform: dobiss_can
    lights:
      - name: WC
        module: 1
        relay: 0
      - name: Bedroom
        module: 1
        relay: 1
"""
PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional(CONF_HOST, default="can0"): cv.string,
    vol.Optional(CONF_BUSTYPE, default="socketcan"): cv.string,
    vol.Required(CONF_LIGHTS): vol.All(cv.ensure_list, [vol.Schema({
        vol.Required(CONF_NAME): cv.string,
        vol.Required(CONF_MODULE): cv.positive_int,
        vol.Required(CONF_RELAY): cv.positive_int,
    })]),
})


async def async_setup_platform(hass: HomeAssistant, config, async_add_entities, discovery_info=None):
    # Load CAN bus. Must be operational already (done by external network tool).
    # Setting bitrate might work, but ideally that should also be set already.
    # We only care about messages related to feedback from a SET command or the reply from a GET command.
    bus = can.Bus(channel=config[CONF_HOST], bustype=config[CONF_BUSTYPE], bitrate=125000, receive_own_messages=False, can_filters=[
        {"can_id": 0x0002FF01, "can_mask": 0x1FFFFFFF, "extended": True},  # Reply to SET
        {"can_id": 0x01FDFF01, "can_mask": 0x1FFFFFFF, "extended": True},  # Reply to GET
    ])
    # Global CAN bus lock, required since the reply to a GET does not include any differentiator.
    lock = asyncio.Lock(loop=hass.loop)

    # All config entries get turned into entities that listen for updates on the bus.
    entities = [DobissLight(bus, o, lock) for o in config[CONF_LIGHTS]]
    can.Notifier(bus, entities, loop=hass.loop)
    async_add_entities(entities)

    # Success.
    return True


class DobissLight(LightEntity, can.Listener):
    def __init__(self, bus: can.BusABC, o: dict, lock: asyncio.Lock):
        self._bus = bus
        self._lock = lock
        # Unpack some config values
        self._name: str = o[CONF_NAME]
        self._module = o[CONF_MODULE]
        self._relay = o[CONF_RELAY]
        # Prepare fixed ids & payloads
        self._set_id: int = 0x01FC0002 | (self._module << 8)
        self._bytes_off: bytes = bytes((self._module, self._relay, 0, 0xFF, 0xFF))
        self._bytes_on: bytes = bytes((self._module, self._relay, 1, 0xFF, 0xFF))
        self._bytes_status: bytes = bytes((self._module, self._relay))
        # Internal state of light
        self._is_on: bool = False
        # Internals to do locking & support GET operation
        self._awaiting_update = False
        self._event_update = asyncio.Event()
        # Logger
        self._log = _LOGGER.getChild(self.name)

    @property
    def name(self) -> str:
        return self._name

    @property
    def is_on(self) -> bool:
        return self._is_on

    @is_on.setter
    def is_on(self, value: bool):
        self._is_on = value
        # This call makes HA update the internal state after getting an update via CAN.
        self.hass.async_add_job(self.async_update_ha_state)

    @property
    def unique_id(self) -> str:
        return f"dobiss.{self._module}.{self._relay}"

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._bus.send(can.Message(arbitration_id=self._set_id, data=self._bytes_on, is_extended_id=True), timeout=.1)

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._bus.send(can.Message(arbitration_id=self._set_id, data=self._bytes_off, is_extended_id=True), timeout=.1)

    async def on_message_received(self, msg):
        # Reply to SET, this we can filter because data contains data from.
        if msg.arbitration_id == 0x0002FF01 and msg.data[0] == self._module and msg.data[1] == self._relay:
            self.is_on = msg.data[2] == 1
        # Reply to GET, this we can only filter by _knowing_ that we are waiting on an update.
        if msg.arbitration_id == 0x01FDFF01 and self._awaiting_update:
            self.is_on = msg.data[0] == 1
            self._event_update.set()

    async def async_update(self):
        # The update cycle must be blocked on the CAN bus lock.
        async with self._lock:
            # Inform handler that we expect an update.
            self._awaiting_update = True
            # Small delay, otherwise we overload the CAN module.
            await asyncio.sleep(.01)
            # Ask CAN module for an update
            self._bus.send(can.Message(arbitration_id=0x01FCFF01, data=self._bytes_status, is_extended_id=True), timeout=.1)
            # Wait for reply to come
            await self._event_update.wait()
            # Small delay, otherwise we overload the CAN module.
            await asyncio.sleep(.01)
            # OK, we're done.
            self._awaiting_update = False
