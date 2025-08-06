import logging
import glob
import json
import os
import shutil
import time
from datetime import datetime
from urllib.parse import quote

import btc_embedded.util as util
from btc_embedded.api import EPRestApi
from btc_embedded.helpers import apply_tolerances_from_config
from btc_embedded.reporting import create_report_from_json

logger = logging.getLogger('btc_embedded')

message_report_file = None
report_json = None
MIGRATION_PHASE_OLD = 'Old'
MIGRATION_PHASE_NEW = 'New'

def migration_suite_source(models, matlab_version, toolchain_script=None, test_mil=False, export_executions=False, reuse_code=False, vector_gen_settings=None, ep=None):
    """For each of the given models this function generates tests for
    full coverage on the given model using the specified Matlab version,
    then performs a MIL and SIL simulation to record the reference behavior.
    
    models: list of dicts with keys 'model' (mandatory), 'script', 'scopeName', 'environmentXml' (optional)

    In order to pass custom vector generation settings, provide a dictionary
    with the structure accepted by the vector generation endpoint. You only need
    to include the settings you want to change. You don't need to include the 
    'scopeUid' key, as this will be added automatically.
    """
    initialize_report(models=models,
                      title='BTC Migration Test Suite',
                      filename='BTCMigrationTestSuite.html',
                      additional_stats={ 'toolchainScriptSrc' : toolchain_script } if toolchain_script else {})

    # clear results folder
    ep = prepare_ep_and_matlab(MIGRATION_PHASE_OLD, matlab_version, toolchain_script, ep)

    # run migration source part for all models
    model_results = {}
    for old_model in models:
        migration_source(old_model, matlab_version,
            ep_api_object=ep,
            model_results=model_results,
            test_mil=test_mil,
            export_executions=export_executions,
            reuse_code=reuse_code,
            vector_gen_settings=vector_gen_settings)

    ep.close_application()
    return model_results

def migration_suite_target(models, matlab_version, model_results=None, accept_interface_changes=False, test_mil=False, toolchain_script=None, reuse_code=False, ep=None):
    """For each of the given models this function
    imports the reference execution records and simulates the same
    vectors on MIL and SIL based on the specified Matlab version. This
    regression test will show any changed behavior compared to the provided 
    reference execution.
    
    models: list of dicts with keys 'model' (mandatory), 'script', 'scopeName', 'environmentXml' (optional)
    """
    global report_json; report_json = os.path.abspath(os.path.join('results', 'report.json'))
    
    if toolchain_script:
        update_report(additional_stats={ 'toolchainScriptSrc' : toolchain_script } if toolchain_script else {})

    ep = prepare_ep_and_matlab(MIGRATION_PHASE_NEW, matlab_version, toolchain_script, ep)

    # run migration target part for all models and collect results
    for new_model in models:
        migration_target(new_model, matlab_version,
            ep_api_object=ep,
            model_results=model_results,
            accept_interface_changes=accept_interface_changes,
            test_mil=test_mil,
            reuse_code=reuse_code)

    # close application and create summary report
    ep.close_application()
    return model_results

