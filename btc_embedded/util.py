import os
import shutil
import zipfile


def run_matlab_script(ep, matlab_script_abs_path):
    """Evaluates the given script in the matlab base workspace:
    **evalin('base', 'run(matlab_script_abs_path)')**"""
    ep.post('execute-long-matlab-script',
        {
            'scriptName' : 'evalin',
            'inArgs' : [ 'base', f"run('{matlab_script_abs_path}')" ]
        },
        message=f"Evaluating '{matlab_script_abs_path}' in Matlab base workspace.")


def print_rbt_results(response, coverage_response=None):
    """Example on how to access coverage and test result data.
    Depending on your desired CI-workflow, you would usually not just print
    the test results and coverage values, but react on failed tests or coverage
    levels below a given threshold."""
    test_results = response['testResults']
    print("Requirements-based Test Results:")
    if coverage_response:
        coverage = coverage_response['MCDCPropertyCoverage']
        print(f" - Coverage: {coverage['handledPercentage']}% MC/DC")
    for config in test_results.keys():
        r = test_results[config]
        errors = f", Error: {r['errorneousTests']}" if not r['errorneousTests'] == '0' else ""
        verdict = "ERROR" if errors else ("FAILED" if not r['failedTests'] == '0' else ("PASSED" if not r['passedTests'] == '0' else "N.A."))
        print(f"- [{config}] Result: {verdict} (Total: {r['totalTests']}, Passed: {r['passedTests']}, Failed: {r['failedTests']}{errors})")


def print_b2b_results(response, coverage_response=None):
    """Example on how to access coverage and test result data.
    Depending on your desired CI-workflow, you would usually not just print
    the test results and coverage values, but react on failed tests or coverage
    levels below a given threshold."""
    errors = f", Error: {response['error']}" if response['error'] else ""
    print("Back-to-Back Test Results:")
    print(f"- [{response['referenceMode']} vs. {response['comparisonMode']}] Result: {response['verdictStatus']} " +
          f"(Total: {response['total']}, Passed: {response['passed']}, Accepted: {response['failedAccepted']}, Failed: {response['failed']}{errors})")
    if coverage_response:
        coverage = coverage_response['MCDCPropertyCoverage']
        print(f"  Coverage: {coverage['handledPercentage']}% MC/DC")

def determine_codegen_type(ep, model_file):
    
    def extract_slx(slx_file):
        # Create a temporary directory to extract model content
        temp_dir = os.path.join(os.path.dirname(slx_file), "_tmpmodelcontent")
        os.makedirs(temp_dir, exist_ok=True)

        if slx_file.endswith('.slx'):
            # Extract the .slx file into the temporary directory
            with zipfile.ZipFile(slx_file, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)
        elif slx_file.endswith('.mdl'):
            shutil.copyfile(slx_file, os.path.join(temp_dir, 'model.mdl'))
        else:
            raise Exception("Unsupported model type: " + slx_file[:-4])

        return temp_dir
    
    def check_tl(temp_dir):
        # pick the right file to analyze (slx vs. mdl)
        if os.path.isfile(os.path.join(temp_dir, 'simulink/systems/system_root.xml')):
            tl_file = os.path.join(temp_dir, 'simulink/systems/system_root.xml')
        elif os.path.isfile(os.path.join(temp_dir, 'model.mdl')):
            tl_file = os.path.join(temp_dir, 'model.mdl')
        else:
            return False

        # search for 'tllib/TargetLink Main Dialog' string in file
        tl_string  = 'tllib/TargetLink Main Dialog'
        with open(tl_file, 'r') as file:
            for line in file:
                if tl_string in line:
                    return True
        
        # no TargetLink main dialog found
        return False

# --> this check leaves the model in a broken state, would at least need to call close_system
#     currently not considered valuable enough to be included. Assuming !TL => EC
#
#     def check_ec(ep, model_file):
#         script_content = f"""
# load_system('{model_file}');
# activeConfigSet = getActiveConfigSet(gcs);
# stf = get_param(activeConfigSet, 'SystemTargetFile');
# """
#         ep.post('execute-long-matlab-script', {'scriptName' : 'evalin', 'inArgs' : [ 'caller', script_content ]})
#         response = ep.post('execute-long-matlab-script', {'scriptName' : 'evalin', 'inArgs' : [ 'caller', 'stf' ], 'outArgs' : 1})
#         tlc = response['outArgs'][0]
#         ec_tlc_excludes = [ 'grt.tlc', 'realtime.tlc', 'rsim.tlc', 'rtwsfunction.tlc' ]
#         valid_tlc = not tlc in ec_tlc_excludes
#         return valid_tlc

    if not os.path.isfile(model_file): raise Exception(f"Model file '{model_file}' not found.")
    try:
        # extract model xml content
        temp_dir = extract_slx(model_file)
        # Fallback for neither TL nor EC -> plain simulink or unsupported TLC
        codegen_type = None

        # first, check if model uses TL codegen
        is_tl_model = check_tl(temp_dir)
        
        if is_tl_model:
            codegen_type = "TL"
        else:
            codegen_type = "EC"

        # clean up model xml content
        shutil.rmtree(temp_dir, ignore_errors=True)    
        
        return codegen_type
    except:
        # clean up model xml content
        if temp_dir: shutil.rmtree(temp_dir, ignore_errors=True)
