"""
Dobiss CAN bus light integration
Documentation of protocol: https://gist.github.com/dries007/436fcd0549a52f26137bca942fef771a
The CAN bus must be enabled by the system before this module is loaded.
systemd-networkd can do this for you, as CAN is a supported network.

Author: Dries007 2021 - 2022
Licence: MIT
"""
import asyncio
import logging
from typing import Any

import can
from homeassistant.components.light import LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_LIGHTS, CONF_NAME, EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import *


_LOGGER = logging.getLogger(DOMAIN)
_LOGGER.setLevel(logging.DEBUG)


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    data = hass.data[DOMAIN][config_entry.entry_id]
    _LOGGER.debug('async_setup_entry %r %r', data, config_entry)

    # Load CAN bus. Must be operational already (done by external network tool).
    # Setting bitrate might work, but ideally that should also be set already.
    # We only care about messages related to feedback from a SET command or the reply from a GET command.
    bus = can.Bus(bustype=data[CONF_INTERFACE], channel=data[CONF_CHANNEL], bitrate=125000, receive_own_messages=True, can_filters=[
        {"can_id": 0x0002FF01, "can_mask": 0x1FFFFFFF, "extended": True},  # Reply to SET
        {"can_id": 0x01FDFF01, "can_mask": 0x1FFFFFFF, "extended": True},  # Reply to GET
    ])

    # Global CAN bus lock, required since the reply to a GET does not include any differentiator.
    # This means we must lock, then send out a GET request.
    # The reply will then only be acked by the entity that holds the lock.
    # I don't like this, it smells, but it works and IDK how to do it better.
    lock = asyncio.Lock()

    entities = [DobissLight(bus, e, lock, config_entry.entry_id) for e in data[CONF_LIGHTS]]
    notifier = can.Notifier(bus, [e.on_can_message_received for e in entities], loop=asyncio.get_running_loop())
    async_add_entities(entities)

    @callback
    def stop(event):
        notifier.stop()
        bus.shutdown()

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, stop)


# noinspection PyAbstractClass
class DobissLight(LightEntity):
    _attr_has_entity_name = True
    _attr_name = None

    @property
    def device_info(self):
        return {
            "identifiers": {
                (DOMAIN, self.unique_id)
            },
            "name": self._name,
        }

    def __init__(self, bus: can.BusABC, o: dict, lock: asyncio.Lock, prefix: str):
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
        self._log = _LOGGER.getChild(self._name)
        self._attr_unique_id = f"dobiss.{prefix}.{self._module}.{self._relay}"

    @property
    def is_on(self) -> bool:
        return self._is_on

    @is_on.setter
    def is_on(self, value: bool):
        self._is_on = value
        # This call makes HA update the internal state after getting an update via CAN.
        self.async_write_ha_state()

    @property
    def unique_id(self) -> str:
        return self._attr_unique_id

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._bus.send(can.Message(arbitration_id=self._set_id, data=self._bytes_on, is_extended_id=True), timeout=.1)

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._bus.send(can.Message(arbitration_id=self._set_id, data=self._bytes_off, is_extended_id=True), timeout=.1)

    def on_can_message_received(self, msg: can.Message):
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
            try:
                # Inform handler that we expect an update.
                self._awaiting_update = True
                # Small delay, otherwise we overload the CAN module.
                await asyncio.sleep(.01)
                # Ask CAN module for an update
                self._bus.send(can.Message(arbitration_id=0x01FCFF01, data=self._bytes_status, is_extended_id=True), timeout=.1)
                # Wait for reply to come
                await asyncio.wait_for(self._event_update.wait(), 0.5)
                # Small delay, otherwise we overload the CAN module.
                await asyncio.sleep(.01)
            finally:
                # In all cases, no matter how we get out of this, we must unset the _awaiting_update flag.
                self._awaiting_update = False
