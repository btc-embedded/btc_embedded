import glob
import logging
import os
import sys
from datetime import datetime

from btc_embedded import EPRestApi
from btc_embedded.util import print_rbt_results, print_b2b_results, dump_testresults_junitxml

RESULTS_DIR   = os.path.abspath('results')
MODEL_FILE    = os.path.abspath('src/Wrapper_seat_heating_control.slx')
INIT_SCRIPT   = os.path.abspath('src/init_Wrapper_seat_heating_control.m')
TESTCASES_DIR = os.path.abspath('testcases')
EPP_FILE      = os.path.join(RESULTS_DIR, 'test_project.epp')

os.makedirs(RESULTS_DIR, exist_ok=True)

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
    ep = EPRestApi()

    # 1. Create a fresh profile and import EmbeddedCoder architecture
    ep.post('profiles')
    ep.post('architectures/embedded-coder',
            {'ecModelFile': MODEL_FILE, 'ecInitScript': INIT_SCRIPT},
            message="Importing EmbeddedCoder architecture")

    scopes = ep.get('scopes')
    scope_uid = scopes[0]['uid']

    # 2. Requirements-Based Testing (RBT) on MIL and SIL
    tc_files = sorted(
        p for p in glob.glob(os.path.join(TESTCASES_DIR, '*.tc.json'))
        if not p.endswith('.ui_settings.tc.json')
    )
    ep.put('test-cases-rbt', {'paths': tc_files}, message="Importing test cases")

    rbt_result = ep.post(f'scopes/{scope_uid}/test-execution-rbt',
                         {'execConfigNames': ['SL MIL', 'SIL']},
                         message="Running Requirements-Based Tests (SL MIL + SIL)")
    rbt_coverage = ep.get(f'scopes/{scope_uid}/coverage-results-rbt')
    print_rbt_results(rbt_result, rbt_coverage)

    # 3. Generate vectors for full MCDC coverage
    ep.post('coverage-generation',
            {'scopeUid': scope_uid,
             'targetDefinitions': [{'label': 'C/DC and MC/DC'}]},
            message="Generating vectors for full MCDC coverage")

    # 4. Back-to-Back test: MIL (reference) vs SIL (comparison)
    b2b_result = ep.post(f'scopes/{scope_uid}/b2b',
                         {'refMode': 'SL MIL', 'compMode': 'SIL'},
                         message="Running Back-to-Back test (SL MIL vs SIL)")
    b2b_coverage = ep.get(f'scopes/{scope_uid}/coverage-results-b2b')
    print_b2b_results(b2b_result, b2b_coverage)

    # 5. Reporting & Export
    report = ep.post(f'scopes/{scope_uid}/project-report',
                     message="Creating test report")
    ep.post(f'reports/{report["uid"]}',
            {'exportPath': RESULTS_DIR, 'newName': 'test_report'})

    ep.put('profiles', {'path': EPP_FILE})

    test_cases = ep.get('test-cases-rbt')
    dump_testresults_junitxml(
        rbt_results=rbt_result,
        test_cases=test_cases,
        scopes=scopes,
        project_name='seat_heating_control',
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
