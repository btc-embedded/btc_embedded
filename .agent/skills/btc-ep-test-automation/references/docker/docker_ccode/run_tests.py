import glob
import logging
import os
import sys
from datetime import datetime

from btc_embedded import EPRestApi
from btc_embedded.util import print_rbt_results, dump_testresults_junitxml

RESULTS_DIR    = os.path.abspath('results')
CODE_MODEL_XML = os.path.abspath('test/CodeModel.xml')
TESTCASES_DIR  = os.path.abspath('test/testcases')
EPP_FILE       = os.path.join(RESULTS_DIR, 'test_project.epp')

os.makedirs(RESULTS_DIR, exist_ok=True)

# Set up logging to both console and file before creating EPRestApi so the
# library skips adding its own console handler (it only adds one when none exist).
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
    ep.set_compiler()

    # 2. Create a fresh profile and import C-code architecture
    ep.post('profiles')
    ep.post('architectures/ccode', {'modelFile': CODE_MODEL_XML},
            message="Importing C-code architecture")

    # 3. Requirements-Based Testing (RBT)
    scopes = ep.get('scopes')
    scope_uid = scopes[0]['uid']

    # Collect test case files; only include *.tc.json (skip macros and *.ui_settings.tc.json)
    tc_files = sorted(
        p for p in glob.glob(os.path.join(TESTCASES_DIR, '*.tc.json'))
        if not p.endswith('.ui_settings.tc.json')
    )
    ep.put('test-cases-rbt', {'paths': tc_files},
           message="Importing test cases")

    rbt_result = ep.post(f'scopes/{scope_uid}/test-execution-rbt',
                         {'execConfigNames': ['SIL']},
                         message="Running Requirements-Based Tests (SIL)")
    # Log achieved coverage for SIL
    rbt_coverage = ep.get(f"scopes/{scope_uid}/coverage-results-rbt")
    print_rbt_results(rbt_result, rbt_coverage)

    # 4. Reporting & Export
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
        project_name='seat_heating_controller',
        start_time=start_time,
        output_file=os.path.join(RESULTS_DIR, 'test_results.xml')
    )

    logger.info("Test execution completed successfully.")

except Exception as e:
    logger.error(f"Test execution failed: {e}")
    sys.exit(1)

