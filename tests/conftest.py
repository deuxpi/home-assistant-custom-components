import os

import pytest

from homeassistant import auth, core as ha
from homeassistant.auth import auth_store


def get_test_config_dir():
    return os.path.join(os.path.dirname(__file__), 'testing_config')


async def async_test_home_assistant(loop):
    hass = ha.HomeAssistant(loop)
    store = auth_store.AuthStore(hass)
    hass.auth = auth.AuthManager(hass, store, {}, {})
    hass.config.config_dir = get_test_config_dir()
    return hass


@pytest.fixture
def hass(loop):
    hass = loop.run_until_complete(async_test_home_assistant(loop))

    yield hass

    loop.run_until_complete(hass.async_stop(force=True))
