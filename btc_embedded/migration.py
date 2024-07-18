import glob
import os
import shutil
from datetime import datetime
from urllib.parse import quote

import btc_embedded.util as util
from btc_embedded.api import EPRestApi
from btc_embedded.helpers import apply_tolerances_from_config
from btc_embedded.reporting import create_test_report_summary

tmp = {}
source_version = None
message_report_file = None

def migration_suite_source(models, matlab_version, toolchain_script=None, test_mil=False, export_executions=False, reuse_code=False, ep=None):
    """For each of the given models this function generates tests for
    full coverage on the given model using the specified Matlab version,
    then performs a MIL and SIL simulation to record the reference behavior."""
    global source_version
    source_version = matlab_version
    
    # clear results folder
    shutil.rmtree('results', ignore_errors=True)
    
    # start ep, connect to selected matlab version and run toolchain script
    ep = start_ep_and_configure_matlab(matlab_version, ep)
    if toolchain_script: # evaluate toolchain script in the base workspace
        util.run_matlab_script(os.path.abspath(toolchain_script))

    # run migration source part for all models
    model_results = {}
    for old_model in models:
        migration_source(old_model, matlab_version,
            ep_api_object=ep,
            model_results=model_results,
            test_mil=test_mil,
            export_executions=export_executions,
            reuse_code=reuse_code)

    ep.close_application()
    return model_results

def migration_suite_target(models, matlab_version, model_results=None, accept_interface_changes=False, test_mil=False, toolchain_script=None, reuse_code=False,ep=None):
    """For each of the given models this function
    imports the reference execution records and simulates the same
    vectors on MIL and SIL based on the specified Matlab version. This
    regression test will show any changed behavior compared to the provided 
    reference execution."""
    results = []

    # start ep, connect to selected matlab version and run toolchain script
    ep = start_ep_and_configure_matlab(matlab_version, ep)
    if toolchain_script: # evaluate toolchain script in the base workspace
        ep.post('execute-long-matlab-script', {'scriptName' : 'evalin', 'inArgs' : [ 'base', toolchain_script ]})

    # run migration target part for all models and collect results
    for new_model in models:
        result = migration_target(new_model, matlab_version,
            ep_api_object=ep,
            model_results=model_results,
            accept_interface_changes=accept_interface_changes,
            test_mil=test_mil,
            reuse_code=reuse_code)
        results.append(result)

    # close application and create summary report
    ep.close_application()
    create_test_report_summary(results, 'BTC Migration Test Suite', 'BTCMigrationTestSuite.html', 'results')
    return model_results

def migration_source(old_model, matlab_version, test_mil=False, ep_api_object=None, model_results=None, export_executions=False, reuse_code=False):
    """Generates tests for full coverage on the given model using the
    specified Matlab version, then performs a MIL and SIL simulation
    to record the reference behavior.

    Returns the BTC EmbeddedPlatform Project (*.epp).
    """
    global message_report_file
    step_results = []
    start_time = datetime.now()
    model_path = os.path.abspath(old_model['model'])
    model_name = os.path.basename(model_path)[:-4].replace('Wrapper_', '')
    script_path = os.path.abspath(old_model['script']) if 'script' in old_model and old_model['script'] else None
    result_dir = os.path.abspath('results')
    message_report_file = os.path.join(result_dir, f'{model_name}_messages.html')
    epp_file, epp_rel_path = get_epp_file_by_name(result_dir, model_path)
    
    # start ep or use provided api object
    ep, step_result = src_01_start_ep(ep_api_object, matlab_version, step_results)
    if step_result and step_result['status'] == 'ERROR':
        return get_project_result_item(model_name, matlab_version, epp_rel_path, start_time, error_message=step_result['message'])
    
    # Empty BTC EmbeddedPlatform profile (*.epp) + Arch Import
    toplevel_uid, step_result = src_02_import_model(ep, model_path, script_path, model_name, matlab_version, reuse_code, step_results)
    if step_result and step_result['status'] == 'ERROR':
        return get_project_result_item(model_name, matlab_version, epp_rel_path, start_time, error_message=step_result['message'])

    # Generate vectors for full coverage
    step_result = src_03_generate_vectors(ep, toplevel_uid, step_results)
    if step_result and step_result['status'] == 'ERROR':
        return get_project_result_item(model_name, matlab_version, epp_rel_path, start_time, error_message=step_result['message'])

    # Simulation
    step_result = src_04_reference_simulation(ep, toplevel_uid, test_mil, export_executions, result_dir, step_results)
    if step_result and step_result['status'] == 'ERROR':
        return get_project_result_item(model_name, matlab_version, epp_rel_path, start_time, error_message=step_result['message'])

    # Save *.epp, close application unless controlled externally
    ep.put('profiles', { 'path': epp_file })
    if not ep_api_object: ep.close_application()

    # time measurement
    global tmp
    duration_seconds = (datetime.now() - start_time).seconds
    tmp[model_name] = duration_seconds
    if not model_results == None: model_results[model_name] = step_results

    return epp_file

