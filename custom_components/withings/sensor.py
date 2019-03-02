"""Support for Withings measurements."""
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

REQUIREMENTS = ['nokia==1.2.0']
DEPENDENCIES = ['http']

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = datetime.timedelta(minutes=30)

CONF_CLIENT_ID = 'client_id'
CONF_CONSUMER_SECRET = 'consumer_secret'

WITHINGS_CONFIG_PATH = 'withings.json'

DATA_CALLBACK = 'withings-callback'

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_CLIENT_ID): cv.string,
    vol.Required(CONF_CONSUMER_SECRET): cv.string,
})

ATTR_WEIGHT = 'weight'
ATTR_HEIGHT = 'height'
ATTR_FAT_FREE_MASS = 'fat_free_mass'
ATTR_FAT_RATIO = 'fat_ratio'
ATTR_FAT_MASS_WEIGHT = 'fat_mass_weight'
ATTR_DIASTOLIC_BLOOD_PRESSURE = 'diastolic_blood_pressure'
ATTR_SYSSTOLIC_BLOOD_PRESSURE = 'sysstolic_blood_pressure'
ATTR_HEART_PULSE = 'heart_pulse'
ATTR_TEMPERATURE = 'temperature'
ATTR_SPO2 = 'spo2'
ATTR_BODY_TEMPERATURE = 'body_temperature'
ATTR_SKIN_TEMPERATURE = 'skin_temperature'
ATTR_MUSCLE_MASS = 'muscle_mass'
ATTR_HYDRATION = 'hydration'
ATTR_BONE_MASS = 'bone_mass'
ATTR_PULSE_WAVE_VELOCITY = 'pulse_wave_velocity'


@asyncio.coroutine
def async_setup_platform(hass, config, async_add_devices, discovery_info=None):
    """Authenticate to the Withings API."""
    from nokia import NokiaApi, NokiaAuth, NokiaCredentials

    hass.http.register_view(WithingsAuthCallbackView())

    client_id = config.get(CONF_CLIENT_ID)
    consumer_secret = config.get(CONF_CONSUMER_SECRET)

    config_path = hass.config.path(WITHINGS_CONFIG_PATH)

    @asyncio.coroutine
    def _read_config():
        if not os.path.isfile(config_path):
            return None
        with open(config_path, 'r') as auth_file:
            config = json.load(auth_file)
            if config.get('client_id') == client_id:
                return config

    @asyncio.coroutine
    def _write_config(creds):
        with open(config_path, 'w') as auth_file:
            json.dump({
                'client_id': client_id,
                'access_token': creds.access_token,
                'refresh_token': creds.refresh_token,
                'token_type': creds.token_type,
                'token_expiry': creds.token_expiry,
                'user_id': creds.user_id,
            }, auth_file)

    @asyncio.coroutine
    def _add_device(creds):
        client = NokiaApi(creds)
        withings = WithingsSensor(hass, client)
        yield from withings.async_update()
        return async_add_devices([withings])

    config = yield from _read_config()
    if config is not None:
        creds = NokiaCredentials(
            client_id=client_id,
            consumer_secret=consumer_secret,
            access_token=config['access_token'],
            token_expiry=config['token_expiry'],
            token_type=config['token_type'],
            refresh_token=['refresh_token'],
            user_id=config['user_id']
        )
        yield from _add_device(creds)
    else:
        callback_uri = '{}{}'.format(
            hass.config.api.base_url, WithingsAuthCallbackView.url)
        auth = NokiaAuth(
            client_id,
            consumer_secret,
            callback_uri=callback_uri,
            scope='user.info,user.metrics,user.activity'
        )
        authorize_url = auth.get_authorize_url()

        configurator = hass.components.configurator
        request_id = configurator.async_request_config(
            "Withings",
            description="Authorization required for Withings account.",
            link_name="Authorize Home Assistant",
            link_url=authorize_url,
            entity_picture='/local/images/logo_nokia_health_mate.png')

    @asyncio.coroutine
    def initialize_callback(code):
        """Handle OAuth callback from Withings authorization flow."""
        creds = auth.get_credentials(code)
        yield from _write_config(creds)
        yield from _add_device(creds)
        configurator.async_request_done(request_id)

    hass.data[DATA_CALLBACK] = initialize_callback
    return True


class WithingsAuthCallbackView(HomeAssistantView):
    """Web view that handles OAuth authentication and redirection flow."""

    requires_auth = False
    url = '/api/withings/callback'
    name = 'api:withings:callback'

    @callback
    def get(self, request):  # pylint: disable=no-self-use
        """Handle browser HTTP request."""
        hass = request.app['hass']
        params = request.query
        response = web.HTTPFound('/states')

        if 'code' not in params:
            _LOGGER.error(
                "Error authorizing to Withings: %s",
                params.get('error', 'invalid response'))
        elif DATA_CALLBACK not in hass.data:
            _LOGGER.error("Configuration request not found")
        else:
            _LOGGER.debug('Params: {}'.format(params))
            code = params['code']
            initialize_callback = hass.data[DATA_CALLBACK]
            hass.async_add_job(initialize_callback(code))

        return response


class WithingsSensor(Entity):
    """Sensor component for Withings measurements."""

    def __init__(self, hass: HomeAssistantType, withings_client):
        """Initialize the Withings sensor."""
        self.hass = hass
        self._client = withings_client
        self._measures = None

        r = self._client.request('user', 'getdevice', version='v2')
        device = r['devices'][0]
        self._name = device['model']
        self.entity_id = async_generate_entity_id(
            ENTITY_ID_FORMAT,
            'withings_{}'.format(device['deviceid']),
            hass=hass
        )

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
        """Fetch measurements from Withings."""
        return self.hass.async_add_job(self._client.get_measures)

    @asyncio.coroutine
    def async_update(self):
        """Get the latest measurements from the Withings API."""
        self._measures = (yield from self.async_get_measures())[0]
