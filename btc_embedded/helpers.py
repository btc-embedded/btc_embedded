import logging
import json
import os
import re
import shutil
import subprocess
from decimal import Decimal

import yaml

from btc_embedded.config import (BTC_CONFIG_DEFAULTLOCATION,
                                 BTC_CONFIG_ENVVAR_NAME, get_resource_path)
import socket


logger = logging.getLogger('btc_embedded')

VERSION_PATTERN_2 = r'(\d+\.\d+[a-zA-Z]\d+)' # e.g.   "24.3p1"
KNOWN_FLOAT_TYPES = [ 'double', 'single', 'float', 'float32', 'float64', 'real' ]

def install_btc_config():
    import winreg

    def _get_subkeys(key):
        index = 0
        try:
            while True:
                subkey_name = winreg.EnumKey(key, index)
                yield subkey_name
                index += 1
        except:
            pass
    if BTC_CONFIG_ENVVAR_NAME in os.environ and os.path.exists(os.environ[BTC_CONFIG_ENVVAR_NAME]):
        return
    if not BTC_CONFIG_ENVVAR_NAME in os.environ:
        # set variable for this session
        os.environ[BTC_CONFIG_ENVVAR_NAME] = BTC_CONFIG_DEFAULTLOCATION
    if os.path.exists(BTC_CONFIG_DEFAULTLOCATION):
        return
    else:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\BTC", access=winreg.KEY_READ | winreg.KEY_WOW64_64KEY)
        ep_version = None
        for subkey_name in _get_subkeys(key):
            if subkey_name.startswith("EmbeddedPlatform"):
                ep_key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\BTC\{subkey_name}")
                value_data = 0
                try:
                    value_data, _ = winreg.QueryValueEx(ep_key, "EPACTIVE")
                except:
                    #older versions do not contain the EPACTIVE key
                    value_data = 0
                if value_data == '1':
                    # version
                    match = re.search(VERSION_PATTERN_2, subkey_name)
                    if match: ep_version = match.group(1)
                    # install location
                    value_data, _ = winreg.QueryValueEx(ep_key, "Path")
                    install_location = value_data
                    # matlab
                    highest_ml_version = None
                    for subkey_name in _get_subkeys(ep_key):
                        if subkey_name.startswith("MATLAB"):
                            highest_ml_version = subkey_name
                        # higher values will overwrite this

        if ep_version and install_location:
            config_file_template = get_resource_path('btc_config_windows.yml')
            with open(config_file_template, 'r') as f:
                config = yaml.safe_load(f) or {}
                config['installationRoot'] = install_location.replace(f'ep{ep_version}', '')[:-1]
                config['epVersion'] = ep_version
                if highest_ml_version:
                    config['preferences']['GENERAL_MATLAB_CUSTOM_VERSION'] = highest_ml_version

            # dump adapted template to btc_config location
            global_config = os.environ[BTC_CONFIG_ENVVAR_NAME]
            
            with open(global_config, 'w') as f:
                yaml.safe_dump(config, f)
            
            logger.info(f"Applied initial btc_config template to '{global_config}'.")
            logger.info(f"""Please verify the initial configuration:
    - BTC EmbeddedPlatform {ep_version} (installed at: '{install_location}')
    - {highest_ml_version}
    - Compiler: {config['preferences']['GENERAL_COMPILER_SETTING']}
""")
            return config

def install_report_templates(template_folder):
    try:
        def xml_filter(_, names): return [name for name in names if not name.endswith('.xml')]
        os.makedirs(template_folder, exist_ok=True)
        resources_folder = get_resource_path('projectreport_templates')
        shutil.copytree(resources_folder, template_folder, ignore=xml_filter, dirs_exist_ok=True)
        logger.info(f"Installed project report templates to '{template_folder}'")
    except:
        logger.warning(f"[WARNING] Could not install report templates to '{template_folder}'")

def set_tolerances(ep, tol_fxp={ 'abs': '1*LSB' }, tol_flp={ 'abs': 1E-16, 'rel': 1E-8 }, tol_regex=[], use_case='B2B'):
    """Tolerances can be defined for RBT (requirements-based tests) and B2B (back-to-back & regression tests)
and will automatically be applied (supported with EP 24.1 and beyond)
For each scope, for each DISP/OUT the signal is checked:
1. Does the signal name match any of the "signal-name-based" tolerance definitions?
  -> first matching tolerance definition is applied (based on regex <-> signal-name)
  If no signal-name based tolerance was defined, default tolerances based no data type are considered:
2. Does the signal use a floating point data type? [ 'double', 'single', 'float', 'float32', 'float64', 'real' ]
  -> apply default tolerances for floats (if defined)
3. Does the signal use a fixed-point data type? (integer with LSB < 1)
  -> apply default tolerances for fixed-point (if defined)
  -> tolerance can also be defined as a multiple of the LSB (e.g. 1*LSB)

abs: absolute tolerance - a deviation <= abs will be accepted as PASSED
rel: relative tolerance - accepted deviation <= (reference value * rel) will be accepted as PASSED
     useful for floats to compensate for low precision on high float values
    """
    subsystems_and_signal_data = _collect_scope_signal_data(ep, tol_fxp, tol_flp, tol_regex)
    if subsystems_and_signal_data:
        tolerance_xml_file = _generate_tolerance_xml(subsystems_and_signal_data)
        _apply_tolerances_to_profile(ep, tolerance_xml_file, use_case)

