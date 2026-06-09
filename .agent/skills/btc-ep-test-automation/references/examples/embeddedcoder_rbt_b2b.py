"""
Example: EmbeddedCoder RBT + B2B Test Automation
"""

import glob
import logging
import os
import sys
from datetime import datetime

from btc_embedded import EPRestApi
from btc_embedded.util import print_rbt_results, print_b2b_results, dump_testresults_junitxml

# Configuration
RESULTS_DIR = os.path.abspath('results')
TESTCASES_DIR = os.path.abspath('testcases')
EC_MODEL_FILE = os.path.abspath('model/Wrapper_my_ec_model.slx')
EC_INIT_SCRIPT = os.path.abspath('model/init_Wrapper_my_ec_model.m')
EPP_FILE = os.path.join(RESULTS_DIR, 'my_ec_model.epp')

os.makedirs(RESULTS_DIR, exist_ok=True)

# Set up logging
logger = logging.getLogger('btc_embedded')
logger.setLevel(logging.INFO)
fmt = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
for handler in [logging.StreamHandler(),
                logging.FileHandler(os.path.join(RESULTS_DIR, 'test_run.log'))]:
    handler.setFormatter(fmt)
    logger.addHandler(handler)

start_time = datetime.now()
ep = None

try:
    # 1. Start BTC EmbeddedPlatform
    ep = EPRestApi()
    
    # 2. Set MATLAB version preference (remove if running in Docker)
    ep.put(
        'preferences',
        [
            {'preferenceName': 'GENERAL_MATLAB_VERSION',        'preferenceValue': 'CUSTOM'},
            {'preferenceName': 'GENERAL_MATLAB_CUSTOM_VERSION', 'preferenceValue': 'MATLAB R2024b (64-bit)'},
        ],
        message='Setting MATLAB version preference to R2024b',
    )
    
    # 3. Create a fresh profile and import EmbeddedCoder architecture
    ep.post('profiles', message='Creating a new profile')
    ep.post('architectures/embedded-coder',
            {'ecModelFile': EC_MODEL_FILE, 'ecInitScript': EC_INIT_SCRIPT},
            message='Importing EmbeddedCoder architecture')
    
    # 4. Get scope UID and import test cases
    scopes = ep.get('scopes')
    scope_uid = scopes[0]['uid']
    
    tc_files = sorted(
        p for p in glob.glob(os.path.join(TESTCASES_DIR, '*.tc.json'))
        if not p.endswith('.ui_settings.tc.json')
    )
    ep.put('test-cases-rbt', {'paths': tc_files},
           message='Importing test cases')
    
    # 5. Run Requirements-Based Tests (RBT) - SIL only
    rbt_result = ep.post(f'scopes/{scope_uid}/test-execution-rbt',
                         {'execConfigNames': ['SIL']},
                         message='Running Requirements-Based Tests (SIL)')
    rbt_coverage = ep.get(f"scopes/{scope_uid}/coverage-results-rbt")
    print_rbt_results(rbt_result, rbt_coverage)
    
    # 6. Generate vectors for full MCDC coverage before B2B
    ep.post('coverage-generation',
            {'scopeUid': scope_uid,
             'targetDefinitions': [{'label': 'C/DC and MC/DC'}]},
            message='Generating vectors for full MCDC coverage before B2B')

    # 7. Run Back-to-Back tests (SL MIL vs SIL)
    b2b_result = ep.post(f'scopes/{scope_uid}/b2b',
                         {'refMode': 'SL MIL', 'compMode': 'SIL'},
                         message='Running Back-to-Back test (SL MIL vs SIL)')
    b2b_coverage = ep.get(f"scopes/{scope_uid}/coverage-results-b2b")
    print_b2b_results(b2b_result, b2b_coverage)
    
    # 8. Generate report and export artifacts
    report = ep.post(f'scopes/{scope_uid}/project-report',
                     message='Creating test report')
    ep.post(f'reports/{report["uid"]}',
            {'exportPath': RESULTS_DIR, 'newName': 'test_report'},
            message='Exporting test report')
    
    ep.put('profiles', {'path': EPP_FILE},
           message='Saving profile')
    
    # 9. Export JUnit XML results
    test_cases = ep.get('test-cases-rbt')
    dump_testresults_junitxml(
        rbt_results=rbt_result,
        b2b_result=b2b_result,
        test_cases=test_cases,
        scopes=scopes,
        project_name='my_ec_model',
        start_time=start_time,
        output_file=os.path.join(RESULTS_DIR, 'test_results.xml')
    )
    
    logger.info("Test execution completed successfully.")

except Exception as e:
    logger.error(f"Test execution failed: {e}")
    sys.exit(1)
finally:
    if ep:
        ep.close_application()