def migration_source(old_model, matlab_version, test_mil=False, ep_api_object=None, model_results=None, export_executions=False, reuse_code=False, vector_gen_settings=None):
    """Generates tests for full coverage on the given model using the
    specified Matlab version, then performs a MIL and SIL simulation
    to record the reference behavior.

    old_model: dict with keys 'model' (mandatory), 'script', 'scopeName', 'environmentXml' (optional)

    Returns the BTC EmbeddedPlatform Project (*.epp).
    """
    global message_report_file
    step_results = []
    start_time = datetime.now()
    model_path, model_name, script_path, environment_xml_path, scope_name = unpack_model_properties(old_model)
    result_dir = os.path.abspath('results')
    message_report_file = os.path.join(result_dir, f'{model_name}_messages.html')
    epp_file, epp_rel_path = get_epp_file_by_name(result_dir, model_path)
    if not model_results == None: model_results[model_name] = step_results
    
    # start ep or use provided api object
    ep, step_result = src_01_start_ep(ep_api_object, matlab_version, model_name, step_results)
    if step_result and step_result['status'] == 'ERROR':
        return get_project_result_item(model_name=model_name, epp_rel_path=epp_rel_path, start_time=start_time, error_message=step_result['message'])
    
    # Empty BTC EmbeddedPlatform profile (*.epp) + Arch Import
    scope_uid, step_result = src_02_import_model(ep, model_path, script_path, environment_xml_path, scope_name, model_name, matlab_version, reuse_code, step_results)
    if step_result and step_result['status'] == 'ERROR':
        return get_project_result_item(model_name=model_name, epp_rel_path=epp_rel_path, start_time=start_time, error_message=step_result['message'])

    # Generate vectors for full coverage
    step_result = src_03_generate_vectors(ep, scope_uid, model_name, vector_gen_settings, step_results)
    if step_result and step_result['status'] == 'ERROR':
        return get_project_result_item(model_name=model_name, epp_rel_path=epp_rel_path, start_time=start_time, error_message=step_result['message'])

    # Simulation
    step_result = src_04_reference_simulation(ep, scope_uid, test_mil, export_executions, result_dir, model_name, step_results)
    if step_result and step_result['status'] == 'ERROR':
        return get_project_result_item(model_name=model_name, epp_rel_path=epp_rel_path, start_time=start_time, error_message=step_result['message'])

    # Save *.epp, close application unless controlled externally
    ep.put('profiles', { 'path': epp_file })
    if not ep_api_object: ep.close_application()

    # time measurement
    duration_seconds = (datetime.now() - start_time).seconds
    update_report(project_item={
        'projectName' : model_name,
        'status' : 'RUNNING', 
        'info' : f"Migration Source step completed.",
        'duration' : duration_seconds
    })

    return epp_file

def migration_target(new_model, matlab_version, test_mil=False, ep_api_object=None, epp_file=None, accept_interface_changes=False, model_results=None, reuse_code=False):
    """Imports the reference execution records and simulates the same
    vectors on MIL and SIL based on the specified Matlab version. This
    regression test will show any changed behavior compared to the provided 
    reference execution.

    new_model: dict with keys 'model' (mandatory), 'script', 'scopeName', 'environmentXml' (optional)

    Produces a test report
    """
    global message_report_file
    start_time = datetime.now()
    model_path, model_name, script_path, _, scope_name = unpack_model_properties(new_model)
    script_path = os.path.abspath(new_model['script']) if 'script' in new_model and new_model['script'] else None
    result_dir = os.path.abspath('results')
    message_report_file = os.path.join(result_dir, f'{model_name}_messages.html')
    step_results = model_results[model_name] if (model_results and model_name in model_results) else []
    reference_executions_dir = step_results[-1]['erDir'] if step_results and 'erDir' in step_results[-1] else None
    if epp_file:
        epp_rel_path = None
        if os.path.realpath(result_dir) in os.path.realpath(epp_file):
            epp_rel_path = os.path.realpath(epp_file).replace(os.path.realpath(result_dir), '')
            while epp_rel_path.startswith(os.sep): epp_rel_path = epp_rel_path[1:]
    else:
        epp_name_suffix = ('_target' if reference_executions_dir else '')
        epp_file, epp_rel_path = get_epp_file_by_name(result_dir, model_path, suffix=epp_name_suffix)
    
    # skip component if neither epp nor execution records directory exist (e.g. due to error in source part)
    epp_file_exists = os.path.isfile(epp_file)
    reference_executions_dir_exists = os.path.isdir(reference_executions_dir) if reference_executions_dir else False
    if not (epp_file_exists or reference_executions_dir_exists): return None
    
    # start ep or use provided api object
    ep, step_result = src_01_start_ep(ep_api_object, matlab_version, model_name, step_results)
    if step_result and step_result['status'] == 'ERROR':
        return get_project_result_item(model_name=model_name, epp_rel_path=epp_rel_path, start_time=start_time, error_message=step_result['message'])
    
    if reference_executions_dir:
        # create profile and import reference execution records
        scope_uid, step_result = tgt_05_profile_with_refs(ep, epp_file, model_path, script_path, scope_name, model_name, matlab_version, reference_executions_dir, test_mil, reuse_code, step_results)
    else:
        # load BTC EmbeddedPlatform profile (*.epp), update architecture and check for interface changes
        scope_uid, step_result = tgt_05_update_and_interface_check(ep, epp_file, model_path, script_path, scope_name, model_name, accept_interface_changes, matlab_version, step_results)
        if step_result and step_result['status'] == 'ERROR':
            return get_project_result_item(model_name=model_name, epp_rel_path=epp_rel_path, start_time=start_time, error_message=step_result['message'])

    # Tolerances
    step_result = tgt_06_tolerances(ep, model_name, step_results)
    if step_result and step_result['status'] == 'ERROR':
        return get_project_result_item(model_name=model_name, epp_rel_path=epp_rel_path, start_time=start_time, error_message=step_result['message'])

    # Regression Test (SIL)
    sil_test, step_result = tgt_06_regression_test_sil(ep, model_name, step_results)
    if step_result and step_result['status'] == 'ERROR':
        return get_project_result_item(model_name=model_name, epp_rel_path=epp_rel_path, start_time=start_time, error_message=step_result['message'])

    # Regression Test (MIL)
    if test_mil:
        mil_test, step_result = tgt_07_regression_test_mil(ep, model_name, step_results)
        if step_result and step_result['status'] == 'ERROR':
            return get_project_result_item(model_name=model_name, epp_rel_path=epp_rel_path, start_time=start_time, error_message=step_result['message'])

    # Create report
    b2b_coverage, step_result = tgt_08_create_report(ep, scope_uid, test_mil, result_dir, model_name, step_results)
    if step_result and step_result['status'] == 'ERROR':
        return get_project_result_item(model_name=model_name, epp_rel_path=epp_rel_path, start_time=start_time, error_message=step_result['message'])

    # Save *.epp, close application unless controlled externally
    ep.put('profiles', { 'path': epp_file })
    if not ep_api_object: ep.close_application()

    # time measurement
    project_result_item = get_project_result_item(model_name, epp_rel_path, start_time, b2b_coverage=b2b_coverage, sil_test=sil_test)
    update_report(project_item=project_result_item)
    return project_result_item

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

