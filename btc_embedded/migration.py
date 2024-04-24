import glob
import os
import shutil
import traceback
from datetime import datetime

from btc_embedded.api import EPRestApi
from btc_embedded.reporting import create_test_report_summary

tmp = {}
source_version = None

def migration_suite_source(models, matlab_version):
    """For each of the given models this function generates tests for
    full coverage on the given model using the specified Matlab version,
    then performs a MIL and SIL simulation to record the reference behavior."""
    global source_version
    source_version = matlab_version
    shutil.rmtree('results', ignore_errors=True)
    ep = start_ep_and_configure_matlab(matlab_version)
    for old_model in models:
        migration_source(old_model, matlab_version, ep_api_object=ep)
    ep.close_application()

def migration_suite_target(models, matlab_version):
    """For each of the given models this function
    imports the reference execution records and simulates the same
    vectors on MIL and SIL based on the specified Matlab version. This
    regression test will show any changed behavior compared to the provided 
    reference execution."""
    results = []
    ep = start_ep_and_configure_matlab(matlab_version)
    for new_model in models:
        result = migration_target(new_model, matlab_version, ep_api_object=ep)
        results.append(result)
    ep.close_application()
    create_test_report_summary(results, 'BTC Migration Test Suite', 'BTCMigrationTestSuite.html', 'results')

def migration_source(old_model, matlab_version, test_mil=False, ep_api_object=None):
    """Generates tests for full coverage on the given model using the
    specified Matlab version, then performs a MIL and SIL simulation
    to record the reference behavior.

    Returns the BTC EmbeddedPlatform Project (*.epp).
    """
    # check if the ep api object is controlled externally
    if ep_api_object: ep = ep_api_object
    else: ep = start_ep_and_configure_matlab(matlab_version)

    start_time = datetime.now()
    model_path = os.path.abspath(old_model['model'])
    model_name = os.path.basename(model_path)[:-4].replace('Wrapper_', '')
    script_path = os.path.abspath(old_model['script']) if 'script' in old_model and old_model['script'] else None
    result_dir = os.path.abspath('results')
    epp_file, _ = get_epp_file_by_name(result_dir, model_path)
    
    # Empty BTC EmbeddedPlatform profile (*.epp) + Arch Import
    ep.post('profiles?discardCurrentProfile=true')

    # Import model
    payload = {
        'ecModelFile' : model_path,
        'ecInitScript' : script_path
    } 
    ep.post('architectures/embedded-coder', payload, message=f"Importing {model_name}  with Matlab R{matlab_version}")
    scopes = ep.get('scopes')
    toplevel_scope_uid = next(scope['uid'] for scope in scopes if scope['architecture'] == 'Simulink')

    # Generate vectors for full coverage
    ep.post('coverage-generation', { 'scopeUid' : toplevel_scope_uid, 'pllString': 'MCDC' }, message="Generating vectors")
    b2b_coverage = ep.get(f"scopes/{toplevel_scope_uid}/coverage-results-b2b")
    print('Coverage ' + "{:.2f}%".format(b2b_coverage['MCDCPropertyCoverage']['handledPercentage']))

    # Simulation
    payload = { 'execConfigNames' : ['SL MIL', 'SIL'] if test_mil else ['SIL'] }
    ep.post(f"scopes/{toplevel_scope_uid}/testcase-simulation", payload, message="Reference Simulation on MIL and SIL")

    # Store MIL and SIL executions for comparison
    all_execution_records = ep.get('execution-records')
    payload = { "folderKind": "EXECUTION_RECORD" }
    
    # SIL
    payload['folderName'] = 'old-sil'
    old_sil_folder = ep.post('folders', payload)
    sil_execution_records_uids = [ er['uid'] for er in all_execution_records if er['executionConfig'] == 'SIL']
    ep.put(f"folders/{old_sil_folder['uid']}/execution-records", { 'UIDs' : sil_execution_records_uids })
    
    # MIL
    if test_mil:
        payload['folderName'] = 'old-mil'
        old_mil_folder = ep.post('folders', payload)
        mil_execution_records_uids = [ er['uid'] for er in all_execution_records if er['executionConfig'] == 'SL MIL']
        ep.put(f"folders/{old_mil_folder['uid']}/execution-records", { 'UIDs' : mil_execution_records_uids })

    # Save *.epp, close application unless controlled externally
    ep.put('profiles', { 'path': epp_file })
    if not ep_api_object: ep.close_application()

    # time measurement
    global tmp
    duration_seconds = (datetime.now() - start_time).seconds
    tmp[model_name] = duration_seconds
    
    return epp_file

