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

    def __init__(self) -> None:
        super().__init__()
        _LOGGER.warning("DobissCANConfigFlow 2")
        self.data: Dict[str, Any] = {}

    async def async_step_user(self, user_input=None):
        _LOGGER.warning("async_step_user %r %r", user_input, self.data)

        if user_input is not None:
            self.data.update(user_input)
            self.data[CONF_LIGHTS] = []
            return await self.async_step_light()

        return self.async_show_form(step_id="user", data_schema=CAN)

    async def async_step_light(self, user_input=None):
        _LOGGER.warning("async_step_light %r %r", user_input, self.data)

        if user_input is not None:
            cont = user_input.pop("add_another", False)

            self.data[CONF_LIGHTS].append(user_input)

            if not cont:
                # User is done adding lights, create the config entry.
                return self.async_create_entry(title="Dobiss Custom", data=self.data)

        return self.async_show_form(step_id="light", data_schema=ENTRY)