def migration_target(new_model, matlab_version, test_mil=False, ep_api_object=None, epp_file=None, accept_interface_changes=False, model_results=None, reuse_code=False):
    """Imports the reference execution records and simulates the same
    vectors on MIL and SIL based on the specified Matlab version. This
    regression test will show any changed behavior compared to the provided 
    reference execution.

    Produces a test report
    """
    global message_report_file
    start_time = datetime.now()
    model_path = os.path.abspath(new_model['model'])
    model_name = os.path.basename(model_path)[:-4].replace('Wrapper_', '')
    script_path = os.path.abspath(new_model['script']) if 'script' in new_model and new_model['script'] else None
    result_dir = os.path.abspath('results')
    message_report_file = quote(os.path.join(result_dir, f'{model_name}_messages.html'))
    step_results = model_results[model_name] if model_results else []
    if step_results and 'erDir' in step_results[-1]:
        reference_executions_dir = step_results[-1]['erDir']
    else:
        reference_executions_dir = None
    if epp_file:
        epp_rel_path = None
        if os.path.realpath(result_dir) in os.path.realpath(epp_file):
            epp_rel_path = os.path.realpath(epp_file).replace(os.path.realpath(result_dir), '')
            while epp_rel_path.startswith(os.sep): epp_rel_path = epp_rel_path[1:]
    else:
        epp_name_suffix = ('_target' if reference_executions_dir else '')
        epp_file, epp_rel_path = get_epp_file_by_name(result_dir, model_path, suffix=epp_name_suffix)
    
    # start ep or use provided api object
    ep, step_result = src_01_start_ep(ep_api_object, matlab_version, step_results)
    if step_result and step_result['status'] == 'ERROR':
        return get_project_result_item(model_name, matlab_version, epp_rel_path, start_time, error_message=step_result['message'])
    
    if reference_executions_dir:
        # create profile and import reference execution records
        toplevel_uid, step_result = tgt_05_profile_with_refs(ep, epp_file, model_path, script_path, model_name, matlab_version, reference_executions_dir, test_mil, reuse_code, step_results)
    else:
        # load BTC EmbeddedPlatform profile (*.epp), update architecture and check for interface changes
        toplevel_uid, step_result = tgt_05_update_and_interface_check(ep, epp_file, model_path, script_path, model_name, accept_interface_changes, matlab_version, step_results)
        if step_result and step_result['status'] == 'ERROR':
            return get_project_result_item(model_name, matlab_version, epp_rel_path, start_time, error_message=step_result['message'])

    # Tolerances
    step_result = tgt_06_tolerances(ep, step_results)
    if step_result and step_result['status'] == 'ERROR':
        return get_project_result_item(model_name, matlab_version, epp_rel_path, start_time, error_message=step_result['message'])

    # Regression Test (SIL)
    sil_test, step_result = tgt_06_regression_test_sil(ep, step_results)
    if step_result and step_result['status'] == 'ERROR':
        return get_project_result_item(model_name, matlab_version, epp_rel_path, start_time, error_message=step_result['message'])

    # Regression Test (MIL)
    if test_mil:
        mil_test, step_result = tgt_07_regression_test_mil(ep, step_results)
        if step_result and step_result['status'] == 'ERROR':
            return get_project_result_item(model_name, matlab_version, epp_rel_path, start_time, error_message=step_result['message'])

    # Create report
    b2b_coverage, step_result = tgt_08_create_report(ep, toplevel_uid, test_mil, result_dir, model_name, step_results)
    if step_result and step_result['status'] == 'ERROR':
        return get_project_result_item(model_name, matlab_version, epp_rel_path, start_time, error_message=step_result['message'])

    # Save *.epp, close application unless controlled externally
    ep.put('profiles', { 'path': epp_file })
    if not ep_api_object: ep.close_application()

    # time measurement
    return get_project_result_item(model_name, matlab_version, epp_rel_path, start_time, b2b_coverage=b2b_coverage, sil_test=sil_test)

