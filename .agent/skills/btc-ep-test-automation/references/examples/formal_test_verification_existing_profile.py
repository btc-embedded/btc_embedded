"""
Example: Combined Formal Test + Formal Verification (existing profile)

Assumptions:
- Existing profile already contains test cases and formal specifications.

Workflow:
1. Load existing profile and run architecture update
2. Run SIL test execution and formal test
3. Create/execute proofs for formal verification
4. Create/export reports and save updated profile
"""

import os
import sys

from btc_embedded import EPRestApi
from btc_embedded.util import print_rbt_results

# Configuration
RESULTS_DIR = os.path.abspath('results')
EPP_FILE = os.path.abspath('existing_project.epp')
RESULTS_EPP = os.path.join(RESULTS_DIR, 'existing_project_formal_results.epp')

os.makedirs(RESULTS_DIR, exist_ok=True)


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


def print_proof_summary(proof_uids, proof_name_by_uid, detailed_results_by_uid):
    print('\nFormal verification summary')
    print(f'  Proof count: {len(proof_uids)}')

    for proof_uid in proof_uids:
        proof_name = proof_name_by_uid.get(proof_uid, '<unnamed-proof>')
        details = detailed_results_by_uid.get(proof_uid, [])

        if not details:
            print(f'    - {proof_name} ({proof_uid}): no detailed result available')
            continue

        latest = details[-1]
        result = latest.get('proofResult', 'UNKNOWN')
        termination = latest.get('terminationReason', 'UNKNOWN')
        steps = latest.get('steps', 'UNKNOWN')
        print(
            f'    - {proof_name} ({proof_uid}): '
            f'result={result}, termination={termination}, steps={steps}'
        )


ep = None

try:
    ep = EPRestApi()
    ep.set_compiler()

    # 1. Load profile and update architecture
    ep.get(f'openprofile?path={EPP_FILE}')
    ep.put('architectures', message='Running architecture update on existing profile')

    scopes = ep.get('scopes')
    scope_uid = scopes[0]['uid']

    test_cases = ep.get('test-cases-rbt')
    if not test_cases:
        raise RuntimeError('Existing profile does not contain test cases for Formal Test')

    formal_requirements = ep.get(f'scopes/{scope_uid}/formal-requirements')
    if not formal_requirements:
        raise RuntimeError('Existing profile does not contain formal requirements/specifications')

    # 2. Execute SIL RBT first, then formal test
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

    # 3. Ensure proofs exist (create if needed), then execute proofs
    existing_proofs = ep.get('proofs')
    proof_uids = [proof['uid'] for proof in existing_proofs]
    proof_name_by_uid = {
        proof['uid']: proof.get('name', '<unnamed-proof>')
        for proof in existing_proofs
    }

    if not proof_uids:
        for formal_requirement in formal_requirements:
            fr_uid = formal_requirement['uid']
            fr_name = formal_requirement.get('name', '<unnamed-formal-requirement>')
            proof = ep.post(f'proofs/{fr_uid}', message=f'Creating proof for {fr_name}')
            proof_uid = proof['uid']
            proof_uids.append(proof_uid)
            proof_name_by_uid[proof_uid] = proof.get('name', fr_name)

    ep.post(
        'proofs/execute',
        {
            'proofUIDs': proof_uids,
            'strategy': 'BALANCED',
            'maxNumberOfThreads': -1,
        },
        message='Executing proofs for formal verification',
    )

    detailed_results_by_uid = {}
    for proof_uid in proof_uids:
        detailed_results_by_uid[proof_uid] = ep.get(
            f'proofs/{proof_uid}/detailed-proof-results'
        )
    print_proof_summary(proof_uids, proof_name_by_uid, detailed_results_by_uid)

    # 4. Create and export reports
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

    formal_verification_report = ep.post(
        f'scopes/{scope_uid}/formal-verification-reports',
        message='Creating formal verification report',
    )
    ep.post(
        f'reports/{formal_verification_report["uid"]}',
        {'exportPath': RESULTS_DIR, 'newName': 'formal_verification_report'},
        message='Exporting formal verification report',
    )

    ep.put('profiles', {'path': RESULTS_EPP}, message='Saving updated profile')
    print('Combined Formal Test + Formal Verification workflow completed successfully.')

except Exception as exc:
    print(f'Combined formal workflow failed: {exc}')
    sys.exit(1)
finally:
    if ep:
        ep.close_application()
