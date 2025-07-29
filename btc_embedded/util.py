import logging
import json
import os
import shutil
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime

logger = logging.getLogger('btc_embedded')

def run_matlab_script(ep, matlab_script_abs_path):
    """Evaluates the given script in the matlab base workspace:
    **evalin('base', 'run(matlab_script_abs_path)')**"""
    ep.post('execute-long-matlab-script',
        {
            'scriptName' : 'evalin',
            'inArgs' : [ 'base', f"run('{matlab_script_abs_path}')" ]
        },
        message=f"Evaluating '{matlab_script_abs_path}' in Matlab base workspace.")

def run_matlab_function(ep, matlab_script_abs_path, args=[]):
    """Adds the script's parent directory to the matlab path,
    then executes the script with the given arguments.

    If you want to simply run a function that is already known to Matlab,
    please use ep.post('execute-long-matlab-script') directly."""
    if not (matlab_script_abs_path[-2:] == '.m') and (os.path.isabs(matlab_script_abs_path)):
        raise Exception(f"Expecting absolute path to a matlab script file (*.m) but received '{matlab_script_abs_path}'")
    
    # add m-script's parent dir to matlab path
    script_dir, script_file = os.path.split(matlab_script_abs_path)
    script_name = script_file[:-2]
    ep.post('execute-long-matlab-script',
        {
            'scriptName' : 'addpath',
            'inArgs' : [ script_dir ]
        })
    
    # execute script with arguments
    ep.post('execute-long-matlab-script',
        {
            'scriptName' : script_name,
            'inArgs' : args
        })

def print_rbt_results(response, coverage_response=None):
    """Example on how to access coverage and test result data.
    Depending on your desired CI-workflow, you would usually not just print
    the test results and coverage values, but react on failed tests or coverage
    levels below a given threshold."""
    test_results = response['testResults']
    logger.info("Requirements-based Test Results:")
    if coverage_response:
        coverage = coverage_response['MCDCPropertyCoverage']
        logger.info(f" - Coverage: {coverage['handledPercentage']:.2f}% MC/DC")
    for config in test_results.keys():
        r = test_results[config]
        if isinstance(r['totalTests'], str):
            errors = f", Error: {r['errorneousTests']}" if not r['errorneousTests'] == '0' else ""
            verdict = "ERROR" if errors else ("FAILED" if not r['failedTests'] == '0' else ("PASSED" if not r['passedTests'] == '0' else "N.A."))
        else: # since 24.3 integers are used instead of strings
            errors = f", Error: {r['errorneousTests']}" if not r['errorneousTests'] == 0 else ""
            verdict = "ERROR" if errors else ("FAILED" if not r['failedTests'] == 0 else ("PASSED" if not r['passedTests'] == 0 else "N.A."))
        logger.info(f"- [{config}] Result: {verdict} (Total: {r['totalTests']}, Passed: {r['passedTests']}, Failed: {r['failedTests']}{errors})")

def print_b2b_results(response, coverage_response=None):
    """Example on how to access coverage and test result data.
    Depending on your desired CI-workflow, you would usually not just print
    the test results and coverage values, but react on failed tests or coverage
    levels below a given threshold."""
    errors = f", Error: {response['error']}" if response['error'] else ""
    logger.info("Back-to-Back Test Results:")
    logger.info(f"- [{response['referenceMode']} vs. {response['comparisonMode']}] Result: {response['verdictStatus']} " +
          f"(Total: {response['total']}, Passed: {response['passed']}, Accepted: {response['failedAccepted']}, Failed: {response['failed']}{errors})")
    if coverage_response:
        coverage = coverage_response['MCDCPropertyCoverage']
        logger.info(f"  Coverage: {coverage['handledPercentage']:.2f}% MC/DC")
        
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