def migration_test(old_model, old_matlab, new_model=None, new_matlab=None, test_mil=False):
    """Convenience 1-liner to test:
    - if a given model yields the same results with a different matlab version
    - if a refactored model yields the same results

    By default, only SIL <-> SIL is tested
    """
    # step 1
    btc_project = migration_source(old_model, old_matlab, test_mil=test_mil)
    
    # clean up if same model is used
    new_matlab = new_matlab if new_matlab else old_matlab
    new_model = new_model if new_model else old_model
    if (new_model['model'] == old_model['model']):
        model_dir = os.path.dirname(new_model['model'])
        clear_sl_cachefiles(model_dir)

    # step 2
    result = migration_target(new_model, new_matlab, epp_file=btc_project)
    return result

def src_01_start_ep(ep_api_object, matlab_version, results):
    # check if the ep api object is controlled externally
    if ep_api_object:
        return ep_api_object, None
    else:
        try:
            step_result = { 'stepName' : 'BTC Startup' }
            ep = start_ep_and_configure_matlab(matlab_version, ep_api_object)
            step_result['status'] = 'PASSED'
        except Exception as e:
            handle_error(ep, step_result)
    results.append(step_result)
    return ep, step_result

def src_02_import_model(ep, model_path, script_path, model_name, matlab_version, reuse_code, results):
    try:
        step_result = { 'stepName' : 'Import Model' }
        toplevel_uid = None
        ep.post('profiles?discardCurrentProfile=true')
        message=f"Importing {model_name}  with Matlab R{matlab_version}"

        # perform architecture import based on codegen type
        codegen_type = util.determine_codegen_type(ep, model_path)
        if codegen_type == 'EC':
            payload = {
                'ecModelFile' : model_path,
                'ecInitScript' : script_path
            }
            if reuse_code:
                payload['useExistingCode'] = True
            ep.post('architectures/embedded-coder', payload, message=message)
        elif codegen_type == 'TL':
            payload = {
                'tlModelFile' : model_path,
                'tlInitScript' : script_path
            } 
            legacy_code_xml = os.path.join(os.path.dirname(model_path), 'LegacyCode.xml')
            if os.path.isfile(legacy_code_xml):
                payload['environment'] = legacy_code_xml
            if reuse_code:
                payload['useExistingCode'] = True
            ep.post('architectures/targetlink', payload, message=message)
        else:
            raise Exception('Unsupported code generation config.')

        toplevel_uid = ep.get('scopes')[0]['uid']
        step_result['status'] = 'PASSED'
    except Exception as e:
        handle_error(ep, step_result)
    results.append(step_result)
    return toplevel_uid, step_result

def src_03_generate_vectors(ep, toplevel_uid, results):
    try:
        step_result = { 'stepName' : 'Generate Vectors' }
        vector_gen_settings = {
            'scopeUid' : toplevel_uid,
            'pllString': 'MCDC',
            'engineSettings' : {
                'timeoutSeconds': 300,
                'engineAtg' : { 'timeoutSecondsPerSubsystem' : 15 },
                'engineCv' : {
                    'coreEngines' : [ { 'name' : 'ISAT' }, { 'name' : 'CBMC' }] ,
                    'maximumNumberOfThreads' : 2
                }
            }
        }
        ep.post('coverage-generation', vector_gen_settings, message="Generating vectors")
        b2b_coverage = ep.get(f"scopes/{toplevel_uid}/coverage-results-b2b")
        print('Coverage ' + "{:.2f}%".format(b2b_coverage['MCDCPropertyCoverage']['handledPercentage']))
        step_result['status'] = 'PASSED'
    except Exception as e:
        handle_error(ep, step_result)
    results.append(step_result)
    return step_result