def migration_target(new_model, matlab_version, test_mil=False, ep_api_object=None, epp_file=None):
    """Imports the reference execution records and simulates the same
    vectors on MIL and SIL based on the specified Matlab version. This
    regression test will show any changed behavior compared to the provided 
    reference execution.

    Produces a test report
    """
    # check if the ep api object is controlled externally
    if ep_api_object: ep = ep_api_object
    else: ep = start_ep_and_configure_matlab(matlab_version)

    start_time = datetime.now()
    model_path = os.path.abspath(new_model['model'])
    model_name = os.path.basename(model_path)[:-4].replace('Wrapper_', '')
    script_path = os.path.abspath(new_model['script']) if 'script' in new_model and new_model['script'] else None
    result_dir = os.path.abspath('results')
    if epp_file: epp_rel_path = None
    else: epp_file, epp_rel_path = get_epp_file_by_name(result_dir, model_path)

    # load BTC EmbeddedPlatform profile (*.epp) -> Update Model
    ep.get(f'profiles/{epp_file}?discardCurrentProfile=true')

    # Arch Update
    payload = {
        'slModelFile' : model_path,
        'slInitScript' : script_path
    } 
    ep.put(f"architectures/model-paths", payload)
    ep.put('architectures', message=f"Updating model & generating code for {model_name} with Matlab {matlab_version}")

    scopes = ep.get('scopes')
    toplevel_scope_uid = next(scope['uid'] for scope in scopes if scope['architecture'] == 'Simulink')
    
    # Import Execution Records
    # -> SIL
    # folder
    payload = {'folderKind': 'EXECUTION_RECORD', 'folderName' : 'new-sil' }
    new_sil_folder = ep.post('folders', payload)
    old_sil_folder = ep.get('folders?name=old-sil')[0]
    # regression test
    payload = { 
        'compMode': 'SIL',
        'compFolderUID' : new_sil_folder['uid']
    }
    sil_test = ep.post(f"folders/{old_sil_folder['uid']}/regression-tests", payload, message="Regression Test SIL vs. SIL")
    # verdictStatus, failed, error, passed, total
    print(f"Result: {sil_test['verdictStatus']}")

    # -> MIL
    if test_mil:
        # folder
        payload = {'folderKind': 'EXECUTION_RECORD', 'folderName' : 'new-mil' }
        new_mil_folder = ep.post('folders', payload)
        old_mil_folder = ep.get('folders?name=old-mil')[0]
        # regression test
        payload = {
            'compMode': 'SL MIL',
            'compFolderUID': new_mil_folder['uid']
        }
        mil_test = ep.post(f"folders/{old_mil_folder['uid']}/regression-tests", payload, message="Regression Test MIL vs. MIL")
        # verdictStatus, failed, error, passed, total
        print(f"Result: {mil_test['verdictStatus']}")


    ep.post('coverage-generation', { 'scopeUid' : toplevel_scope_uid, 'pllString': 'MCDC' })
    b2b_coverage = ep.get(f"scopes/{toplevel_scope_uid}/coverage-results-b2b")

    # Create project report using "regression-test" template
    # and export project report to a file called '{model_name}-migration-test.html'
    if test_mil: report_template = 'regression-test'
    else: report_template = 'regression-sil-only'
    report = ep.post(f"scopes/{toplevel_scope_uid}/project-report?template-name={report_template}", message="Creating test report")
    ep.post(f"reports/{report['uid']}", { 'exportPath': result_dir, 'newName': f'{model_name}-migration-test' })

    # Save *.epp, close application unless controlled externally
    ep.put('profiles', { 'path': epp_file })
    if not ep_api_object: ep.close_application()

    # time measurement
    global tmp
    duration_seconds = (datetime.now() - start_time).seconds
    if model_name in tmp: duration_seconds += tmp[model_name]

    result = {
        'projectName' : f'{model_name}_{source_version}-vs-{matlab_version}',
        'duration' : duration_seconds,
        'statementCoverage' : b2b_coverage['StatementPropertyCoverage']['handledPercentage'],
        'mcdcCoverage' : b2b_coverage['MCDCPropertyCoverage']['handledPercentage'],
        'testResult' : sil_test['verdictStatus'],
        'eppPath' : epp_rel_path,
        'reportPath' : f"{model_name}-migration-test.html"
    }
    return result 


def get_existing_references(execution_record_folder):
    mil_executions = [os.path.abspath(p) for p in glob.glob(f"{execution_record_folder}/MIL/*.mdf")]
    sil_executions = [os.path.abspath(p) for p in glob.glob(f"{execution_record_folder}/SIL/*.mdf")]
    return mil_executions, sil_executions

def handle_error(ep, epp_file, step_result):
    step_result['status'] = 'ERROR'
    step_result['message'] = traceback.format_exc()
    ep.put('profiles', { 'path': epp_file }, message="Saving profile")
    print(step_result['message'])

def start_ep_and_configure_matlab(version):
    ep = EPRestApi()
    ep.put('preferences', [ {'preferenceName' : 'GENERAL_MATLAB_CUSTOM_VERSION', 'preferenceValue' : f'MATLAB R{version} (64-bit)' }, { 'preferenceName' : 'GENERAL_MATLAB_VERSION', 'preferenceValue': 'CUSTOM' } ])
    return ep

def get_epp_file_by_name(result_dir, model_path):
    model_name = os.path.basename(model_path)[:-4].replace('Wrapper_', '')
    return os.path.join(result_dir, model_name + '.epp'), model_name + '.epp'
