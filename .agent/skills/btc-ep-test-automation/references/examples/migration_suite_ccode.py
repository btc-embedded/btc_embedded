"""
Example: Custom Migration Suite for C-Code Projects — Multiple Components (Two-Phase / Docker)

Runs migration testing for a suite of C-code components in two phases:
  Phase 1 (source): generate vectors and record reference SIL behavior in the old environment
  Phase 2 (target): regression test against reference behavior in the new environment

In production, these phases run as separate scripts in separate environments
(e.g., different Docker images or machines) sharing a mounted results/ directory:

  docker run ... ep:old migration_source.py
  docker run ... ep:new migration_target.py

This file demonstrates both phases for reference. For production use, copy the
source section into migration_source.py and the target section into migration_target.py.

The migration_source_ccode / migration_target_ccode functions defined here include
integrated report updates (via _update_report). For single-component use without
reporting, see migration_test_ccode.py. In a production setup, extract all four
functions into a shared module (e.g. ccode_migration.py) and import from there.

Always verify endpoint paths and payload field names against the openapi spec
(references/openapi-specs/openapi_<version>.json) before adapting this script.
"""

import json
import logging
import os
import sys
from datetime import datetime

from btc_embedded import EPRestApi
from btc_embedded.reporting import create_report_from_json

RESULTS_DIR = os.path.abspath('results')
os.makedirs(RESULTS_DIR, exist_ok=True)

logger = logging.getLogger('btc_embedded')
logger.setLevel(logging.INFO)
fmt = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
for handler in [logging.StreamHandler(),
                logging.FileHandler(os.path.join(RESULTS_DIR, 'migration.log'))]:
    handler.setFormatter(fmt)
    logger.addHandler(handler)

report_json = None  # set by _initialize_report (source) or migration_suite_target_ccode (target)


# ── Report helpers ─────────────────────────────────────────────────────────────

def _get_comp_name(component):
    return component.get('name', os.path.splitext(os.path.basename(component['codeModelXml']))[0])


def _initialize_report(components, results_dir):
    """Create the initial report.json and render BTCMigrationTestSuite.html."""
    global report_json
    report_json = os.path.join(results_dir, 'report.json')
    report_data = {
        'title': 'BTC Migration Test Suite (C-Code)',
        'filename': 'BTCMigrationTestSuite.html',
        'results': {},
        'additionalStats': {},
    }
    for component in components:
        comp_name = _get_comp_name(component)
        report_data['results'][comp_name] = {'projectName': comp_name, 'status': 'SCHEDULED'}
    with open(report_json, 'w') as f:
        json.dump(report_data, f, indent=4)
    create_report_from_json(json_path=report_json)


def _update_report(project_item=None, additional_stats=None):
    """Update report.json and re-render the HTML. No-op if report_json is not set."""
    if not report_json or not os.path.isfile(report_json):
        return
    with open(report_json, 'r') as f:
        report_data = json.load(f)
    if project_item:
        comp_name = project_item['projectName']
        if comp_name in report_data['results']:
            report_data['results'][comp_name].update(project_item)
        else:
            report_data['results'][comp_name] = project_item
    if additional_stats:
        report_data.setdefault('additionalStats', {}).update(additional_stats)
    with open(report_json, 'w') as f:
        json.dump(report_data, f, indent=4)
    create_report_from_json(json_path=report_json)


def _update_report_running(comp_name, step_name):
    _update_report({'projectName': comp_name, 'status': 'RUNNING', 'info': f'{step_name}...'})


# ── Single-component source / target phases ────────────────────────────────────

