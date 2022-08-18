"""
Dobiss CAN Bus Integration
"""
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import *


_LOGGER = logging.getLogger(DOMAIN)
_LOGGER.setLevel(logging.DEBUG)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    _LOGGER.debug("async_setup_entry2 %r %r", entry, entry.data)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = entry.data

    # Forward the setup to the sensor platform.
    hass.async_create_task(hass.config_entries.async_forward_entry_setup(entry, "light"))
    return True
