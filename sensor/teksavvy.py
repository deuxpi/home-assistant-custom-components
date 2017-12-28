"""
Data usage from the Teksavvy API.
"""
import logging

import voluptuous as vol

from homeassistant.const import ATTR_FRIENDLY_NAME
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.helpers.entity import Entity
import homeassistant.helpers.config_validation as cv

REQUIREMENTS = ['requests==2.18.4']

_LOGGER = logging.getLogger(__name__)

CONF_API_KEY = 'api_key'

ATTR_ON_PEAK_DOWNLOAD = 'on_peak_download'
ATTR_ON_PEAK_UPLOAD = 'on_peak_upload'
ATTR_OFF_PEAK_DOWNLOAD = 'off_peak_download'
ATTR_OFF_PEAK_UPLOAD = 'off_peak_upload'

ICON_DATA_USAGE = 'mdi:chart-donut'

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_API_KEY): cv.string,
})


def setup_platform(hass, config, add_devices, discovery_info=None):
    api_key = config.get(CONF_API_KEY)
    dev = TeksavvySensor(api_key)
    add_devices([dev], True)


class TeksavvySensor(Entity):
    def __init__(self, api_key):
        self._api_key = api_key
        self._oid = None
        self.on_peak_download = None
        self.on_peak_upload = None
        self.off_peak_download = None
        self.off_peak_upload = None

    @property
    def name(self):
        return 'teksavvy_' + self._oid

    @property
    def unit_of_measurement(self):
        return 'GB'

    @property
    def state(self):
        if self.on_peak_download is None:
            return 0
        return self.on_peak_download

    @property
    def device_state_attributes(self):
        return {
            ATTR_FRIENDLY_NAME: 'Data Usage',
            ATTR_ON_PEAK_DOWNLOAD: self.on_peak_download,
            ATTR_ON_PEAK_UPLOAD: self.on_peak_upload,
            ATTR_OFF_PEAK_DOWNLOAD: self.off_peak_download,
            ATTR_OFF_PEAK_UPLOAD: self.off_peak_upload,
        }

    @property
    def icon(self):
        return ICON_DATA_USAGE

    def update(self):
        import requests
        response = requests.get(
            'https://api.teksavvy.com/web/Usage/UsageSummaryRecords',
            params={'$filter': 'IsCurrent eq true'},
            headers={'TekSavvy-APIKey': self._api_key}
        ).json()
        self._oid = response['value'][0]['OID']
        self.on_peak_download = response['value'][0]['OnPeakDownload']
        self.on_peak_upload = response['value'][0]['OnPeakUpload']
        self.off_peak_download = response['value'][0]['OffPeakDownload']
        self.off_peak_upload = response['value'][0]['OffPeakUpload']