def src_01_start_ep(ep_api_object, matlab_version, model_name, results):
    start_time = time.time()
    # check if the ep api object is controlled externally
    if ep_api_object:
        return ep_api_object, None
    else:
        try:
            step_result = { 'stepName' : 'BTC Startup' }
            update_report_running(model_name, step_result)
            ep = start_ep_and_configure_matlab(matlab_version, ep_api_object)
            step_result['status'] = 'PASSED'
        except Exception as e:
            handle_error(ep, step_result, error=e, step_start_time=start_time)
    results.append(step_result)
    return ep, step_result

def src_02_import_model(ep, model_path, script_path, environment_xml_path, scope_name, model_name, matlab_version, reuse_code, results):
    start_time = time.time()
    try:
        step_result = { 'stepName' : 'Import Model' }
        scope_uid = None
        update_report_running(model_name, step_result)
        clear_sl_cachefiles(os.path.dirname(model_path))
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
            # use environment xml if available, otherwise assume default name 'Environment.xml' next to the model
            if environment_xml_path:
                payload['environment'] = environment_xml_path
            else:
                legacy_code_xml = os.path.join(os.path.dirname(model_path), 'Environment.xml')
                if os.path.isfile(legacy_code_xml):
                    payload['environment'] = legacy_code_xml
            if reuse_code:
                payload['useExistingCode'] = True
            ep.post('architectures/targetlink', payload, message=message)
        else:
            raise Exception('Unsupported code generation config.')

        scope_uid = get_scope_uid(ep, scope_name)
        step_result['status'] = 'PASSED'
    except Exception as e:
        handle_error(ep, step_result, error=e, step_start_time=start_time)
    results.append(step_result)
    return scope_uid, step_result