def dump_testresults_mochajson(file, rbt_response, exec_start_time, exec_end_time, test_cases):
    """Dumps the test results in the mocha-json format (beta-status):
    - file shall be an absolute path
    - rbt_response the response of the requirements-based test execution post call
    - exec_start/end time shall be datetime objects
    - test_cases shall be the result of ep.get('test-cases-rbt')"""
    delta = exec_end_time - exec_start_time
    tc_uid_to_name = {tc['uid']: tc['name'] for tc in test_cases}
    report = {
        "stats": {
            "suites": len(rbt_response["testResults"]),
            "tests": sum(suite["totalTests"] for suite in rbt_response["testResults"].values()),
            "passes": sum(suite["passedTests"] for suite in rbt_response["testResults"].values()),
            "pending": sum(suite["skippedTests"] for suite in rbt_response["testResults"].values()),
            "failures": sum(suite["failedTests"] for suite in rbt_response["testResults"].values()),
            "start": exec_start_time.isoformat() + "Z",
            "end": exec_end_time.isoformat() + "Z",
            "duration": delta.total_seconds() * 1000
        },
        "suites": [],
        "tests": [],
        "passes": [],
        "failures": [],
        "pending": []
    }

    for execModeName, em in rbt_response["testResults"].items():
        for result in em["testResults"]:
            tc_name = tc_uid_to_name[result["rbTestCaseUID"]]
            test_case = {
                "title": tc_name,
                "fullTitle": tc_name,
                "file": execModeName, 
                "duration": 0,
                "currentRetry": 0,
                "err": {},
                "state": result["verdictStatus"].lower()
            }

            if result["verdictStatus"] == "PASSED":
                report["passes"].append(test_case)
            elif result["verdictStatus"] == "FAILED":
                test_case["err"] = {
                    "message": result["execResultMessages"][0]["message"] if result["execResultMessages"] else "No error message",
                    #"stack": "Error: " + (result["execResultMessages"][0]["message"] if result["execResultMessages"] else "No error message")
                }
                report["failures"].append(test_case)
            elif result["verdictStatus"] == "NO_VERDICT":
                report["pending"].append(test_case)

            report["tests"].append(test_case)
            
    with open(file, "w") as json_file:
        json.dump(report, json_file, indent=4) 

