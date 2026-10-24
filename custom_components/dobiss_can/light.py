"""
Dobiss CAN bus light integration
Documentation of protocol: https://gist.github.com/dries007/436fcd0549a52f26137bca942fef771a
The CAN bus must be enabled by the system before this module is loaded.
systemd-networkd can do this for you, as CAN is a supported network.

Author: Dries007 2021 - 2022 - 2025
Licence: MIT
"""
import asyncio
import logging
from typing import Any

import can
from homeassistant.components.light import ColorMode, LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import *


_LOGGER = logging.getLogger(DOMAIN)
_LOGGER.setLevel(logging.DEBUG)


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    data = hass.data[DOMAIN][config_entry.entry_id]
    _LOGGER.debug('async_setup_entry %r %r', data, config_entry)

    def _make_bus():
        return can.Bus(interface=data[CONF_INTERFACE], channel=data[CONF_CHANNEL], bitrate=125000, receive_own_messages=True, can_filters=[
            {"can_id": 0x0002FF01, "can_mask": 0x1FFFFFFF, "extended": True},  # Reply to SET
            {"can_id": 0x01FDFF01, "can_mask": 0x1FFFFFFF, "extended": True},  # Reply to GET
        ])

    bus = await hass.async_add_executor_job(_make_bus)

    # Global CAN bus lock, required since the reply to a GET does not include any differentiator.
    # This means we must lock, then send out a GET request.
    # The reply will then only be acked by the entity that holds the lock.
    # I don't like this, it smells, but it works and IDK how to do it better.
    lock = asyncio.Lock()

    entities = [DobissLight(bus, e, lock, config_entry.entry_id) for e in data[CONF_LIGHTS]]
    notifier = can.Notifier(bus, [e.on_can_message_received for e in entities], loop=asyncio.get_running_loop())
    async_add_entities(entities)

    @callback
    def stop(event=None):
        notifier.stop()
        bus.shutdown()

    config_entry.async_on_unload(stop)
    config_entry.async_on_unload(hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, stop))


# noinspection PyAbstractClass
class DobissLight(LightEntity):
    _attr_has_entity_name = True
    _attr_name = None
    _attr_color_mode = ColorMode.ONOFF
    _attr_supported_color_modes = {ColorMode.ONOFF}
    _attr_is_on = False

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

    def _set_state(self, value: bool):
        self._attr_is_on = value
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.hass.async_add_executor_job(self._send, self._set_id, self._bytes_on)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.hass.async_add_executor_job(self._send, self._set_id, self._bytes_off)

    def _send(self, arb_id: int, data: bytes) -> None:
        self._bus.send(can.Message(arbitration_id=arb_id, data=data, is_extended_id=True), timeout=.1)

    def on_can_message_received(self, msg: can.Message):
        if self.hass is None:
            return
        if msg.arbitration_id == 0x0002FF01 and msg.data[0] == self._module and msg.data[1] == self._relay:
            self._set_state(msg.data[2] == 1)
        if msg.arbitration_id == 0x01FDFF01 and self._awaiting_update:
            self._set_state(msg.data[0] == 1)
            self._event_update.set()

    async def async_update(self):
        async with self._lock:
            try:
                self._event_update.clear()
                self._awaiting_update = True
                await asyncio.sleep(.01)
                await self.hass.async_add_executor_job(self._send, 0x01FCFF01, self._bytes_status)
                await asyncio.wait_for(self._event_update.wait(), 0.5)
                await asyncio.sleep(.01)
            except asyncio.TimeoutError:
                self._log.debug("Timeout waiting for status reply")
            finally:
                self._awaiting_update = False
