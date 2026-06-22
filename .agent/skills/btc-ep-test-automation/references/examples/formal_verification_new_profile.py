"""
Example: Formal Verification Workflow (new profile)

Workflow:
1. Create a new profile and import C-code architecture
2. Import formal specifications (*.spec)
3. Create proofs for all formal requirements and execute them
4. Create/export formal verification report and save profile
"""

import glob
import os
import sys

from btc_embedded import EPRestApi

# Configuration
RESULTS_DIR = os.path.abspath('results')
CODE_MODEL_XML = os.path.abspath('test/CodeModel.xml')
SPECS_DIR = os.path.abspath('specs')
EPP_FILE = os.path.join(RESULTS_DIR, 'formal_verification_project.epp')

os.makedirs(RESULTS_DIR, exist_ok=True)


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

    # 1. Create fresh profile and import architecture
    ep.post('profiles', message='Creating a new profile')
    ep.post(
        'architectures/ccode',
        {'modelFile': CODE_MODEL_XML},
        message='Importing C-code architecture',
    )

    scopes = ep.get('scopes')
    scope_uid = scopes[0]['uid']

    # 2. Import formal specifications (*.spec)
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

    formal_requirements = ep.get(f'scopes/{scope_uid}/formal-requirements')
    if not formal_requirements:
        raise RuntimeError('No formal requirements are available after SPEC import')

    # 3. Create proofs and execute them
    proof_uids = []
    proof_name_by_uid = {}
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

    # 4. Create and export formal verification report
    formal_verification_report = ep.post(
        f'scopes/{scope_uid}/formal-verification-reports',
        message='Creating formal verification report',
    )
    ep.post(
        f'reports/{formal_verification_report["uid"]}',
        {'exportPath': RESULTS_DIR, 'newName': 'formal_verification_report'},
        message='Exporting formal verification report',
    )

    ep.put('profiles', {'path': EPP_FILE}, message='Saving profile')
    print('Formal Verification workflow completed successfully.')

except Exception as exc:
    print(f'Formal Verification workflow failed: {exc}')
    sys.exit(1)
finally:
    if ep:
        ep.close_application()