def dump_testresults_junitxml(
    b2b_result=None,
    rbt_results=None,
    regression_results=None,
    test_cases=None,
    scopes=None,
    project_name="",
    start_time=None,
    output_file='test_results.xml'):
    """Dumps the test results in the JUnit XML format:
    - Creates a testsuite with n testcases per execution config of requirements-based tests (MIL, SIL, ...)
        - n testcases per suite (depending on number of tests)
        - messages will be attached in case of error/failure
        - the scope path of the test case is used as the classname
    - Creates a testsuite for back-to-back tests (if present)
        - 1 testcase in total
        - toplevel scope path used as classname
    - Creates a testsuite for regression tests
        - 1 testcase per regression test (e.g. MIL-MIL, SIL-SIL, ...)
        - toplevel scope path used as classname
    """
    
    # Create the root element <testsuites>
    testsuites = ET.Element('testsuites', name=project_name)
    tcs_by_uid = { tc['uid'] : tc for tc in test_cases } if test_cases else None
    scopes_by_uid = { scope['uid'] : scope for scope in scopes } if scopes else None
    total_tests = total_tests = total_errors = total_failures = total_skipped = 0
    output_file = os.path.abspath(output_file)
    if start_time: duration_seconds = (datetime.now() - start_time).seconds

    # Helper function to add test cases
    def add_testcase(testsuite, name, status, messages=None, classname=None):
        testcase = ET.SubElement(testsuite, 'testcase', name=name)
        if classname: testcase.set('classname', classname)
        if status == 'FAILED':
            failure = ET.SubElement(testcase, 'failure')
            if messages:
                failure.text = "\n".join(messages)
        elif status == 'ERROR':
            error = ET.SubElement(testcase, 'error')
            if messages:
                error.text = "\n".join(messages)

    # 1. Create RBT Test Suites for MIL and SIL
    if rbt_results:
        for execution_config, rbt_response in rbt_results['testResults'].items():
            # Test Suite Name (e.g. "Requirements-based Tests MIL" or "Requirements-based Tests SIL")
            suite_name = f"Requirements-based Tests {execution_config}"
            testsuite = ET.SubElement(testsuites, 'testsuite', name=suite_name)

            # sort by tc name
            rbt_response['testResults'].sort(key=lambda item: tcs_by_uid[item['rbTestCaseUID']]['name'] if tcs_by_uid else item['rbTestCaseUID'])
            for test_result in rbt_response['testResults']:
                ts_tests = ts_tests = ts_errors = ts_failures = ts_skipped = 0
                tc_name = tcs_by_uid[test_result['rbTestCaseUID']]['name'] if tcs_by_uid else test_result['rbTestCaseUID']
                scope_uid = tcs_by_uid[test_result['rbTestCaseUID']]['scopeUID'] if tcs_by_uid else None
                classname = scopes_by_uid[scope_uid]['path'] if scope_uid else ""
                
                # count
                total_tests += 1
                ts_tests += 1
                if test_result['verdictStatus'] == 'ERROR':
                    total_errors += 1
                    ts_errors += 1
                if test_result['verdictStatus'] == 'FAILED':
                    total_failures += 1
                    ts_failures += 1
                if test_result['verdictStatus'] in ['NO_VERDICT', 'MISSING_EXECUTION']:
                    total_skipped += 1
                    ts_skipped += 1

                add_testcase(
                    testsuite,
                    name=tc_name,
                    classname=classname,
                    status=test_result['verdictStatus'],
                    messages=[msg['message'] for msg in test_result['execResultMessages']]
                )
            
            testsuite.set('tests', str(total_tests))
            testsuite.set('errors', str(total_errors))
            testsuite.set('failures', str(total_failures))
            testsuite.set('skipped', str(total_skipped))

    # 2. Create B2B Test Suite
    if b2b_result:
        b2b_testsuite = ET.SubElement(testsuites, 'testsuite', name=f"B2B Test {b2b_result['referenceMode']} vs. {b2b_result['comparisonMode']}")
        classname = scopes[0]['path']
        add_testcase(
            b2b_testsuite,
            name=f"B2B Test {b2b_result['referenceMode']} vs. {b2b_result['comparisonMode']}",
            status=b2b_result['verdictStatus'],
            classname=classname
        )
        total_tests += 1
        b2b_testsuite.set('tests', '1')
        if b2b_result['verdictStatus'] == 'ERROR':
            total_errors += 1
            b2b_testsuite.set('errors', '1')
        if b2b_result['verdictStatus'] == 'FAILED':
            total_failures += 1
            b2b_testsuite.set('failures', '1')

    # 3. Create Regression Test Suite
    if regression_results:
        regression_testsuite = ET.SubElement(testsuites, 'testsuite', name="Regression Tests")
        classname = scopes[0]['path']
        for regression_result in regression_results:
            total_tests += 1
            regression_testsuite.set('tests', '1')
            if regression_result['verdictStatus'] == 'ERROR':
                total_errors += 1
                regression_testsuite.set('errors', '1')
            if regression_result['verdictStatus'] == 'FAILED':
                total_failures += 1
                regression_testsuite.set('failures', '1')
            add_testcase(
                regression_testsuite,
                name=f"{regression_result['name']} ({regression_result['referenceMode']}-{regression_result['comparisonMode']})",
                status=regression_result['verdictStatus'],
                classname=classname
            )

    # Write the XML tree to a file
    testsuites.set('tests', str(total_tests))
    testsuites.set('errors', str(total_errors))
    testsuites.set('failures', str(total_failures))
    testsuites.set('skipped', str(total_skipped))
    testsuites.set('timestamp', datetime.now().isoformat())
    if duration_seconds: testsuites.set('time', str(duration_seconds))

    tree = ET.ElementTree(testsuites)
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    tree.write(output_file, encoding='utf-8', xml_declaration=True)
