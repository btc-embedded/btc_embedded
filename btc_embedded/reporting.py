import logging
import datetime
import getpass
import json
import os
import re

from btc_embedded.config import get_resource_path

logger = logging.getLogger('btc_embedded')

def create_report_from_json(json_path):
    target_dir = os.path.dirname(json_path)
    with open(json_path, 'r') as f:
        data = json.load(f)
        create_test_report_summary(results=data['results'],
                                   additional_stats=data['additionalStats'],
                                   report_title=data['title'],
                                   report_name=data['filename'],
                                   target_dir=target_dir)

# 
# ----------------------------- Main-function -----------------------------
# 
def create_test_report_summary(results={}, report_title='BTC Test Report Summary', report_name='BTCTestReportSummary.html', target_dir='.', additional_stats={}):
    """Takes a dict of individual results an creates a summary report including additional metadata stats."""
    def total_duration(results):
        try: 
            return sum(project['duration'] for _, project in results.items() if 'duration' in project or 0)
        except:
            return 0

    def overall_status(results, additional_stats):
        try:
            if 'status' in additional_stats: return additional_stats['status']
            if any(project["testResult"] == "ERROR" for _, project in results.items() if "testResult" in project): return "ERROR"
            if any(project["testResult"] == "FAILED" for _, project in results.items() if "testResult" in project): return "FAILED"
            if any(project["testResult"] == "PASSED" for _, project in results.items() if "testResult" in project): return "PASSED"
        except: 
            pass
        return "NO_VERDICT"

    def additional_stats_string(additional_stats):
        additional_stats_string = ""
        if additional_stats:
            for key, value in additional_stats.items():
                additional_stats_string += f'<tr><td class="colA">{camelCaseToDisplayName(key)}</td><td class="colB">{value}</td></tr>'
        return additional_stats_string

    # aggregate total_duration and overall_status
    total_duration_seconds = total_duration(results)
    projects_with_duration = [r for _, r in results.items() if 'duration' in r]

    # prepare projects_string, containing info for all projects
    projects_string = ''
    for _, result in results.items():
        projects_string += get_project_string(result, target_dir) + '\r\n'

    # import html template
    with open(get_resource_path('btc_summary_report.template'), 'r') as template_file:
        html_template = template_file.read()

    # fill placeholders in template
    final_html = html_template.replace('__title__', report_title)\
                              .replace('__creator__', getpass.getuser() or os.getenv('USERNAME') or os.getenv('USER'))\
                              .replace('__timestamp__', datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))\
                              .replace('__totalDuration__', seconds_to_hms(total_duration_seconds) if total_duration_seconds else "")\
                              .replace('__averageDuration__', seconds_to_hms(total_duration_seconds // len(projects_with_duration)) if total_duration_seconds else "")\
                              .replace('__overallStatus__', overall_status(results, additional_stats))\
                              .replace('__numberOfProjects__', str(len(results)))\
                              .replace('__numberOfProjectsPassed__', str(sum(1 for _, project in results.items() if "testResult" in project and project["testResult"] == "PASSED")))\
                              .replace('__numberOfProjectsFailed__', str(sum(1 for _, project in results.items() if "testResult" in project and project["testResult"] == "FAILED")))\
                              .replace('__additional_global_stats__', additional_stats_string(additional_stats))\
                              .replace('__projects__', projects_string)

    # Write the final HTML file
    target_file_path = os.path.abspath(os.path.join(target_dir, report_name))
    with open(target_file_path, "w") as target_file:
        target_file.write(final_html)


#
# ----------------------------- Sub-functions -----------------------------
#

def get_additional_stats_string(additional_stats):
    additional_stats_string = ""
    if additional_stats:
        for key, value in additional_stats.items():
            additional_stats_string += f'<tr><td class="colA">{camelCaseToDisplayName(key)}</td><td class="colB">{value}</td></tr>'
    return additional_stats_string


def get_project_string(result, target_dir):
    target_dir_abs = os.path.abspath(target_dir).replace('\\', '/')
    
    if 'reportPath' in result and os.path.isabs(result['reportPath']):
        report_relpath = os.path.relpath(result['reportPath'], target_dir_abs).replace('\\', '/')
    elif 'reportPath' in result:
        report_relpath = result['reportPath'].replace('\\', '/')
    else:
        report_relpath = None

    if 'eppPath' in result and os.path.isabs(result['eppPath']):
        epp_relpath = os.path.relpath(result['eppPath'], target_dir_abs).replace('\\', '/')
    elif 'eppPath' in result:
        epp_relpath = result['eppPath'].replace('\\', '/')
    else:
        epp_relpath = None

    # we need to replace the following placeholders:
    # - projectName      : can be eppName without extension
    # - testResult       : PASSED / FAILED / NO_VERDICT / ERROR
    # - statementCoverage
    # - mcdcCoverage
    # - reportPath       : path to project report.html
    # - eppPath          : path to project.epp
    # - eppName          : name of the project.epp (incl. extension) -> eppPath basename
    # - duration         : duration in the form hh:mm:ss
    template = '<tr><td><span class="{statusIconClass}" title="{statusMessage}"> </span></td><td>{reportLink}</td><td>{infoText}</td><td><a href="{eppPath}">{eppName}</a></td><td>{duration}</td><td><div class="result_container"><div class="{testResult}"/><b>{testResult}</b></div></td></tr>'
    # Fill in the HTML template with the data
    # 
    if 'statementCoverage' in result and 'mcdcCoverage' in result:
        info = f'{result["statementCoverage"]:.2f}% Statement, {result["mcdcCoverage"]:.2f}% MC/DC'
    elif 'errorMessage' in result:
        info = result['errorMessage']
    elif 'info' in result:
        info = result['info']
    else:
        info = ''
    if not "status" in result or result["status"] in ['SCHEDULED', 'RUNNING']: statusIcon = 'icon-mc'
    elif result["status"] in ['PASSED', 'COMPLETED']: statusIcon = 'icon-sdc'
    elif result["status"] == 'FAILED': statusIcon = 'icon-wdc'
    elif result["status"] == 'ERROR': statusIcon = 'icon-edc'

    report_link = f'<a href="{report_relpath}">{result["projectName"]}</a>' if report_relpath else result["projectName"]
    project_html_entry = template.format(
        projectName = result["projectName"],
        testResult = result["testResult"] if "testResult" in result else "",
        reportPath = report_relpath,
        eppPath = epp_relpath,
        eppName = os.path.basename(result["eppPath"]) if "eppPath" in result else "",
        duration = seconds_to_hms(result["duration"]) if "duration" in result else "",
        statusIconClass = statusIcon,
        statusMessage = result["status"],
        infoText = info,
        reportLink = report_link
    )
    return project_html_entry

def camelCaseToDisplayName(camelCaseString):
    words = re.findall(r'[A-Z][a-z]*|[a-z]+', camelCaseString)
    return ' '.join(words).title()

def seconds_to_hms(seconds):
    """Converts a seconds value (like 42343) into an hh:mm:ss value (like 11:45:43)"""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"