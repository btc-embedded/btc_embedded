import os
import sys
from datetime import datetime

from btc_embedded import EPRestApi, util


def run_btc_tests():
    epp_file = os.path.abspath('test/test.epp')
    project_name = os.path.basename(epp_file)[:-4]
    work_dir = os.path.dirname(epp_file)
    # BTC EmbeddedPlatform API object
    ep = EPRestApi()

    # Load a BTC EmbeddedPlatform profile (*.epp) and update it
    ep.get(f'profiles/{epp_file}', message="Loading test project (old API)")
    # ep.get(f'openprofile?path={epp_file}', message="Loading test project (new API)")
    ep.put('profiles', { 'path': epp_file }, message="Saving test project")
    exit()
    ep.put('architectures?performUpdateCheck=true', message="Updating test project")

    start_time = datetime.now()

    # Execute requirements-based tests
    scopes = ep.get('scopes')
    scope_uids = [scope['uid'] for scope in scopes]
    toplevel_scope_uid = scope_uids[0]
    rbt_exec_payload = {
        'UIDs': scope_uids,
        'data' : {
            'execConfigNames' : [ 'SL MIL', 'SIL' ]
        }
    }
    test_cases = ep.get('test-cases-rbt')
    rbt_response = ep.post('scopes/test-execution-rbt', rbt_exec_payload, message="Executing requirements-based tests")
    rbt_coverage = ep.get(f"scopes/{toplevel_scope_uid}/coverage-results-rbt?goal-types=MCDC")
    util.print_rbt_results(rbt_response, rbt_coverage)

    # automatic test generation
    ep.post('coverage-generation', { 'scopeUid' : toplevel_scope_uid }, message="Generating vectors")
    b2b_coverage = ep.get(f"scopes/{toplevel_scope_uid}/coverage-results-b2b?goal-types=MCDC")

    # B2B TL MIL vs. SIL
    response = ep.post(f"scopes/{toplevel_scope_uid}/b2b", { 'refMode': 'SL MIL', 'compMode': 'SIL' }, message="Executing B2B test")
    util.print_b2b_results(response, b2b_coverage)

    # Dump JUnit XML report
    util.dump_testresults_junitxml(
        b2b_result=response,
        rbt_results=rbt_response,
        scopes=scopes,
        test_cases=test_cases,
        start_time=start_time,
        project_name=project_name,
        output_file=os.path.join(work_dir, 'test_results.xml')
    )

    # Create project report
    report = ep.post(f"scopes/{toplevel_scope_uid}/project-report", message="Creating test report")
    # export project report to a file called 'report.html'
    ep.post(f"reports/{report['uid']}", { 'exportPath': work_dir, 'newName': project_name })

    # Save *.epp
    ep.put('profiles', { 'path': epp_file }, message="Saving test project")


if __name__ == '__main__':
    run_btc_tests()
