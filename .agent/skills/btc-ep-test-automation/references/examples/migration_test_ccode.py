"""
Example: Custom Migration Test for C-Code Projects — Single Component

The built-in migration_test() only supports model-based projects (EmbeddedCoder / TargetLink).
This script implements the same two-phase pattern manually for C-code projects.

For multi-component migration testing, see migration_suite_ccode.py.

Always verify endpoint paths and payload field names against the openapi spec
(references/openapi-specs/openapi_<version>.json) before adapting this script.
"""

import logging
import os
import sys

from btc_embedded import EPRestApi

RESULTS_DIR = os.path.abspath('results')
os.makedirs(RESULTS_DIR, exist_ok=True)

logger = logging.getLogger('btc_embedded')
logger.setLevel(logging.INFO)
fmt = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
for handler in [logging.StreamHandler(),
                logging.FileHandler(os.path.join(RESULTS_DIR, 'migration.log'))]:
    handler.setFormatter(fmt)
    logger.addHandler(handler)

def migration_source_ccode(component, source_epp, ep=None):
    """Source phase: create profile, import C-code architecture, generate coverage
    vectors, record SIL reference behavior, and save to source_epp.

    component: dict with keys 'codeModelXml' (mandatory), 'name' (optional)
    source_epp: path where the .epp is saved (execution records stored inside)
    ep: optional EPRestApi instance; if None, one is created and closed automatically

    Returns source_epp path.
    """
    owns_ep = ep is None
    if owns_ep:
        ep = EPRestApi()
        ep.set_compiler()

    try:
        ep.post('profiles', message='Creating source profile')
        ep.post('architectures/ccode', {'modelFile': component['codeModelXml']},
                message='Importing C-code architecture (source)')

        scope_uid = ep.get('scopes')[0]['uid']

        ep.post('coverage-generation',
                {
                    'scopeUid': scope_uid,
                    'pllString': 'STM',
                    'engineSettings': {
                        'timeoutSeconds': 300,
                        'engineAtg': {'timeoutSecondsPerSubsystem': 100},
                    },
                },
                message='Generating coverage vectors')

        ep.post(f'scopes/{scope_uid}/testcase-simulation',
                {'execConfigNames': ['SIL']},
                message='Reference simulation (SIL)')

        all_er = ep.get('execution-records')
        old_sil_folder = ep.post('folders',
                                 {'folderKind': 'EXECUTION_RECORD', 'folderName': 'old-sil'},
                                 message='Creating old-sil folder')
        sil_er_uids = [er['uid'] for er in all_er if er['executionConfig'] == 'SIL']
        ep.put(f"folders/{old_sil_folder['uid']}/execution-records", {'UIDs': sil_er_uids})

        ep.put('profiles', {'path': source_epp}, message='Saving source profile')
        logger.info(f"Source phase complete: {source_epp}")
    finally:
        if owns_ep:
            ep.close_application()

    return source_epp


def migration_target_ccode(component, source_epp, target_epp, ep=None):
    """Target phase: load source .epp (execution records already inside), update
    C-code architecture, run SIL regression test, create and export report.

    component: dict with keys 'codeModelXml' (mandatory), 'name' (optional)
    source_epp: path to the .epp created by migration_source_ccode
    target_epp: path where the resulting target .epp is saved
    ep: optional EPRestApi instance; if None, one is created and closed automatically

    Returns the regression test result dict (keys: verdictStatus, passed, failed, error, total).
    """
    owns_ep = ep is None
    if owns_ep:
        ep = EPRestApi()
        ep.set_compiler()

    try:
        ep.get('openprofile', {'path': source_epp})

        ep.put('architectures/ccode', {'modelFile': component['codeModelXml']},
               message='Updating C-code architecture (target)')
        ep.put('architectures', message='Regenerating code')

        scope_uid = ep.get('scopes')[0]['uid']

        new_sil_folder = ep.post('folders',
                                 {'folderKind': 'EXECUTION_RECORD', 'folderName': 'new-sil'},
                                 message='Creating new-sil folder')
        er_folders = [f for f in ep.get('folders?kind=EXECUTION_RECORD') if not f['isDefault']]
        old_sil_folder = next(f for f in er_folders if f['name'] == 'old-sil')

        regression_result = ep.post(
            f"folders/{old_sil_folder['uid']}/regression-tests",
            {'compMode': 'SIL', 'compFolderUID': new_sil_folder['uid']},
            message='Regression Test SIL vs. SIL')
        logger.info(f"Regression result: {regression_result['verdictStatus']}")

        comp_name = component.get('name', os.path.splitext(os.path.basename(component['codeModelXml']))[0])
        report = ep.post(f'scopes/{scope_uid}/project-report?template-name=regression-test-sil-only',
                         message='Creating migration test report')
        ep.post(f"reports/{report['uid']}",
                {'exportPath': os.path.dirname(target_epp), 'newName': f'{comp_name}-migration-test'},
                message='Exporting report')

        ep.put('profiles', {'path': target_epp}, message='Saving target profile')
        logger.info(f"Target phase complete: {target_epp}")
    finally:
        if owns_ep:
            ep.close_application()

    return regression_result


# ── Configuration ──────────────────────────────────────────────────────────────

OLD_COMPONENT = {
    'codeModelXml': os.path.abspath('test/CodeModel.xml'),
    'name': 'MyComponent',  # optional; derived from codeModelXml filename if omitted
}

# Same component, different compiler / tool config:
NEW_COMPONENT = OLD_COMPONENT
# For refactored source files, provide updated codeModelXml:
# NEW_COMPONENT = {'codeModelXml': os.path.abspath('test/CodeModel_v2.xml'), 'name': 'MyComponent'}

COMP_NAME = OLD_COMPONENT.get('name', os.path.splitext(os.path.basename(OLD_COMPONENT['codeModelXml']))[0])
SOURCE_EPP = os.path.join(RESULTS_DIR, f'{COMP_NAME}.epp')
TARGET_EPP = os.path.join(RESULTS_DIR, f'{COMP_NAME}_target.epp')

# ── Run migration test ─────────────────────────────────────────────────────────

try:
    migration_source_ccode(OLD_COMPONENT, SOURCE_EPP)
    result = migration_target_ccode(NEW_COMPONENT, SOURCE_EPP, TARGET_EPP)
    status = result.get('verdictStatus', 'ERROR') if result else 'ERROR'
    logger.info(f"Migration test result: {status}")
    # Per-component report: results/<name>-migration-test.html
    if status != 'PASSED':
        sys.exit(1)
except Exception as e:
    logger.error(f"Migration test failed: {e}")
    sys.exit(1)