def src_04_reference_simulation(ep, toplevel_uid, test_mil, export_executions, result_dir, results):
    try:
        mil_sil_configs = ep.get('execution-configs')['execConfigNames']
        step_result = { 'stepName' : 'Reference Simulation' }
        payload = { 'execConfigNames' : mil_sil_configs if test_mil else ['SIL'] }
        ep.post(f"scopes/{toplevel_uid}/testcase-simulation", payload, message=f"Reference Simulation on {payload['execConfigNames']}")

        # Store MIL and SIL executions for comparison
        all_execution_records = ep.get('execution-records')
        payload = { "folderKind": "EXECUTION_RECORD" }
        
        # SIL
        payload['folderName'] = 'old-sil'
        old_sil_folder = ep.post('folders', payload)
        sil_execution_records_uids = [ er['uid'] for er in all_execution_records if er['executionConfig'] == 'SIL']
        ep.put(f"folders/{old_sil_folder['uid']}/execution-records", { 'UIDs' : sil_execution_records_uids })
        # export to directory
        if export_executions:
            sil_er_dir = os.path.join(result_dir, 'ER', 'SIL')
            ep.post('execution-records-export', { 'UIDs' : sil_execution_records_uids, 'exportDirectory': sil_er_dir })

        # MIL
        if test_mil:
            payload['folderName'] = 'old-mil'
            old_mil_folder = ep.post('folders', payload)
            mil_execution_config = next(cfg for cfg in mil_sil_configs if 'MIL' in cfg)
            mil_execution_records_uids = [ er['uid'] for er in all_execution_records if er['executionConfig'] == mil_execution_config]
            ep.put(f"folders/{old_mil_folder['uid']}/execution-records", { 'UIDs' : mil_execution_records_uids })
            
            # export to directory
            if export_executions:
                mil_er_dir = os.path.join(result_dir, 'ER', 'MIL')
                ep.post('execution-records-export', { 'UIDs' : mil_execution_records_uids, 'exportDirectory': mil_er_dir })

        step_result['erDir'] = os.path.join(result_dir, 'ER')
        step_result['status'] = 'PASSED'
    except Exception as e:
        handle_error(ep, step_result)
    results.append(step_result)
    return step_result

def tgt_05_update_and_interface_check(ep, epp_file, model_path, script_path, model_name, accept_interface_changes, matlab_version, results):
    try:
        step_result = { 'stepName' : 'Update & Check Interface' }
        # load BTC EmbeddedPlatform profile (*.epp) -> Update Model
        ep.get(f'profiles/{epp_file}?discardCurrentProfile=true')

        # check for interface changes (part 1)
        toplevel_uid = ep.get('scopes')[0]['uid']
        toplevel_signals_old = [signal['identifier'] for signal in ep.get(f'scopes/{toplevel_uid}/signals')]

        # Arch Update
        message=f"Updating model & generating code for {model_name} with Matlab {matlab_version}"
        # get mil config (can be TL MIL or SL MIL)
        mil_config = next(cfg for cfg in ep.get('execution-configs')['execConfigNames'] if 'MIL' in cfg)
        if mil_config == 'SL MIL':
            payload = {
                'slModelFile' : model_path,
                'slInitScript' : script_path
            } 
        elif mil_config == 'TL MIL':
            payload = {
                'tlModelFile' : model_path,
                'tlInitScript' : script_path
            } 
        else:
            raise Exception(f"Unsupported architecture / config: '{mil_config}'")
        ep.put(f"architectures/model-paths", payload)
        ep.put('architectures', message=message)
        
        # check for interface changes (part 2)
        toplevel_uid = ep.get('scopes')[0]['uid'] # fetch again: scopes have new uids after update
        toplevel_signals_new = [signal['identifier'] for signal in ep.get(f'scopes/{toplevel_uid}/signals')]
        if not (toplevel_signals_old == toplevel_signals_new):
            severity = 'CRITICAL' if accept_interface_changes else 'ERROR'
            msg = f'The interface of {model_name} has changed:'
            hint = f"""
    - old interface: {toplevel_signals_old}
    - new interface: {toplevel_signals_new}"""
            ep.post('messages', { "message": msg, "hint": hint, "severity": severity })
            warning = f"[WARNING] {msg}\n{hint}"
            print(warning)
            if not accept_interface_changes: raise Exception(warning)
        step_result['status'] = 'PASSED'
    except Exception as e:
        handle_error(ep, step_result)
    results.append(step_result)
    return toplevel_uid, step_result

