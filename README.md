## Home Assistant custom components

### Questrade

#### Installation

- Copy `sensor/questrade.py` to `/config/custom_components/sensor/questrade.py`.
- Create an personal application on Questrade.
- Fill the following configuration:

```yaml
sensor:
  - platform: questrade
    client_id: <consumer key>
    refresh_token: <token>
    currency: CAD
    scan_interval: 900
```

Configuration variables:

- **client_id** (Required): The API consumer key. This is not used at this
  time but could be once this component uses a proper authorization flow.
- **refresh_token** (Required): The initial OAuth refresh token.
- **currency** (Optional): For combined balances, the currency to use for the
  account attributes. Defaults to `CAD`.
- **scan_interval** (Optional): The number of seconds between updates.
  Defaults to 60.

#### Custom UI

- Copy `custom_ui/state-card-custom-questrade.html` to
  `/config/www/custom_ui/state-card-custom-questrade.html`.
- In the `frontend:` section of the `configuration.yaml` file, use
  `extra_html_url` to specify the URL to load.
- In the `customize:` section add `custom_ui_state_card: state-card-custom-questrade`
  for each account entity.

Example:

```yaml
homeassistant:
  frontend:
    extra_html_url:
      - /local/custom_ui/state-card-custom-questrade.html

  customize:
    sensor.questrade_12345678:
      custom_ui_state_card: state-card-custom-questrade
```