def src_03_generate_vectors(ep, scope_uid, model_name, vector_gen_settings, results):
    start_time = time.time()
    try:
        step_result = { 'stepName' : 'Generate Vectors' }
        update_report_running(model_name, step_result)
        if ep.version >= '22.3p0': # new style vector generation
            if vector_gen_settings: vector_gen_settings['scopeUid'] = scope_uid
            else:
                vector_gen_settings = {
                    'scopeUid' : scope_uid,
                    'pllString': 'STM',
                    'engineSettings' : {
                        'timeoutSeconds': 300,
                        'engineAtg' : { 'timeoutSecondsPerSubsystem' : 100 },
                        'engineCv' : {
                            'coreEngines' : [ { 'name' : 'ISAT' }, { 'name' : 'CBMC' }] ,
                            'maximumNumberOfThreads' : 2
                        }
                    }
                }
        else: # legacy support for old API
            if vector_gen_settings:
                scope = ep.get(f"scopes/{scope_uid}")
                vector_gen_settings['scope'] = scope
            else:
                vector_gen_settings = ep.get('coverage-generation')
                vector_gen_settings['targetDefinitions'] = []
                vector_gen_settings['pllString'] = 'MCDC'
                vector_gen_settings['engineSettings']['engineCv']['coreEngines'] = [
                    { 'name' : 'CBMC', 'enabled' : True },
                    { 'name' : 'ISAT', 'enabled' : True }
                ]
        ep.post('coverage-generation', vector_gen_settings, message="Generating vectors")
        if ep.version >= '22.2p0':
            b2b_coverage = ep.get(f"scopes/{scope_uid}/coverage-results-b2b")
            logger.info('Coverage ' + "{:.2f}%".format(b2b_coverage['MCDCPropertyCoverage']['handledPercentage']))
        step_result['status'] = 'PASSED'
    except Exception as e:
        handle_error(ep, step_result, error=e, step_start_time=start_time)
    results.append(step_result)
    return step_result

def src_04_reference_simulation(ep, scope_uid, test_mil, export_executions, result_dir, model_name, results):
    start_time = time.time()
    try:
        step_result = { 'stepName' : 'Reference Simulation' }
        update_report_running(model_name, step_result)
        
        if ep.version >= '22.1p0':
            mil_sil_configs = ep.get('execution-configs')['execConfigNames'] if test_mil else ['SIL']
            payload = { 'execConfigNames' : mil_sil_configs }
            ep.post(f"scopes/{scope_uid}/testcase-simulation", payload, message=f"Reference Simulation on {payload['execConfigNames']}")
        else: # legacy support for old API
            archs = ep.get('architectures')
            mil_cfg = None
            if any('Simulink' in arch['architectureKind'] for arch in archs): mil_cfg = 'SL MIL'
            if any('Targetlink' in arch['architectureKind'] for arch in archs): mil_cfg = 'TL MIL'
            mil_sil_configs = [ mil_cfg, 'SIL' ] if test_mil else ['SIL']
            scopes = ep.get('scopes')
            payload = {
                'refMode' : mil_sil_configs[0],
                'compMode' : (mil_sil_configs[1] if len(mil_sil_configs) == 2 else mil_sil_configs[0]),
                'UIDs' : [ scope['uid'] for scope in scopes ],
            }
            ep.post('scopes/b2b', payload, message=f"Reference Simulation on {mil_sil_configs}")

        # Store MIL and SIL executions for comparison
        all_execution_records = ep.get('execution-records')
        payload = { "folderKind": "EXECUTION_RECORD" }
        
        # SIL
        if ep.version >= '22.1p0': payload['folderName'] = 'old-sil'
        old_sil_folder = ep.post('folders', payload)
        sil_execution_records_uids = [ er['uid'] for er in all_execution_records if er['executionConfig'] == 'SIL']
        ep.put(f"folders/{old_sil_folder['uid']}/execution-records", { 'UIDs' : sil_execution_records_uids })
        # export to directory
        if export_executions:
            er_dir = os.path.join(result_dir, model_name, 'ER')
            sil_er_dir = os.path.join(er_dir, 'SIL')
            ep.post('execution-records-export', { 'UIDs' : sil_execution_records_uids, 'exportDirectory': sil_er_dir, 'exportFormat' : 'MDF' })

        # MIL
        if test_mil:
            if ep.version >= '22.1p0': payload['folderName'] = 'old-mil'
            old_mil_folder = ep.post('folders', payload)
            mil_execution_config = next(cfg for cfg in mil_sil_configs if 'MIL' in cfg)
            mil_execution_records_uids = [ er['uid'] for er in all_execution_records if er['executionConfig'] == mil_execution_config]
            ep.put(f"folders/{old_mil_folder['uid']}/execution-records", { 'UIDs' : mil_execution_records_uids })
            
            # export to directory
            if export_executions:
                mil_er_dir = os.path.join(er_dir, 'MIL')
                ep.post('execution-records-export', { 'UIDs' : mil_execution_records_uids, 'exportDirectory': mil_er_dir })

        if export_executions:
            step_result['erDir'] = er_dir
        step_result['status'] = 'PASSED'
    except Exception as e:
        handle_error(ep, step_result, error=e, step_start_time=start_time)
    results.append(step_result)
    return step_result