def migration_source_ccode(component, source_epp, ep=None):
    """Source phase: create profile, import C-code architecture, generate coverage
    vectors, record SIL reference behavior, and save to source_epp.

    component: dict with keys 'codeModelXml' (mandatory), 'name' (optional)
    source_epp: path where the .epp is saved (execution records stored inside)
    ep: optional EPRestApi instance; if None, one is created and closed automatically

    Returns source_epp path.
    """
    comp_name = _get_comp_name(component)
    start_time = datetime.now()

    owns_ep = ep is None
    if owns_ep:
        ep = EPRestApi()
        ep.set_compiler()

    try:
        _update_report_running(comp_name, 'Importing C-code architecture')
        ep.post('profiles', message='Creating source profile')
        ep.post('architectures/ccode', {'modelFile': component['codeModelXml']},
                message='Importing C-code architecture (source)')

        scope_uid = ep.get('scopes')[0]['uid']

        _update_report_running(comp_name, 'Generating coverage vectors')
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

        _update_report_running(comp_name, 'Reference simulation (SIL)')
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

        duration = (datetime.now() - start_time).seconds
        _update_report({'projectName': comp_name, 'status': 'RUNNING',
                        'info': 'Migration Source step completed.', 'duration': duration})
        logger.info(f"[{comp_name}] Source phase complete.")
    except Exception as e:
        duration = (datetime.now() - start_time).seconds
        _update_report({'projectName': comp_name, 'status': 'ERROR',
                        'info': str(e).split('\n')[0], 'duration': duration})
        raise
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
    comp_name = _get_comp_name(component)
    start_time = datetime.now()
    results_dir = os.path.dirname(target_epp)

    owns_ep = ep is None
    if owns_ep:
        ep = EPRestApi()
        ep.set_compiler()

    try:
        _update_report_running(comp_name, 'Loading source profile')
        ep.get(f'openprofile?path={source_epp}', message='Loading source profile')

        _update_report_running(comp_name, 'Updating C-code architecture')
        ep.put('architectures', message='Updating C-code architecture (target)')

        scope_uid = ep.get('scopes')[0]['uid']

        _update_report_running(comp_name, 'Regression Test SIL vs. SIL')
        new_sil_folder = ep.post('folders',
                                 {'folderKind': 'EXECUTION_RECORD', 'folderName': 'new-sil'},
                                 message='Creating new-sil folder')
        er_folders = [f for f in ep.get('folders?kind=EXECUTION_RECORD') if not f['isDefault']]
        old_sil_folder = next(f for f in er_folders if f['name'] == 'old-sil')

        regression_result = ep.post(
            f"folders/{old_sil_folder['uid']}/regression-tests",
            {'compMode': 'SIL', 'compFolderUID': new_sil_folder['uid']},
            message='Regression Test SIL vs. SIL')
        verdict = regression_result.get('verdictStatus', 'ERROR')
        logger.info(f"[{comp_name}] Regression result: {verdict}")

        _update_report_running(comp_name, 'Creating report')
        report = ep.post(f'scopes/{scope_uid}/project-report?template-name=regression-test-sil-only',
                         message='Creating migration test report')
        ep.post(f"reports/{report['uid']}",
                {'exportPath': results_dir, 'newName': f'{comp_name}-migration-test'},
                message='Exporting report')

        ep.put('profiles', {'path': target_epp}, message='Saving target profile')

        # Accumulate duration across both phases (source duration was stored in the report)
        src_duration = 0
        if report_json and os.path.isfile(report_json):
            with open(report_json, 'r') as f:
                rd = json.load(f)
            src_duration = rd.get('results', {}).get(comp_name, {}).get('duration', 0)
        total_duration = (datetime.now() - start_time).seconds + src_duration

        _update_report({
            'projectName': comp_name,
            'status': 'COMPLETED',
            'testResult': verdict,
            'reportPath': f'{comp_name}-migration-test.html',
            'eppPath': os.path.basename(target_epp),
            'duration': total_duration,
            'info': '',
        })
        logger.info(f"[{comp_name}] Target phase complete: {verdict}")
    except Exception as e:
        duration = (datetime.now() - start_time).seconds
        _update_report({'projectName': comp_name, 'status': 'ERROR',
                        'info': str(e).split('\n')[0], 'duration': duration})
        raise
    finally:
        if owns_ep:
            ep.close_application()

    return regression_result


# ── Suite functions ────────────────────────────────────────────────────────────