def tgt_05_profile_with_refs(ep, epp_file, model_path, script_path, model_name, matlab_version, reference_executions_dir, test_mil, reuse_code, results):
    try:
        step_result = { 'stepName' : 'Target Profile & Ref Executions Import' }
        ep.post('profiles?discardCurrentProfile=true')

        # perform architecture import based on codegen type
        message=f"Importing {model_name}  with Matlab R{matlab_version}"
        codegen_type = util.determine_codegen_type(ep, model_path)
        if codegen_type == 'EC':
            payload = {
                'ecModelFile' : model_path,
                'ecInitScript' : script_path
            }
            if reuse_code:
                payload['useExistingCode'] = True
            ep.post('architectures/embedded-coder', payload, message=message)
        elif codegen_type == 'TL':
            payload = {
                'tlModelFile' : model_path,
                'tlInitScript' : script_path
            } 
            if reuse_code:
                payload['useExistingCode'] = True
            ep.post('architectures/targetlink', payload, message=message)
        else:
            raise Exception('Unsupported code generation config.')

        # import reference executions
        mil_executions, sil_executions = get_existing_references(reference_executions_dir)
        # SIL
        if sil_executions:
            payload = {'folderKind': 'EXECUTION_RECORD', 'folderName' : 'old-sil' }
            old_sil_folder = ep.post('folders', payload)
            payload = { 'paths' : sil_executions, 'kind' : 'SIL', 'folderUID' : old_sil_folder['uid']}
            ep.post('execution-records', payload, message='Importing SIL reference executions')

        # MIL
        if test_mil and mil_executions:
            # get mil config (can be TL MIL or SL MIL)
            mil_config = next(cfg for cfg in ep.get('execution-configs')['execConfigNames'] if 'MIL' in cfg)
            payload = {'folderKind': 'EXECUTION_RECORD', 'folderName' : 'old-mil' }
            old_mil_folder = ep.post('folders', payload)
            payload = { 'paths' : mil_executions, 'kind' : mil_config, 'folderUID' : old_mil_folder['uid']}
            ep.post('execution-records', payload, message='Importing MIL reference executions')
        
        # saving target profile
        ep.put('profiles', { 'path': epp_file })

        toplevel_uid = ep.get('scopes')[0]['uid']
        step_result['status'] = 'PASSED'
    except Exception as e:
        handle_error(ep, step_result)
    results.append(step_result)
    return toplevel_uid, step_result

def tgt_06_tolerances(ep, results):
    try:
        step_result = { 'stepName' : 'Default Tolerances' }
        tolerance_definition_found = apply_tolerances_from_config(ep)
        step_result['status'] = 'PASSED' if tolerance_definition_found else 'SKIPPED'
    except Exception as e:
        handle_error(ep, step_result)
    results.append(step_result)
    return step_result

def tgt_06_regression_test_sil(ep, results):
    try:
        step_result = { 'stepName' : 'Regression Test (SIL)' }
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
        step_result['status'] = sil_test['verdictStatus']
    except Exception as e:
        handle_error(ep, step_result)
    results.append(step_result)
    return sil_test, step_result

def tgt_07_regression_test_mil(ep, results):
    try:
        step_result = { 'stepName' : 'Regression Test (MIL)' }
        # get mil config (can be TL MIL or SL MIL)
        mil_config = next(cfg for cfg in ep.get('execution-configs')['execConfigNames'] if 'MIL' in cfg)
        payload = {'folderKind': 'EXECUTION_RECORD', 'folderName' : 'new-mil' }
        new_mil_folder = ep.post('folders', payload)
        old_mil_folder = ep.get('folders?name=old-mil')[0]
        # regression test
        payload = { 
            'compMode': mil_config,
            'compFolderUID' : new_mil_folder['uid']
        }
        mil_test = ep.post(f"folders/{old_mil_folder['uid']}/regression-tests", payload, message="Regression Test MIL vs. MIL")
        # verdictStatus, failed, error, passed, total
        print(f"Result: {mil_test['verdictStatus']}")
        step_result['status'] = mil_test['verdictStatus']
    except Exception as e:
        handle_error(ep, step_result)
    results.append(step_result)
    return mil_test, step_result

