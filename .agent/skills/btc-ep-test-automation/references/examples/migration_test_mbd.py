"""
Example: Model-Based Migration Test — Single Model (EmbeddedCoder / TargetLink)

Convenience wrapper that runs source and target phases in sequence within a
single environment. Use for quick single-model migration tests (e.g. MATLAB
version upgrade or model refactoring validation).

For two-phase Docker-based testing across separate environments, see
migration_suite_mbd.py instead.
"""

import logging
import os
import sys

from btc_embedded import migration_test

# Configuration
RESULTS_DIR = os.path.abspath('results')
OLD_MATLAB = '2024b'
NEW_MATLAB = '2025b'

OLD_MODEL = {
    'model':  os.path.abspath('models/MyModel.slx'),
    'script': os.path.abspath('models/init.m'),  # optional MATLAB init/start script
}

# Same model, different MATLAB version:
NEW_MODEL = OLD_MODEL
# For a refactored/updated model, use a different path:
# NEW_MODEL = {'model': os.path.abspath('models/MyModel_v2.slx'), 'script': os.path.abspath('models/init.m')}

os.makedirs(RESULTS_DIR, exist_ok=True)

# Set up logging before migration_test() so output goes to both console and file.
logger = logging.getLogger('btc_embedded')
logger.setLevel(logging.INFO)
fmt = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
for handler in [logging.StreamHandler(),
                logging.FileHandler(os.path.join(RESULTS_DIR, 'migration.log'))]:
    handler.setFormatter(fmt)
    logger.addHandler(handler)

try:
    result = migration_test(
        OLD_MODEL,
        OLD_MATLAB,
        new_model=NEW_MODEL,
        new_matlab=NEW_MATLAB,
        test_mil=False,   # set True to also run MIL–MIL regression on top of SIL–SIL
    )
    status = result.get('testResult', 'ERROR') if result else 'ERROR'
    logger.info(f"Migration test result: {status}")
    # Report: results/<model_name>-migration-test.html
    if status != 'PASSED':
        sys.exit(1)
except Exception as e:
    logger.error(f"Migration test failed: {e}")
    sys.exit(1)
