"""Support for Nokia Health measurements."""
import asyncio
import datetime
import json
import logging
import os

from aiohttp import web
import voluptuous as vol

from homeassistant.components.http import HomeAssistantView
from homeassistant.components.sensor import ENTITY_ID_FORMAT, PLATFORM_SCHEMA
from homeassistant.const import MASS_KILOGRAMS
from homeassistant.core import callback
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import Entity, async_generate_entity_id
from homeassistant.helpers.typing import HomeAssistantType

REQUIREMENTS = ['nokia==0.4.0']
DEPENDENCIES = ['http']

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = datetime.timedelta(minutes=30)

CONF_CONSUMER_KEY = 'consumer_key'
CONF_CONSUMER_SECRET = 'consumer_secret'

NOKIA_CONFIG_PATH = 'nokia.json'

DATA_CALLBACK = 'nokia-callback'

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_CONSUMER_KEY): cv.string,
    vol.Required(CONF_CONSUMER_SECRET): cv.string,
})

ATTR_WEIGHT = 'weight'
ATTR_FAT_RATIO = 'fat_ratio'
ATTR_MUSCLE_MASS = 'muscle_mass'
ATTR_HYDRATION = 'hydration'
ATTR_BONE_MASS = 'bone_mass'


@asyncio.coroutine
def async_setup_platform(hass, config, async_add_devices, discovery_info=None):
    """Authenticate to the Nokia Health API."""
    from nokia import NokiaApi, NokiaAuth, NokiaCredentials

    hass.http.register_view(NokiaAuthCallbackView())

    consumer_key = config.get(CONF_CONSUMER_KEY)
    consumer_secret = config.get(CONF_CONSUMER_SECRET)

    config_path = hass.config.path(NOKIA_CONFIG_PATH)

    @asyncio.coroutine
    def _read_config():
        if not os.path.isfile(config_path):
            return None
        with open(config_path, 'r') as auth_file:
            config = json.load(auth_file)
            if config['consumer_key'] == consumer_key:
                return config

    @asyncio.coroutine
    def _write_config(creds):
        with open(config_path, 'w') as auth_file:
            json.dump({
                'consumer_key': consumer_key,
                'access_token': creds.access_token,
                'access_token_secret': creds.access_token_secret,
                'user_id': creds.user_id,
            }, auth_file)

    @asyncio.coroutine
    def _add_device(creds):
        client = NokiaApi(creds)
        nokia = NokiaSensor(hass, client)
        yield from nokia.async_update()
        return async_add_devices([nokia])

    config = yield from _read_config()
    if config is not None:
        creds = NokiaCredentials(
            config['access_token'],
            config['access_token_secret'],
            consumer_key,
            consumer_secret,
            config['user_id']
        )
        yield from _add_device(creds)
    else:
        auth = NokiaAuth(consumer_key, consumer_secret)
        callback_uri = '{}{}'.format(
            hass.config.api.base_url, NokiaAuthCallbackView.url)
        authorize_url = auth.get_authorize_url(callback_uri=callback_uri)

        configurator = hass.components.configurator
        request_id = configurator.async_request_config(
            "Nokia Health",
            description="Authorization required for Nokia Health account.",
            link_name="Authorize Home Assistant",
            link_url=authorize_url,
            entity_picture='/local/images/logo_nokia_health_mate.png')

    @asyncio.coroutine
    def initialize_callback(oauth_verifier):
        """Handle OAuth callback from Nokia authorization flow."""
        creds = auth.get_credentials(oauth_verifier)
        yield from _write_config(creds)
        yield from _add_device(creds)
        configurator.async_request_done(request_id)

    hass.data[DATA_CALLBACK] = initialize_callback
    return True


class NokiaAuthCallbackView(HomeAssistantView):
    """Web view that handles OAuth authentication and redirection flow."""

    requires_auth = False
    url = '/api/nokia/callback'
    name = 'api:nokia:callback'

    @callback
    def get(self, request):  # pylint: disable=no-self-use
        """Handle browser HTTP request."""
        hass = request.app['hass']
        params = request.query
        response = web.HTTPFound('/states')

        if 'oauth_verifier' not in params:
            _LOGGER.error(
                "Error authorizing to Nokia Health: %s",
                params.get('error', 'invalid response'))
        elif DATA_CALLBACK not in hass.data:
            _LOGGER.error("Configuration request not found")
        else:
            oauth_verifier = params['oauth_verifier']
            initialize_callback = hass.data[DATA_CALLBACK]
            hass.async_add_job(initialize_callback(oauth_verifier))

        return response


class NokiaSensor(Entity):
    """Sensor component for Nokia Health measurements."""

    def __init__(self, hass: HomeAssistantType, nokia_client):
        """Initialize the Nokia Health sensor."""
        self.hass = hass
        self._client = nokia_client
        self._measures = None

        user_id = self._client.credentials.user_id
        user = self._client.get_user()['users'][0]
        self._name = '{} {}'.format(user['firstname'], user['lastname'])
        self.entity_id = async_generate_entity_id(
            ENTITY_ID_FORMAT, 'nokia_{}'.format(user_id), hass=hass)

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def icon(self):
        """Return the icon that will be shown in the interface."""
        return 'mdi:human'

    @property
    def unit_of_measurement(self):
        """Return the unit appended to the state value in the interface."""
        return MASS_KILOGRAMS

    @property
    def state(self):
        """Return the measurement from the sensor."""
        if self._measures is None:
            return 0
        return self._measures.weight

    @property
    def device_state_attributes(self):
        """Return the measurement attributes."""
        attributes = {}
        if self._measures is not None:
            attributes.update({
                ATTR_WEIGHT: self._measures.weight,
                ATTR_FAT_RATIO: self._measures.fat_ratio,
                # ATTR_MUSCLE_MASS: self._measures.muscle_mass,
                # ATTR_HYDRATION: self._measures.hydration,
                # ATTR_BONE_MASS: self._measures.bone_mass,
            })
        return attributes

    @asyncio.coroutine
    def async_get_measures(self):
        """Fetch measurements from Nokia Health."""
        return self.hass.async_add_job(self._client.get_measures)

    @asyncio.coroutine
    def async_update(self):
        """Get the latest measurements from the Nokia Health API."""
        self._measures = (yield from self.async_get_measures())[0]
