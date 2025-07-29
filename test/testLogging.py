import logging
import os

from btc_embedded import LOGGING_DISABLED, EPRestApi

# Configure logger
logger = logging.getLogger('btc_embedded')
log_file = os.path.join(os.path.dirname(__file__), 'btc_embedded.log')
file_handler = logging.FileHandler(log_file)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
logger.addHandler(file_handler)

ep = EPRestApi(log_level=LOGGING_DISABLED)