def tgt_08_create_report(ep, toplevel_uid, test_mil, result_dir, model_name, results):
    try:
        # Create project report using "regression-test" template
        # and export project report to a file called '{model_name}-migration-test.html'
        step_result = { 'stepName' : 'Create Report' }
        # try: ep.post('coverage-generation', { 'scopeUid' : toplevel_uid, 'pllString': 'MCDC' })
        # except: pass
        b2b_coverage = ep.get(f"scopes/{toplevel_uid}/coverage-results-b2b")
        # select the appropriate report template
        report_template = select_report_template(ep, test_mil)
        query_param = f'?template-name={report_template}' if report_template else ''
        # create report
        report = ep.post(f"scopes/{toplevel_uid}/project-report{query_param}", message="Creating test report")
        ep.post(f"reports/{report['uid']}", { 'exportPath': result_dir, 'newName': f'{model_name}-migration-test' })
        step_result['status'] = 'PASSED'
    except Exception as e:
        handle_error(ep, step_result)
    results.append(step_result)
    return b2b_coverage, step_result

def get_existing_references(execution_record_folder):
    mil_executions = [os.path.abspath(p) for p in glob.glob(f"{execution_record_folder}/MIL/*.mdf")]
    sil_executions = [os.path.abspath(p) for p in glob.glob(f"{execution_record_folder}/SIL/*.mdf")]
    return mil_executions, sil_executions

def handle_error(ep, step_result, epp_file=None):
    step_result['status'] = 'ERROR'
    step_result['message'] = f"Error in step '{step_result['stepName']}'"
    if epp_file: ep.put('profiles', { 'path': epp_file }, message="Saving profile after error")
    # export messages to {model_name}_messages.html
    global message_report_file
    os.makedirs(os.path.dirname(message_report_file), exist_ok=True)
    ep.post(f'messages/message-report?file-name={quote(message_report_file, safe="")}&marker-date={ep.message_marker_date}')

def start_ep_and_configure_matlab(version, ep):
    if not ep: ep = EPRestApi()
    ep.put('preferences', [ {'preferenceName' : 'GENERAL_MATLAB_CUSTOM_VERSION', 'preferenceValue' : f'MATLAB R{version} (64-bit)' }, { 'preferenceName' : 'GENERAL_MATLAB_VERSION', 'preferenceValue': 'CUSTOM' } ])
    return ep

def get_epp_file_by_name(result_dir, model_path, suffix=''):
    model_name = os.path.basename(model_path)[:-4].replace('Wrapper_', '') + suffix
    return os.path.join(result_dir, model_name + '.epp'), model_name + '.epp'

def select_report_template(ep, test_mil):
    # pick the right report template
    if test_mil:
        mil_config = next(cfg for cfg in ep.get('execution-configs')['execConfigNames'] if 'MIL' in cfg)
        report_template = 'regression-test-ec' if mil_config == 'SL MIL' else 'regression-test-tl'
    else:
        report_template = 'regression-test-sil-only'
    return report_template

def clear_sl_cachefiles(dir=os.getcwd()):
    try:
        shutil.rmtree(os.path.join(dir, 'slprj'), ignore_errors=True)
        shutil.rmtree(os.path.join(dir, 'TLProj'), ignore_errors=True)
        shutil.rmtree(os.path.join(dir, 'TLSim'), ignore_errors=True)
        [os.remove(os.path.join(dir, file)) for file in glob.glob('*.slxc', root_dir=dir)]
        [shutil.rmtree(os.path.join(dir, rtw_dir)) for rtw_dir in glob.glob('*_rtw', root_dir=dir)]
    except Exception as e:
        raise Exception(f"Error removing model cache files in '{dir}'. " + repr(e))

def get_project_result_item(model_name, matlab_version, epp_rel_path, start_time, b2b_coverage=None, sil_test=None, error_message=None):
    # calculate duration in seconds
    global tmp
    global source_version
    duration_seconds = (datetime.now() - start_time).seconds
    if model_name in tmp: duration_seconds += tmp[model_name]
    # return project result item
    result = {
        'projectName' : f'{model_name}_{source_version}-vs-{matlab_version}',
        'eppPath' : epp_rel_path,
        'reportPath' : f"{model_name}-migration-test.html",
        'duration' : duration_seconds,
        'errorMessage' : error_message
    }
    if b2b_coverage:
        result['statementCoverage'] = b2b_coverage['StatementPropertyCoverage']['handledPercentage']
        result['mcdcCoverage'] = b2b_coverage['MCDCPropertyCoverage']['handledPercentage']
    if sil_test:
        result['testResult'] = sil_test['verdictStatus']
    if error_message:
        result['testResult'] = 'ERROR'
        result['reportPath'] = f"{model_name}_messages.html"
    
    return result