def migration_suite_source_ccode(components, results_dir=None, ep=None):
    """Source phase for multiple C-code components.

    Initializes the live overview report (results/BTCMigrationTestSuite.html), then
    creates one EP session and calls migration_source_ccode for each component in the list.

    components: list of dicts with keys 'codeModelXml' (mandatory), 'name' (optional)
    results_dir: directory for .epp files and reports (default: 'results/')
    ep: optional EPRestApi instance shared across all components

    Returns dict mapping component name -> source_epp path (None on per-component error).
    """
    if results_dir is None:
        results_dir = RESULTS_DIR
    os.makedirs(results_dir, exist_ok=True)

    _initialize_report(components, results_dir)

    owns_ep = ep is None
    if owns_ep:
        ep = EPRestApi()
        ep.set_compiler()

    source_epps = {}
    try:
        for component in components:
            comp_name = _get_comp_name(component)
            source_epp = os.path.join(results_dir, f'{comp_name}.epp')
            try:
                migration_source_ccode(component, source_epp, ep=ep)
                source_epps[comp_name] = source_epp
            except Exception as e:
                logger.error(f"[{comp_name}] Source phase failed: {e}")
                source_epps[comp_name] = None
    finally:
        if owns_ep:
            ep.close_application()

    return source_epps


def migration_suite_target_ccode(components, results_dir=None, ep=None):
    """Target phase for multiple C-code components.

    Sets the report path (results/BTCMigrationTestSuite.html updated per component),
    creates one EP session, and calls migration_target_ccode for each component.
    Components whose source .epp is missing are skipped.

    components: list of dicts with keys 'codeModelXml' (mandatory), 'name' (optional)
    results_dir: directory containing source .epp files and where reports are written
    ep: optional EPRestApi instance shared across all components

    Returns dict mapping component name -> regression result dict (None on per-component error).
    """
    global report_json
    if results_dir is None:
        results_dir = RESULTS_DIR

    # Resolve report path so _update_report works when running as a separate process
    report_json = os.path.join(results_dir, 'report.json')

    owns_ep = ep is None
    if owns_ep:
        ep = EPRestApi()
        ep.set_compiler()

    results = {}
    try:
        for component in components:
            comp_name = _get_comp_name(component)
            source_epp = os.path.join(results_dir, f'{comp_name}.epp')
            target_epp = os.path.join(results_dir, f'{comp_name}_target.epp')

            if not os.path.isfile(source_epp):
                logger.warning(f"[{comp_name}] Skipping — source .epp not found: {source_epp}")
                results[comp_name] = None
                continue

            try:
                result = migration_target_ccode(component, source_epp, target_epp, ep=ep)
                results[comp_name] = result
            except Exception as e:
                logger.error(f"[{comp_name}] Target phase failed: {e}")
                results[comp_name] = None
    finally:
        if owns_ep:
            ep.close_application()

    passed = [n for n, r in results.items() if r and r.get('verdictStatus') == 'PASSED']
    failed = [n for n, r in results.items() if not r or r.get('verdictStatus') != 'PASSED']
    logger.info(f"Suite summary — PASSED: {len(passed)}, FAILED/ERROR: {len(failed)}")
    if failed:
        logger.error(f"Failed components: {failed}")

    return results


# ── Configuration — must be identical in both migration_source.py and migration_target.py ──

COMPONENTS = [
    {
        'codeModelXml': os.path.abspath('test/ComponentA/CodeModel.xml'),
        'name': 'ComponentA',  # optional; derived from codeModelXml filename if omitted
    },
    {
        'codeModelXml': os.path.abspath('test/ComponentB/CodeModel.xml'),
        'name': 'ComponentB',
    },
]


# ── PHASE 1: Migration Source ──────────────────────────────────────────────────
# Runs in the OLD environment (old compiler / old tool config / old source files).
# Creates results/BTCMigrationTestSuite.html (updated live as each component completes).
# In production: copy this block to migration_source.py

try:
    migration_suite_source_ccode(COMPONENTS)
    logger.info("Migration source phase completed.")
except Exception as e:
    logger.error(f"Migration source phase failed: {e}")
    sys.exit(1)


# ── PHASE 2: Migration Target ──────────────────────────────────────────────────
# Runs in the NEW environment (new compiler / new tool config / new source files).
# Loads source .epp per component, updates architecture, runs SIL regression test,
# exports per-component reports to results/, and updates BTCMigrationTestSuite.html.
# In production: copy this block to migration_target.py

try:
    results = migration_suite_target_ccode(COMPONENTS)
    any_failed = any(not r or r.get('verdictStatus') != 'PASSED' for r in results.values())
    # Overview report: results/BTCMigrationTestSuite.html
    # Per-component reports: results/<name>-migration-test.html
    if any_failed:
        sys.exit(1)
except Exception as e:
    logger.error(f"Migration target phase failed: {e}")
    sys.exit(1)
