import logging

from btc_embedded import EPRestApi

# Configure logger
logger = logging.getLogger('BTC')
logger.setLevel(logging.DEBUG)

# Create console handler and set level to debug
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)

# Create formatter
#formatter = logging.Formatter('[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
formatter = logging.Formatter('[%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

# Add formatter to console handler
ch.setFormatter(formatter)

# Add console handler to logger
logger.addHandler(ch)

ep = EPRestApi()

