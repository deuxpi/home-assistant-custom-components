"""Home Assistant component for Strava athlete activity statistics."""
import asyncio
from datetime import timedelta
import json
import logging
import os

from aiohttp import web
import voluptuous as vol

from homeassistant.components.http import HomeAssistantView
from homeassistant.components.sensor import (
    ENTITY_ID_FORMAT, PLATFORM_SCHEMA)
from homeassistant.const import LENGTH_METERS
from homeassistant.core import callback
from homeassistant.helpers.entity import Entity, async_generate_entity_id
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.typing import HomeAssistantType

REQUIREMENTS = ['stravalib==0.9.1']
DEPENDENCIES = ['http']

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=3600)

CONF_CLIENT_ID = 'client_id'
CONF_CLIENT_SECRET = 'client_secret'

STRAVA_CONFIG_PATH = 'strava.json'

DATA_CALLBACK = 'strava-callback'

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_CLIENT_ID): cv.string,
    vol.Required(CONF_CLIENT_SECRET): cv.string,
})

ICON_RIDE = 'mdi:bike'
ICON_RUN = 'mdi:run'
ICON_SWIM = 'mdi:swim'

ATTR_YTD_RUN_DISTANCE = 'ytd_run_distance'


@asyncio.coroutine
def async_setup_platform(hass, config, async_add_devices, discovery_info=None):
    """Authenticate to the Strava API."""
    from stravalib.client import Client

    hass.http.register_view(StravaAuthCallbackView())

    client_id = config.get(CONF_CLIENT_ID)
    client_secret = config.get(CONF_CLIENT_SECRET)

    client = Client()

    config_path = hass.config.path(STRAVA_CONFIG_PATH)

    @asyncio.coroutine
    def _read_config():
        if not os.path.isfile(config_path):
            return None
        with open(config_path, 'r') as auth_file:
            config = json.load(auth_file)
            if config['client_id'] == client_id:
                return config['access_token']

    @asyncio.coroutine
    def _write_config():
        with open(config_path, 'w') as auth_file:
            json.dump({
                'client_id': client_id,
                'access_token': client.access_token,
            }, auth_file)

    @asyncio.coroutine
    def _add_device():
        strava = StravaSensor(hass, client)
        yield from strava.async_update()
        return async_add_devices([strava])

    access_token = yield from _read_config()
    if access_token is not None:
        client.access_token = access_token
        yield from _add_device()
    else:
        callback_url = '{}{}'.format(
            hass.config.api.base_url, StravaAuthCallbackView.url)
        authorize_url = client.authorization_url(
            client_id=client_id, redirect_uri=callback_url)

        configurator = hass.components.configurator
        request_id = configurator.async_request_config(
            'Strava',
            description='Authorization required for Strava account.',
            link_name='Authorize Home Assistant',
            link_url=authorize_url,
            entity_picture='/local/images/logo_strava.png')

    @asyncio.coroutine
    def initialize_callback(code):
        """Handle OAuth callback from Strava authorization flow."""
        client.access_token = client.exchange_code_for_token(
            client_id=client_id, client_secret=client_secret, code=code)
        yield from _write_config()
        yield from _add_device()
        configurator.async_request_done(request_id)

    hass.data[DATA_CALLBACK] = initialize_callback
    return True


class StravaAuthCallbackView(HomeAssistantView):
    """Web view that handles OAuth authentication and redirection flow."""
    requires_auth = False
    url = '/api/strava/callback'
    name = 'api:strava:callback'

    @callback
    def get(self, request):  # pylint: disable=no-self-use
        """Handle browser HTTP request."""
        hass = request.app['hass']
        params = request.query
        response = web.HTTPFound('/states')

        if 'code' not in params:
            _LOGGER.error(
                'Error authorizing Strava: %s',
                params.get('error', 'invalid response'))
        elif DATA_CALLBACK not in hass.data:
            _LOGGER.error('Configuration request not found')
        else:
            code = params['code']
            initialize_callback = hass.data[DATA_CALLBACK]
            hass.async_add_job(initialize_callback(code))

        return response


class StravaSensor(Entity):
    """Sensor component for Strava athlete activity statistics."""
    def __init__(self, hass: HomeAssistantType, strava_client):
        self.hass = hass
        self._client = strava_client
        self._stats = None

        athlete = self._client.get_athlete()
        self._name = '{} {}'.format(athlete.firstname, athlete.lastname)
        self.athlete_id = athlete.id
        self.entity_id = async_generate_entity_id(
            ENTITY_ID_FORMAT, 'strava_{}'.format(self.athlete_id), hass=hass)

    @property
    def name(self):
        return self._name

    @property
    def icon(self):
        return ICON_RUN

    @property
    def unit_of_measurement(self):
        return LENGTH_METERS

    @property
    def state(self):
        if self._stats is None:
            return 0
        return self._stats.ytd_run_totals.distance.num

    @property
    def device_state_attributes(self):
        """Return the athete stats attributes."""
        attributes = {}
        if self._stats is not None:
            attributes.update({
                ATTR_YTD_RUN_DISTANCE: self._stats.ytd_run_totals.distance.num,
            })
        return attributes

    @asyncio.coroutine
    def async_fetch_stats(self):
        """Fetch athlete statistics from Strava."""
        return self.hass.async_add_job(
            self._client.get_athlete_stats, self.athlete_id)

    @asyncio.coroutine
    def async_update(self):
        """Update current athlete statistics."""
        self._stats = yield from self.async_fetch_stats()