def tgt_05_update_and_interface_check(ep, epp_file, model_path, script_path, scope_name, model_name, accept_interface_changes, matlab_version, results):
    start_time = time.time()
    try:
        step_result = { 'stepName' : 'Update & Check Interface' }
        update_report_running(model_name, step_result)
        clear_sl_cachefiles(os.path.dirname(model_path))

        # load BTC EmbeddedPlatform profile (*.epp) -> Update Model
        ep.get(f'profiles/{epp_file}?discardCurrentProfile=true', message="Migrating profile to " + ep.version)

        # check for interface changes (part 1)
        scope_uid = get_scope_uid(ep, scope_name)
        toplevel_signals_old = [signal['identifier'] for signal in ep.get(f'scopes/{scope_uid}/signals')]

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
        scope_uid = get_scope_uid(ep, scope_name) # fetch again: scopes have new uids after update
        toplevel_signals_new = [signal['identifier'] for signal in ep.get(f'scopes/{scope_uid}/signals')]
        if not (toplevel_signals_old == toplevel_signals_new):
            severity = 'CRITICAL' if accept_interface_changes else 'ERROR'
            msg = f'The interface of {model_name} has changed:'
            hint = f"""
    - old interface: {toplevel_signals_old}
    - new interface: {toplevel_signals_new}"""
            ep.post('messages', { "message": msg, "hint": hint, "severity": severity })
            warning = f"[WARNING] {msg}\n{hint}"
            logger.warning(warning)
            if not accept_interface_changes: raise Exception(warning)
        step_result['status'] = 'PASSED'
    except Exception as e:
        handle_error(ep, step_result, error=e, step_start_time=start_time)
    results.append(step_result)
    return scope_uid, step_result

def tgt_05_profile_with_refs(ep, epp_file, model_path, script_path, scope_name, model_name, matlab_version, reference_executions_dir, test_mil, reuse_code, results):
    start_time = time.time()
    try:
        step_result = { 'stepName' : 'Target Profile & Ref Executions Import' }
        update_report_running(model_name, step_result)

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

        scope_uid = get_scope_uid(ep, scope_name)
        step_result['status'] = 'PASSED'
    except Exception as e:
        handle_error(ep, step_result, error=e, step_start_time=start_time)
    results.append(step_result)
    return scope_uid, step_result

def tgt_06_tolerances(ep, model_name, results):
    start_time = time.time()
    try:
        step_result = { 'stepName' : 'Default Tolerances' }
        update_report_running(model_name, step_result)
        tolerance_definition_found = apply_tolerances_from_config(ep)
        step_result['status'] = 'PASSED' if tolerance_definition_found else 'SKIPPED'
    except Exception as e:
        handle_error(ep, step_result, error=e, step_start_time=start_time)
    results.append(step_result)
    return step_result

