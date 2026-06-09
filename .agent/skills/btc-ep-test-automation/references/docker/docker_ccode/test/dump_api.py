import json

from btc_embedded import EPRestApi

ep = EPRestApi()
btc_embedded_api = ep.get('openapi.json')

with open('openapi.json', 'w') as f:
    json.dump(btc_embedded_api, f, indent=2)

