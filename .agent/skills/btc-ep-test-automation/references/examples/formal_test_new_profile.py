"""
Example: Formal Test Workflow (new profile)

Workflow:
1. Create a new profile and import C-code architecture
2. Import test cases and formal specifications (*.spec)
3. Run SIL test execution and formal test
4. Create/export reports and save profile
"""

import glob
import os
import sys

from btc_embedded import EPRestApi
from btc_embedded.util import print_rbt_results

# Configuration
RESULTS_DIR = os.path.abspath('results')
CODE_MODEL_XML = os.path.abspath('test/CodeModel.xml')
TESTCASES_DIR = os.path.abspath('test/testcases')
SPECS_DIR = os.path.abspath('specs')
EPP_FILE = os.path.join(RESULTS_DIR, 'formal_test_project.epp')

os.makedirs(RESULTS_DIR, exist_ok=True)


def collect_test_case_files(testcases_dir):
    tc_json_files = sorted(
        p for p in glob.glob(os.path.join(testcases_dir, '*.tc.json'))
        if not p.endswith('.ui_settings.tc.json')
    )
    tc_files = sorted(
        p for p in glob.glob(os.path.join(testcases_dir, '*.tc'))
        if not p.endswith('.ui_settings.tc')
    )
    return tc_json_files + tc_files


def print_formal_test_status(result):
    print('\nFormal test summary')
    print(f"  Coverage: {result.get('coverage', 'UNKNOWN')}")
    print(f"  Status:   {result.get('status', 'UNKNOWN')}")
    fr_results = result.get('formalRequirementResults', [])
    print(f"  Formal requirements: {len(fr_results)}")

    for fr in fr_results:
        fr_name = fr.get('formalRequirmentName', '<unnamed>')
        fr_uid = fr.get('formalRequirementUid', '<no-uid>')
        fr_coverage = fr.get('coverage', 'UNKNOWN')
        fr_status = fr.get('status', 'UNKNOWN')
        print(f"    - {fr_name} ({fr_uid}): status={fr_status}, coverage={fr_coverage}")


ep = None

try:
    ep = EPRestApi()
    ep.set_compiler()

    # 1. Create fresh profile and import architecture
    ep.post('profiles', message='Creating a new profile')
    ep.post(
        'architectures/ccode',
        {'modelFile': CODE_MODEL_XML},
        message='Importing C-code architecture',
    )

    scopes = ep.get('scopes')
    scope_uid = scopes[0]['uid']

    # 2. Import test cases
    tc_files = collect_test_case_files(TESTCASES_DIR)
    if not tc_files:
        raise RuntimeError(f'No test case files found in {TESTCASES_DIR}')

    ep.put(
        'test-cases-rbt',
        {'paths': tc_files},
        message='Importing test cases for Formal Test workflow',
    )

    # 3. Import formal specifications (*.spec)
    spec_files = sorted(glob.glob(os.path.join(SPECS_DIR, '*.spec')))
    if not spec_files:
        raise RuntimeError(f'No .spec files found in {SPECS_DIR}')

    for spec_file in spec_files:
        ep.post(
            'specifications-import',
            {
                'specPath': spec_file,
                'scopeId': scope_uid,
                'optionParam': 'OVERWRITE',
            },
            message=f'Importing formal specification: {os.path.basename(spec_file)}',
        )

    # 4. Run SIL test execution before formal test
    rbt_result = ep.post(
        f'scopes/{scope_uid}/test-execution-rbt',
        {'execConfigNames': ['SIL']},
        message='Running Requirements-Based Tests (SIL)',
    )
    rbt_coverage = ep.get(f'scopes/{scope_uid}/coverage-results-rbt')
    print_rbt_results(rbt_result, rbt_coverage)

    ep.post('execute-formal-test', message='Executing formal test')
    formal_test_results = ep.get(
        f'scopes/{scope_uid}/formal-test-results?execution-config-name=SIL'
    )
    print_formal_test_status(formal_test_results)

    # 5. Create and export reports
    test_report = ep.post(
        f'scopes/{scope_uid}/project-report?template-name=rbt-sil-only',
        message='Creating test report',
    )
    ep.post(
        f'reports/{test_report["uid"]}',
        {'exportPath': RESULTS_DIR, 'newName': 'test_report'},
        message='Exporting test report',
    )

    formal_test_report = ep.post(
        f'scopes/{scope_uid}/formal-test-reports',
        {'executionConfigNames': ['SIL']},
        message='Creating formal test report',
    )
    ep.post(
        f'reports/{formal_test_report["uid"]}',
        {'exportPath': RESULTS_DIR, 'newName': 'formal_test_report'},
        message='Exporting formal test report',
    )

    ep.put('profiles', {'path': EPP_FILE}, message='Saving profile')
    print('Formal Test workflow completed successfully.')

except Exception as exc:
    print(f'Formal Test workflow failed: {exc}')
    sys.exit(1)
finally:
    if ep:
        ep.close_application()