def apply_tolerances_from_config(ep):
    """Tolerances can be defined for RBT (requirements-based tests) and B2B (back-to-back & regression tests)
and will automatically be applied (supported with EP 24.1 and beyond)
For each scope, for each DISP/OUT the signal is checked:
1. Does the signal name match any of the "signal-name-based" tolerance definitions?
  -> first matching tolerance definition is applied (based on regex <-> signal-name)
  If no signal-name based tolerance was defined, default tolerances based no data type are considered:
2. Does the signal use a floating point data type? [ 'double', 'single', 'float', 'float32', 'float64', 'real' ]
  -> apply default tolerances for floats (if defined)
3. Does the signal use a fixed-point data type? (integer with LSB < 1)
  -> apply default tolerances for fixed-point (if defined)
  -> tolerance can also be defined as a multiple of the LSB (e.g. 1*LSB)

abs: absolute tolerance - a deviation <= abs will be accepted as PASSED
rel: relative tolerance - accepted deviation <= (reference value * rel) will be accepted as PASSED
     useful for floats to compensate for low precision on high float values
    """
    config = ep.config
    if config and 'tolerances' in config and ep._does_api_support_signalinfo():
        tolerance_definition_found = True
        for use_case in [ 'RBT', 'B2B' ]:
            if use_case in config['tolerances']:
                tol_b2b = config['tolerances'][use_case]
                tolerances_flp = tol_b2b['floating-point'] if 'floating-point' in tol_b2b else None
                tolerances_fxp = tol_b2b['fixed-point'] if 'fixed-point' in tol_b2b else None
                tolerances_regex = tol_b2b['signal-name-based'] if 'signal-name-based' in tol_b2b else None
                set_tolerances(ep, use_case=use_case,
                    tol_flp=tolerances_flp,
                    tol_fxp=tolerances_fxp,
                    tol_regex=tolerances_regex)
    else:
        tolerance_definition_found = False
    return tolerance_definition_found

def _collect_scope_signal_data(ep, tol_fxp, tol_flp, tol_regex):
    # query tolerances based on category (using model name)
    xml_subsystems = []
    scopes = ep.get('scopes')
    scopes = [scope for scope in scopes]
    for scope in scopes:
        # check apply_to / FLOAT_FLOAT, etc.
        signals = ep.get(f"scopes/{scope['uid']}/signals")
        signal_infos = [ep.get(f"/signals/{signal['uid']}/signal-datatype-information") for signal in signals]

        scope_path = scope['path'] if not scope['topLevel'] else ''
        # TEMPORARY WORKAROUND: weird scope path without first /
        # (see http://jira.osc.local:8080/browse/EP-3337)
        first_slash_idx = scope_path.find('/')
        if not first_slash_idx == -1: scope_path = scope_path[:first_slash_idx] + scope_path[first_slash_idx+1:]
        # END OF WORKAROUND ------------------------------------

        xml_subsystem = { 'path' : scope_path }
        xml_subsystem['signals'] = []
        for signal_info in signal_infos:
            kind = _get_signal_kind(signal_info)
            if kind not in ['OUTPUT', 'LOCAL']: continue
            # check if a defined regular expression matches the current signal name
            tolerances = None
            if tol_regex: # list of signal-name-based tolerance definitions
                for tolerance_definition in tol_regex:
                    if re.match(tolerance_definition['regex'], signal_info['name']):
                        tolerances = tolerance_definition
                        break
            # if not, apply default tolerances
            if not tolerances:
                if tol_flp and _is_float(signal_info):
                    tolerances = tol_flp.copy()
                elif tol_fxp and _is_fxp(signal_info):
                    tolerances = tol_fxp.copy()
                else:
                    continue
            # "undefined tolerance" defaults to "zero tolerance"
            if not 'abs' in tolerances: tolerances['abs'] = 0
            if not 'rel' in tolerances: tolerances['rel'] = 0
            _convert_lsb_based_tolerances(tolerances, signal_info['resolution'])
            xml_signal = { 
                'kind' : 'PORT' if kind == 'OUTPUT' else 'DISPLAY',
                'name' : signal_info['name'],
                'dataType' : signal_info['dataType'],
                'lsb' : signal_info['resolution'],
                'offset' : signal_info['offset'],
                'absTolerance' : tolerances['abs'],
                'relTolerance' : tolerances['rel']
            }
            xml_subsystem['signals'].append(xml_signal)
        
        # add scope to list if there's at least 1 signal
        if xml_subsystem['signals']: xml_subsystems.append(xml_subsystem)

    return xml_subsystems

