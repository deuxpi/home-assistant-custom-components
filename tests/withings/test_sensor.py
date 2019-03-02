from unittest.mock import patch

from custom_components import withings
from homeassistant.setup import async_setup_component

import homeassistant.components.sensor as sensor


@patch('nokia.NokiaApi.request')
@patch('nokia.NokiaApi.get_measures')
def test_setup_platform(mock_get_measures, mock_request, hass):
    mock_request.return_value = {
        'devices': [{'model': 'test', 'deviceid': 'device id'}],
    }
    mock_get_measures.return_value.__getitem__.return_value.weight = 86.0

    config = {
        'sensor': {
            'platform': withings.DOMAIN,
            'client_id': 'client id',
            'consumer_secret': 'consumer secret',
        }
    }
    result = hass.loop.run_until_complete(
        async_setup_component(hass, sensor.DOMAIN, config)
    )
    assert result

    state = hass.states.get('sensor.withings_device_id')
    assert state is not None

    assert state.state == '86.0'
    assert state.attributes.get('weight') == 86.0
    assert state.attributes.get('unit_of_measurement') == 'kg'
