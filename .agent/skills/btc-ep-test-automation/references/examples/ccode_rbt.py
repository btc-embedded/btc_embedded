"""
Example: C-Code RBT Test Automation
"""

import glob
import os
import sys
from datetime import datetime

from btc_embedded import EPRestApi
from btc_embedded.util import print_rbt_results, dump_testresults_junitxml

# Configuration
RESULTS_DIR = os.path.abspath('results')
CODE_MODEL_XML = os.path.abspath('test/CodeModel.xml')
TESTCASES_DIR = os.path.abspath('test/testcases')
EPP_FILE = os.path.join(RESULTS_DIR, 'test_project.epp')

os.makedirs(RESULTS_DIR, exist_ok=True)

start_time = datetime.now()
ep = None

try:
    # 1. Start BTC EmbeddedPlatform
    ep = EPRestApi()
    ep.set_compiler()

    # 2. Create a fresh profile and import C-code architecture
    ep.post('profiles', message='Creating a new profile')
    ep.post('architectures/ccode', {'modelFile': CODE_MODEL_XML},
            message='Importing C-code architecture')

    # 3. Get scope UID and import test cases
    scopes = ep.get('scopes')
    scope_uid = scopes[0]['uid']

    # Collect test case files; only include *.tc.json (skip macros and *.ui_settings.tc.json)
    tc_files = sorted(
        p for p in glob.glob(os.path.join(TESTCASES_DIR, '*.tc.json'))
        if not p.endswith('.ui_settings.tc.json')
    )
    ep.put('test-cases-rbt', {'paths': tc_files},
           message='Importing test cases')

    # 4. Run Requirements-Based Tests (RBT)
    rbt_result = ep.post(f'scopes/{scope_uid}/test-execution-rbt',
                         {'execConfigNames': ['SIL']},
                         message='Running Requirements-Based Tests (SIL)')
    rbt_coverage = ep.get(f"scopes/{scope_uid}/coverage-results-rbt")
    print_rbt_results(rbt_result, rbt_coverage)

    # 5. Generate report and export artifacts
    report = ep.post(f'scopes/{scope_uid}/project-report?template-name=rbt-sil-only',
                     message='Creating test report')
    ep.post(f'reports/{report["uid"]}',
            {'exportPath': RESULTS_DIR, 'newName': 'test_report'},
            message='Exporting test report')

    ep.put('profiles', {'path': EPP_FILE},
           message='Saving profile')

    # 6. Export JUnit XML results
    test_cases = ep.get('test-cases-rbt')
    dump_testresults_junitxml(
        rbt_results=rbt_result,
        test_cases=test_cases,
        scopes=scopes,
        project_name='seat_heating_controller',
        start_time=start_time,
        output_file=os.path.join(RESULTS_DIR, 'test_results.xml')
    )

    print("Test execution completed successfully.")

except Exception as e:
    print(f"Test execution failed: {e}")
    sys.exit(1)
finally:
    if ep:
        ep.close_application()
