"""
Example: Model-Based Migration Suite — Multiple Models (Two-Phase / Docker)

Runs migration testing for a suite of models in two phases:
  Phase 1 (source): generate vectors and record reference SIL behavior in the old environment
  Phase 2 (target): regression test against reference behavior in the new environment

In production, these phases run as separate scripts in separate environments
(e.g., different Docker images) sharing a mounted results/ directory:

  docker run ... ep:old bash /opt/ep/btc_start.bash migration_source.py
  docker run ... ep:new bash /opt/ep/btc_start.bash migration_target.py

This file demonstrates both phases for reference. For production use, copy the
source section into migration_source.py and the target section into migration_target.py.
"""

import logging
import os
import sys

from btc_embedded import migration_suite_source, migration_suite_target

# Configuration — must be identical in both migration_source.py and migration_target.py
RESULTS_DIR = os.path.abspath('results')
MODELS = [
    {
        'model':  os.path.abspath('models/ModelA.slx'),
        'script': os.path.abspath('models/initA.m'),   # optional MATLAB init script
    },
    {
        'model':  os.path.abspath('models/ModelB.slx'),
    },
]

os.makedirs(RESULTS_DIR, exist_ok=True)

logger = logging.getLogger('btc_embedded')
logger.setLevel(logging.INFO)
fmt = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
for handler in [logging.StreamHandler(),
                logging.FileHandler(os.path.join(RESULTS_DIR, 'migration.log'))]:
    handler.setFormatter(fmt)
    logger.addHandler(handler)


# ── PHASE 1: Migration Source ──────────────────────────────────────────────────
# Runs in the OLD environment (old MATLAB / old model version / old tool config).
# Detects EC or TL codegen automatically, generates coverage vectors, records
# reference SIL behavior, and saves a .epp per model into results/.
# In production: copy this block to migration_source.py

try:
    migration_suite_source(
        MODELS,
        matlab_version='2022b',
        # toolchain_script=os.path.abspath('init_toolchain.m'),  # optional MATLAB toolchain init
        # test_mil=True,     # also record MIL reference behavior (default: False)
        # reuse_code=True,   # skip code regeneration if already generated (default: False)
    )
    logger.info("Migration source phase completed.")
except Exception as e:
    logger.error(f"Migration source phase failed: {e}")
    sys.exit(1)


# ── PHASE 2: Migration Target ──────────────────────────────────────────────────
# Runs in the NEW environment (new MATLAB / new model version / new tool config).
# Loads .epp from results/, updates architecture, runs SIL regression test, and
# updates the overview report in results/BTCMigrationTestSuite.html.
# In production: copy this block to migration_target.py
# When running as a separate script, omit model_results — it is not available
# across separate process invocations; the target reads state from the .epp file.

try:
    migration_suite_target(
        MODELS,
        matlab_version='2025b',
        # toolchain_script=os.path.abspath('init_toolchain.m'),
        # test_mil=True,                   # must match source setting
        # reuse_code=True,
        # accept_interface_changes=False,  # set True if interface missmatches are expected and should be accepted as part of migration (default: False)
    )
    logger.info("Migration target phase completed. See results/BTCMigrationTestSuite.html for the report.")
except Exception as e:
    logger.error(f"Migration target phase failed: {e}")
    sys.exit(1)