def tgt_06_regression_test_sil(ep, model_name, results):
    def legacy_find_folder(ep, exe_config, er_custom_folders):
        for folder in er_custom_folders:
            records = ep.get(f"folders/{folder['uid']}/execution-records")
            if records and records[0]['executionConfig'] == exe_config:
                return folder
        return None

    start_time = time.time()
    try:
        step_result = { 'stepName' : 'Regression Test (SIL)' }
        sil_test = None
        update_report_running(model_name, step_result)

        # identify old folder
        er_custom_folders = [folder for folder in ep.get('folders?kind=EXECUTION_RECORD') if not folder['isDefault']]
        old_sil_folder = next((folder for folder in er_custom_folders if folder['name'] == 'old-sil'), None)
        if not old_sil_folder:
            # legacy support for old API
            old_sil_folder = legacy_find_folder(ep,  'SIL', er_custom_folders)
            if not old_sil_folder: raise Exception("No SIL folder found in execution records")

        # new folder
        payload = {'folderKind': 'EXECUTION_RECORD', 'folderName' : 'new-sil' }
        new_sil_folder = ep.post('folders', payload)
        # regression test
        payload = { 
            'compMode': 'SIL',
            'compFolderUID' : new_sil_folder['uid']
        }
        sil_test = ep.post(f"folders/{old_sil_folder['uid']}/regression-tests", payload, message="Regression Test SIL vs. SIL")
        # verdictStatus, failed, error, passed, total
        logger.info(f"Result: {sil_test['verdictStatus']}")
        step_result['status'] = sil_test['verdictStatus']
    except Exception as e:
        handle_error(ep, step_result, error=e, step_start_time=start_time)
    results.append(step_result)
    return sil_test, step_result

def tgt_07_regression_test_mil(ep, model_name, results):
    start_time = time.time()
    try:
        step_result = { 'stepName' : 'Regression Test (MIL)' }
        update_report_running(model_name, step_result)
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
        logger.info(f"Result: {mil_test['verdictStatus']}")
        step_result['status'] = mil_test['verdictStatus']
    except Exception as e:
        handle_error(ep, step_result, error=e, step_start_time=start_time)
    results.append(step_result)
    return mil_test, step_result

def tgt_08_create_report(ep, scope_uid, test_mil, result_dir, model_name, results):
    start_time = time.time()
    try:
        # Create project report using "regression-test" template
        # and export project report to a file called '{model_name}-migration-test.html'
        step_result = { 'stepName' : 'Create Report' }
        update_report_running(model_name, step_result)

        # try: ep.post('coverage-generation', { 'scopeUid' : scope_uid, 'pllString': 'MCDC' })
        # except: pass
        b2b_coverage = ep.get(f"scopes/{scope_uid}/coverage-results-b2b")
        # select the appropriate report template
        report_template = select_report_template(ep, test_mil)
        query_param = f'?template-name={report_template}' if report_template else ''
        # create report
        report = ep.post(f"scopes/{scope_uid}/project-report{query_param}", message="Creating test report")
        ep.post(f"reports/{report['uid']}", { 'exportPath': result_dir, 'newName': f'{model_name}-migration-test' })
        step_result['status'] = 'PASSED'
    except Exception as e:
        handle_error(ep, step_result, error=e, step_start_time=start_time)
    results.append(step_result)
    return b2b_coverage, step_result

def get_existing_references(execution_record_folder):
    mil_executions = [os.path.abspath(p) for p in glob.glob(f"{execution_record_folder}/MIL/*.mdf")]
    sil_executions = [os.path.abspath(p) for p in glob.glob(f"{execution_record_folder}/SIL/*.mdf")]
    return mil_executions, sil_executions

def handle_error(ep, step_result, epp_file=None, error="", step_start_time=None):
    if step_result and 'name' in step_result and error:
        logger.error(f"Encountered error in step '{step_result['stepName']}': {error}")
    step_result['status'] = 'ERROR'
    # only show first line of error, prevents ugly long stack traces
    shortened_error = str(error).split("\n")[0]
    if len(shortened_error) > 60: shortened_error = shortened_error[0:60] + '...'
    step_result['message'] = f"Error in step '{step_result['stepName']}': {shortened_error}"
    if epp_file: ep.put('profiles', { 'path': epp_file }, message="Saving profile after error")
    # export messages to {model_name}_messages.html
    if ep.version >= '22.2p0':
        global message_report_file
        os.makedirs(os.path.dirname(message_report_file), exist_ok=True)
        message_report_uri = f'messages/message-report?file-name={quote(message_report_file, safe="")}'
        if ep.message_marker_date:
            message_report_uri += f'&marker-date={ep.message_marker_date}'
        ep.post(message_report_uri)
        errors_from_log = ep.get_errors_from_log(step_start_time)
        with open(f"{message_report_file[:-13]}error.log", 'w') as log:
            log.writelines(errors_from_log)

