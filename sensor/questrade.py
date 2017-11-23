"""
Stock quotes and other market data from Questrade API.
"""
import logging
import time

import voluptuous as vol

from homeassistant.const import ATTR_FRIENDLY_NAME, CONF_CURRENCY
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.helpers.entity import Entity
import homeassistant.helpers.config_validation as cv
from homeassistant.util.json import load_json, save_json

REQUIREMENTS = ['requests==2.18.4']

DEPENDENCIES = ['http']

_LOGGER = logging.getLogger(__name__)

QUESTRADE_CONFIG_PATH = 'questrade.conf'

CONF_CLIENT_ID = 'client_id'
CONF_REFRESH_TOKEN = 'refresh_token'

DEFAULT_CURRENCY = 'CAD'

ATTR_CASH = 'cash'
ATTR_MARKET_VALUE = 'market_value'
ATTR_TOTAL_EQUITY = 'total_equity'
ATTR_BUYING_POWER = 'buying_power'
ATTR_MAINTENANCE_EXCESS = 'maintenance_excess'

ICON = 'mdi:currency-usd'

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_CLIENT_ID): cv.string,
    vol.Required(CONF_REFRESH_TOKEN): cv.string,
    vol.Optional(CONF_CURRENCY): cv.string,
})


class QuestradeClient:
    def __init__(self, hass, client_id, token):
        self.hass = hass
        self._token = token

    def _request(self, resource):
        import requests
        if 'access_token' not in self._token:
            self._fetch_token(self._token)
        elif self._token.get('expires_at', 0) < time.time():
            self._fetch_token(self._token)
        base_url = self._token['api_server']
        url = base_url + 'v1/' + resource
        _LOGGER.info('Requesting %s', url)
        headers = {
            'Authorization': 'Bearer %s' % self._token['access_token']
        }
        return requests.get(url, headers=headers).json()

    def _fetch_token(self, token):
        import requests
        _LOGGER.info('Fetching new access token')
        refresh_url = 'https://login.questrade.com/oauth2/token'
        params = {
            'grant_type': 'refresh_token',
            'refresh_token': token['refresh_token'],
        }
        self._token = requests.get(refresh_url, params=params).json()
        self._token['expires_at'] = time.time() + self._token['expires_in']
        config_path = self.hass.config.path(QUESTRADE_CONFIG_PATH)
        save_json(config_path, self._token)

    def get_accounts(self):
        return self._request('accounts')

    def get_account_balances(self, account_id):
        return self._request('accounts/%s/balances' % account_id)


def setup_platform(hass, config, add_devices, discovery_info=None):
    client_id = config.get(CONF_CLIENT_ID)
    currency = config.get(CONF_CURRENCY, DEFAULT_CURRENCY)
    token = load_json(hass.config.path(QUESTRADE_CONFIG_PATH))
    if not token:
        token = {'refresh_token': config.get(CONF_REFRESH_TOKEN)}
    client = QuestradeClient(hass, client_id, token)
    response = client.get_accounts()
    accounts = [
        (account['number'], account['type'])
        for account in response['accounts']
        if account['status'] == 'Active'
    ]
    dev = []
    for account_id, name in accounts:
        dev.append(QuestradeSensor(client, account_id, name, currency))
    add_devices(dev, True)


class QuestradeSensor(Entity):
    def __init__(self, questrade_client, account_id, name, currency):
        self._client = questrade_client
        self._name = name
        self.account_id = account_id
        self.currency = currency
        self.cash = None
        self.market_value = None
        self.total_equity = None
        self.buying_power = None
        self.maintenance_excess = None

    @property
    def name(self):
        return 'questrade_%s' % self.account_id

    @property
    def unit_of_measurement(self):
        return self.currency

    @property
    def state(self):
        if self.total_equity is None:
            return 0
        return self.total_equity

    @property
    def device_state_attributes(self):
        return {
            ATTR_CASH: self.cash,
            ATTR_MARKET_VALUE: self.market_value,
            ATTR_TOTAL_EQUITY: self.total_equity,
            ATTR_BUYING_POWER: self.buying_power,
            ATTR_MAINTENANCE_EXCESS: self.maintenance_excess,
            ATTR_FRIENDLY_NAME: self._name,
        }

    @property
    def icon(self):
        return ICON

    def update(self):
        response = self._client.get_account_balances(self.account_id)
        balances = response['combinedBalances']
        for balance in balances:
            if balance['currency'] != self.currency:
                continue
            self.cash = balance['cash']
            self.market_value = balance['marketValue']
            self.total_equity = balance['totalEquity']
            self.buying_power = balance['buyingPower']
            self.maintenance_excess = balance['maintenanceExcess']
