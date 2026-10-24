import logging
from typing import Any, Dict, Optional

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_LIGHTS, CONF_NAME

from .const import *


_LOGGER = logging.getLogger(DOMAIN)
_LOGGER.setLevel(logging.DEBUG)


CAN = vol.Schema({
    vol.Optional(CONF_INTERFACE, default="socketcan"): cv.string,
    vol.Optional(CONF_CHANNEL, default="can0"): cv.string,
})

ENTRY = vol.Schema({
    vol.Required(CONF_NAME): cv.string,
    vol.Required(CONF_MODULE, default=1): cv.positive_int,
    vol.Required(CONF_RELAY, default=0): cv.positive_int,
    vol.Optional("add_another", default=True): cv.boolean,
})


class DobissCANConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """DobissCAN config flow."""

    VERSION = 1

    def __init__(self) -> None:
        super().__init__()
        self._data: Dict[str, Any] = {}

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            self._data.update(user_input)
            self._data[CONF_LIGHTS] = []
            return await self.async_step_light()

        return self.async_show_form(step_id="user", data_schema=CAN)

    async def async_step_light(self, user_input=None):
        if user_input is not None:
            user_input = dict(user_input)
            cont = user_input.pop("add_another", False)

            self._data[CONF_LIGHTS].append(user_input)

            if not cont:
                # User is done adding lights, create the config entry.
                return self.async_create_entry(title="Dobiss Custom", data=self._data)

        return self.async_show_form(step_id="light", data_schema=ENTRY)
