import json
from btc_embedded import EPRestApi

import sys

ep = EPRestApi()
btc_embedded_api = ep.get('openapi.json')
with open(f'openapi_{sys.argv[1]}.json', 'w') as f:
    json.dump(btc_embedded_api, f, indent=2)
