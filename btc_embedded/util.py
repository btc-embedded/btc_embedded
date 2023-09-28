import platform


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
        errors = f", Error: {response['errorneousTests']}" if not response['errorneousTests'] == '0' else ""
        verdict = "ERROR" if errors else ("FAILED" if not response['failedTests'] == '0' else ("PASSED" if not response['passedTests'] == '0' else "N.A."))
        print(f"- [{config}] Result: {verdict} (Total: {response['totalTests']}, Passed: {response['passedTests']}, Failed: {response['failedTests']}{errors})")


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