def start_ep_and_configure_matlab(version, ep):
    if not ep: ep = EPRestApi()
    ep.put('preferences', [ {'preferenceName' : 'GENERAL_MATLAB_CUSTOM_VERSION', 'preferenceValue' : f'MATLAB R{version} (64-bit)' }, { 'preferenceName' : 'GENERAL_MATLAB_VERSION', 'preferenceValue': 'CUSTOM' } ])
    return ep

def prepare_ep_and_matlab(migration_phase, matlab_version, toolchain_script=None, ep=None):
    try:
        # start ep, connect to selected matlab version
        ep = start_ep_and_configure_matlab(matlab_version, ep)
        ep_version = ep.get('openapi.json')['info']['version']
        update_report(additional_stats={ f'{migration_phase} Config' : f'BTC {ep_version}, Matlab {matlab_version}' })
        
        # evaluate toolchain script in the base workspace
        if toolchain_script: 
            util.run_matlab_script(ep=ep, matlab_script_abs_path=os.path.abspath(toolchain_script))

    except Exception as e:
        update_report(additional_stats={
            'status': 'ERROR',
            'globalMessage' : f"Error during preparation of Migration phase '{migration_phase}': {e}" })
        raise e
    
    return ep

def get_epp_file_by_name(result_dir, model_path, suffix=''):
    epp_filename = os.path.basename(get_wrapper_free_path(model_path))[:-4] + suffix + '.epp'
    return os.path.join(result_dir, epp_filename), epp_filename

def get_wrapper_free_path(model_path):
    dir, basename = os.path.dirname(model_path), os.path.basename(model_path)
    if basename.startswith('Wrapper_'):
        name_without_wrapper = basename[len('Wrapper_'):]
        if os.path.exists(os.path.join(dir, name_without_wrapper)):
            basename = name_without_wrapper
    return os.path.join(dir, basename)

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
        [os.remove(os.path.join(dir, file)) for file in glob.glob(f"{dir}/*.slxc")]
        [shutil.rmtree(os.path.join(dir, rtw_dir)) for rtw_dir in glob.glob(f"{dir}/*_rtw")]
    except Exception as e:
        raise Exception(f"Error removing model cache files in '{dir}'. " + repr(e))

def get_scope_uid(ep, scope_name):
    """
    Retrieve the UID of a specific scope from the endpoint.
    Args:
        ep: EPRestApi object
        scope_name (str): The name of the scope to retrieve the UID for. If None, the UID of the first scope is returned.
    Returns:
        str: The UID of the specified scope.
    Raises:
        Exception: If the specified scope name is not found in the endpoint's scopes.
    """
    scopes = ep.get('scopes')
    if scope_name:
        scope = next((scope for scope in scopes if scope['name'] == scope_name), None)
        if not scope: raise Exception(f"Scope '{scope_name}' not found.")
    else:
        scope = scopes[0]
    return scope['uid']

def unpack_model_properties(model_dict):
    """
    Extracts and returns various properties from a model dictionary.
    Args:
        model_dict (dict): A dictionary containing model properties. Expected keys are:
            - 'model': Path to the model file.
            - 'script' (optional): Path to the script file.
            - 'environmentXml' (optional): Path to the environment XML file.
            - 'scopeName' (optional): Name of the scope.
    Returns:
        tuple: A tuple containing:
            - model_path (str): Absolute path to the model file.
            - model_name (str): Base name of the model file.
            - script_path (str or None): Absolute path to the script file, or None if not provided.
            - environment_xml_path (str or None): Absolute path to the environment XML file, or None if not provided.
            - scope_name (str or None): Name of the scope, or None if not provided.
    """
    model_path = os.path.abspath(model_dict['model'])
    model_name = os.path.basename(get_wrapper_free_path(model_path))[:-4]
    script_path = os.path.abspath(model_dict['script']) if 'script' in model_dict and model_dict['script'] else None
    environment_xml_path = os.path.abspath(model_dict['environmentXml']) if 'environmentXml' in model_dict and model_dict['environmentXml'] else None
    scope_name = model_dict['scopeName'] if 'scopeName' in model_dict else None
    return model_path, model_name, script_path, environment_xml_path, scope_name

