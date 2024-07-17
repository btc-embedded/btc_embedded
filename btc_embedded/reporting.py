import datetime
import os
from importlib import resources


# 
# ----------------------------- Main-function -----------------------------
# 
def create_test_report_summary(results, report_title='BTC Test Report Summary', report_name='BTCTestReportSummary.html', target_dir='.'):
    """
    Takes a list of individual results and creates a summary report from it.
    
    The results objects are expected to contain the following fields:
    - projectName
    - duration (integer indicating the duration in seconds)
    - statementCoverage
    - mcdcCoverage
    - testResult (PASSED / FAILED / ERROR / SKIPPED)
    - eppPath (path to the *.epp file)
    - reportPath (path to the project's html report)
    """
    if not results:
        print("No data provided to 'create_test_report_summary' method.")
        return
    
    # aggregate total_duration and overall_status
    total_duration = sum(project['duration'] for project in results)
    overall_status = "ERROR" if any(project["testResult"] == "ERROR" for project in results) else ("FAILED" if any(project["testResult"] == "FAILED" for project in results) else "PASSED")
    
    # prepare projects_string, containing info for all projects
    projects_string = ''
    for result in results:
        projects_string += get_project_string(result, target_dir) + '\r\n'

    # import html template
    with open(os.path.join(resources.files('btc_embedded'), 'resources', 'btc_summary_report.template'), 'r') as template_file:
        html_template = template_file.read()

    # fill placeholders in template
    final_html = html_template.replace('__title__', report_title)\
                              .replace('__creator__', os.getenv('USERNAME') or os.getlogin())\
                              .replace('__timestamp__', datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))\
                              .replace('__totalDuration__', seconds_to_hms(total_duration))\
                              .replace('__averageDuration__', seconds_to_hms(total_duration // len(results)))\
                              .replace('__overallStatus__', overall_status)\
                              .replace('__numberOfProjects__', str(len(results)))\
                              .replace('__numberOfProjectsPassed__', str(sum(1 for project in results if project["testResult"] == "PASSED")))\
                              .replace('__numberOfProjectsFailed__', str(sum(1 for project in results if project["testResult"] == "FAILED")))\
                              .replace('__projects__', projects_string)

    # Write the final HTML file
    target_file_path = os.path.abspath(os.path.join(target_dir, report_name))
    with open(target_file_path, "w") as target_file:
        target_file.write(final_html)


#
# ----------------------------- Sub-functions -----------------------------
#

def get_project_string(result, target_dir):
    target_dir_abs = os.path.abspath(target_dir).replace('\\', '/')
    report_abspath = os.path.abspath(result['reportPath']).replace('\\', '/')
    epp_abspath = os.path.abspath(result['eppPath']).replace('\\', '/')
    report_relpath = os.path.relpath(report_abspath, target_dir_abs)
    epp_relpath = os.path.relpath(epp_abspath, target_dir_abs)

    # we need to replace the following placeholders:
    # - projectName      : can be eppName without extension
    # - testResult       : PASSED / FAILED / NO_VERDICT / ERROR
    # - statementCoverage
    # - mcdcCoverage
    # - reportPath       : path to project report.html
    # - eppPath          : path to project.epp
    # - eppName          : name of the project.epp (incl. extension) -> eppPath basename
    # - duration         : duration in the form hh:mm:ss
    template = '<tr><td><span class="{statusIconClass}" title="{statusMessage}"> </span></td><td><a href="{reportPath}">{projectName}</a></td><td>{infoText}</td><td><a href="{eppPath}">{eppName}</a></td><td>{duration}</td><td><div class="result_container"><div class="{testResult}"/><b>{testResult}</b></div></td></tr>'
    # Fill in the HTML template with the data
    # 
    if 'statementCoverage' in result and 'mcdcCoverage' in result:
        info = f'{result["statementCoverage"]:.2f}% Statement, {result["mcdcCoverage"]:.2f}% MC/DC'
    elif 'errorMessage' in result:
        info = result['errorMessage']
    else:
        info = ''
    project_html_entry = template.format(
        projectName = result["projectName"],
        testResult = result["testResult"],
        reportPath = report_relpath,
        eppPath = epp_relpath,
        eppName = os.path.basename(result["eppPath"]),
        duration = seconds_to_hms(result["duration"]),
        statusIconClass = ('icon-sdc' if result["testResult"] == 'PASSED' else 'icon-wdc' if result["testResult"] == 'FAILED' else 'icon-edc'),
        statusMessage = result["testResult"],
        infoText = info
    )
    return project_html_entry


def seconds_to_hms(seconds):
    """Converts a seconds value (like 42343) into an hh:mm:ss value (like 11:45:43)"""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"