def _generate_tolerance_xml(subsystems, tolerance_xml_file='tolerances.xml'):
    # templates for substitution
    xml_template = """<?xml version="1.0" encoding="UTF-8"?>
<ToleranceSettings version="1.1">
{subsystem_nodes}
</ToleranceSettings>"""

    subsystem_node_template = """  <Subsystem relPath="{rel_path}">
{output_nodes}
  </Subsystem>"""

    output_node_template = """    <Output uniqueName="{unique_name}">
      <Tolerance absValue="{abs_value}" relValue="{rel_value}" leadSteps="0" lagSteps="0" checked="true"/>
      <Info kind="{kind}" dataType="{data_type}" lsb="{lsb}" offset="{offset}"/>
    </Output>"""

    # collect data and apply to templates
    subsystem_nodes = []
    for subsystem in subsystems:
        output_nodes = []
        for signal in subsystem['signals']:
            # <Output>
            output_node = output_node_template.format(
                unique_name=signal['name'].replace("<", "&lt;").replace(">", "&gt;"),
                abs_value=signal['absTolerance'],
                rel_value=signal['relTolerance'],
                kind=signal['kind'],
                data_type=signal['dataType'],
                lsb=signal['lsb'],
                offset=signal['offset']
            )
            output_nodes.append(output_node)

        # <Subsystem>
        subsystem_node = subsystem_node_template.format(
            rel_path=subsystem['path'],
            output_nodes='\n'.join(output_nodes)
        )
        subsystem_nodes.append(subsystem_node)

    # <ToleranceSettings>
    xml_content = xml_template.format(subsystem_nodes='\n'.join(subsystem_nodes))
    with open(tolerance_xml_file, 'w') as file: file.write(xml_content)

    return os.path.abspath(tolerance_xml_file)

def _apply_tolerances_to_profile(ep, tolerance_xml_file, use_case):
    tol_import = {
        'path' : tolerance_xml_file,
        'toleranceUseCase' : use_case
    }
    ep.put('profiles/global-tolerances', tol_import)
    # delete the xml file that we produced
    os.remove(tolerance_xml_file)

def _is_float(signal_info):
    return signal_info['dataType'].lower() in KNOWN_FLOAT_TYPES

def _is_fxp(signal_info):
    if _is_float(signal_info):
        return False
    else:
        lsb = _get_converted_lsb(signal_info['resolution'])
        return Decimal(lsb).compare(Decimal(1)) == -1

def _get_converted_lsb(lsb_string):
    if '^' in lsb_string:
        lsb_base, lsb_exp = lsb_string.split('^')
        lsb_value = Decimal(lsb_base) ** Decimal(lsb_exp)
    else:
        lsb_value = Decimal(lsb_string)
    return lsb_value


def _get_signal_kind(signal):
    return signal['identifier'].split(':')[0]

def _convert_lsb_based_tolerances(tolerances, resolution):
    """Extracts the lsb-factor and multiplies it with the resolution."""
    lsb_value = _get_converted_lsb(resolution)
    abs_str = str(tolerances['abs']).upper()
    if '*LSB' in abs_str:
        atr_index = abs_str.index('*')
        factor = abs_str[0:atr_index]
        tolerances['abs'] = str(Decimal(factor) * lsb_value)
    rel_str = str(tolerances['rel']).upper()
    if '*LSB' in rel_str:
        atr_index = rel_str.index('*')
        factor = rel_str[0:atr_index]
        tolerances['rel'] = str(Decimal(factor) * lsb_value)


def get_processes_by_name(name):
    ps_script = f"""
    Get-Process -Name "{name}" -ErrorAction SilentlyContinue |
    Where-Object {{ $_.Path }} |
    Select-Object Name, Path |
    ConvertTo-Json
    """
    result = subprocess.run(
        ['powershell', '-Command', ps_script],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True
    )
    try:
        data = json.loads(result.stdout)
        return [(p["Name"], p["Path"]) for p in (data if isinstance(data, list) else [data])]
    except json.JSONDecodeError:
        return []

def is_port_in_use(port: int, host) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((host, port)) == 0 #can raise an exception in case of bad host name