def get_project_result_item(model_name, epp_rel_path, start_time, b2b_coverage=None, sil_test=None, error_message=None, info=""):
    global report_json
    
    duration_seconds = ""
    if report_json:
        # calculate duration in seconds
        # if previous durations for this model are available, add those
        duration_seconds = (datetime.now() - start_time).seconds
        with open(report_json, 'r') as f:
            report_data = json.load(f)
            intermediate_results = report_data['results']
            if model_name in intermediate_results and 'duration' in intermediate_results[model_name]:
                duration_seconds += intermediate_results[model_name]['duration']

    # return project result item
    result = {
        'projectName' : model_name,
        'eppPath' : epp_rel_path,
        'reportPath' : f"{model_name}-migration-test.html",
        'duration' : duration_seconds,
        'errorMessage' : error_message,
        'status' : 'COMPLETED'
    }
    if info: result['info'] = info
    if b2b_coverage:
        result['statementCoverage'] = b2b_coverage['StatementPropertyCoverage']['handledPercentage']
        result['mcdcCoverage'] = b2b_coverage['MCDCPropertyCoverage']['handledPercentage']
    if sil_test:
        result['testResult'] = sil_test['verdictStatus']
    if error_message:
        result['status'] = 'ERROR'
        result['testResult'] = 'ERROR'
        result['reportPath'] = f"{model_name}_messages.html"
        result['info'] = error_message
        update_report(project_item=result, additional_stats={'status': 'ERROR'})

    return result

def update_report(project_item=None, additional_stats={}):
    global report_json
    if report_json:
        # load existing state
        with open(report_json, "r") as f:
            report_data = json.load(f)

        # add information
        if project_item:
            if project_item['projectName'] in report_data['results']:
                # update existing item
                old_project_item = report_data['results'][project_item['projectName']]
                old_project_item.update(project_item)
            else:
                # add new item
                report_data['results'][project_item['projectName']] = project_item

        if additional_stats:
            if 'additionalStats' in report_data:
                # clear status & globalMessage
                if 'status' not in additional_stats and 'status' in report_data['additionalStats']:
                    del report_data['additionalStats']['status']
                if 'globalMessage' not in additional_stats and 'globalMessage' in report_data['additionalStats']:
                    del report_data['additionalStats']['globalMessage']
                # update existing additional_stats section
                report_data['additionalStats'].update(additional_stats)
            else:
                # add new additional_stats section
                report_data['additionalStats'] = additional_stats

        # dump updated state
        with open(report_json, "w") as f:
            json.dump(report_data, f, indent=4)

        create_report_from_json(json_path=report_json)

def initialize_report(models, title, filename, additional_stats={}):
    global report_json; report_json = os.path.abspath(os.path.join('results', 'report.json'))
    os.makedirs(os.path.dirname(report_json), exist_ok=True)
    report_data = {
        'title' : title,
        'filename' : filename,
        'results' : { },
        'additionalStats' : additional_stats
    }

    # add all models as "scheduled"
    for model in models:
        project_name = os.path.basename(get_wrapper_free_path(model['model']))[:-4]
        report_data['results'][project_name] = {
            "projectName" : project_name,
            "status" : "SCHEDULED"
        }

    # persist as json file
    with open(report_json, 'w') as f:
        json.dump(report_data, f, indent=4)

    # trigger html creation
    create_report_from_json(json_path=report_json)

def update_report_running(model_name, step_result):
    update_report(project_item={'projectName' : model_name, 'status' : 'RUNNING', 'info' : f"{step_result['stepName']}..." })
