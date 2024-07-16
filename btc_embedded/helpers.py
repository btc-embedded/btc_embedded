import os
import re
import shutil
from decimal import Decimal
from importlib import resources

import yaml

from btc_embedded.config import (BTC_CONFIG_DEFAULTLOCATION,
                                 BTC_CONFIG_ENVVAR_NAME)

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
                value_data, _ = winreg.QueryValueEx(ep_key, "EPACTIVE")
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
            config_file_template = os.path.join(resources.files('btc_embedded'), 'resources', 'btc_config.yml')
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
            
            print(f"Applied initial btc_config template to '{global_config}'.")
            print(f"""Please verify the initial configuration:
    - BTC EmbeddedPlatform {ep_version} (installed at: '{install_location}')
    - {highest_ml_version}
    - Compiler: {config['preferences']['GENERAL_COMPILER_SETTING']}
""")
            return config

def install_report_templates(template_folder):
    try:
        def xml_filter(_, names): return [name for name in names if not name.endswith('.xml')]
        os.makedirs(template_folder, exist_ok=True)
        resources_folder = os.path.join(resources.files('btc_embedded'), 'resources', 'projectreport_templates')
        shutil.copytree(resources_folder, template_folder, ignore=xml_filter, dirs_exist_ok=True)
        print(f"Installed project report templates to '{template_folder}'")
    except:
        print(f"[WARNING] Could not install report templates to '{template_folder}'")

def set_tolerances(ep, tol_fxp={ 'abs': '1*LSB' }, tol_flp={ 'abs': 1E-16, 'rel': 1E-8 }, use_case='B2B', signal_name_based_tolerances=None):
    """Sets the tolerances for float (tol_flp) and fixed-point (tol_fxp) outputs (integers with an LSB < 1 are considered fxp) \n
    - use_case can be 'RBT' or 'B2B' (default)

    Default values:
    - tol_flp = { 'abs': 1E-16, 'rel': 1E-8 }
    - tol_fxp = { 'abs': '1*LSB' }   (1*LSB is converted based on each signals LSB)

    Other examples:
    - tol_fxp = { 'abs': 0.0001, 'rel': 0.001 }
    - tol_flp = { 'rel': 0.004 }
    - tol_flp = None   (no tolerance for floats)
    """
    subsystems_and_signal_data = _collect_scope_signal_data(ep, tol_fxp, tol_flp, signal_name_based_tolerances=signal_name_based_tolerances)
    if subsystems_and_signal_data:
        tolerance_xml_file = _generate_tolerance_xml(subsystems_and_signal_data)
        _apply_tolerances_to_profile(ep, tolerance_xml_file, use_case)

def apply_tolerances_from_config(ep):
    config = ep.config
    if config and 'default_tolerances' in config and ep._does_api_support_signalinfo():
        if 'B2B' in config['default_tolerances']:
            b2b_tolerances_flp = None
            b2b_tolerances_fxp = None
            if 'floating-point' in config['default_tolerances']['B2B']:
                b2b_tolerances_flp = config['default_tolerances']['B2B']['floating-point']
            if 'fixed-point' in config['default_tolerances']['B2B']:
                b2b_tolerances_fxp = config['default_tolerances']['B2B']['fixed-point']
            set_tolerances(ep, tol_flp=b2b_tolerances_flp, tol_fxp=b2b_tolerances_fxp, use_case='B2B')
        if 'RBT' in config['default_tolerances']:
            rbt_tolerances_flp = None
            rbt_tolerances_fxp = None
            if 'floating-point' in config['default_tolerances']['RBT']:
                rbt_tolerances_flp = config['default_tolerances']['RBT']['floating-point']
            if 'fixed-point' in config['default_tolerances']['RBT']:
                rbt_tolerances_fxp = config['default_tolerances']['RBT']['fixed-point']
            set_tolerances(ep, tol_flp=rbt_tolerances_flp, tol_fxp=rbt_tolerances_fxp, use_case='RBT')
        tolerance_definition_found = True
    else:
        tolerance_definition_found = False
    return tolerance_definition_found

def _collect_scope_signal_data(ep, tol_fxp, tol_flp, signal_name_based_tolerances):
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
        # first_slash_idx = scope_path.find('/')
        # if not first_slash_idx == -1: scope_path = scope_path[:first_slash_idx] + scope_path[first_slash_idx+1:]
        # END OF WORKAROUND ------------------------------------

        xml_subsystem = { 'path' : scope_path }
        xml_subsystem['signals'] = []
        for signal_info in signal_infos:
            kind = _get_signal_kind(signal_info)
            if kind not in ['OUTPUT', 'LOCAL']: continue
            tolerances = None
            if signal_name_based_tolerances:
                for tol_definition in signal_name_based_tolerances:
                    regex = tol_definition['regex']
                    if re.match(regex, signal_info['name']):
                        tolerances = tol_definition
                
            if not tolerances:
                if tol_flp and _is_float(signal_info):
                    tolerances = tol_flp.copy()
                elif tol_fxp and _is_fxp(signal_info):
                    tolerances = tol_fxp.copy()
                else:
                    continue
            # undefined tolerance defaults to zero tolerance
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

def _generate_tolerance_xml(subsystems, tolerance_xml_file='default_tolerances.xml'):
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
                unique_name=signal['name'],
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

def _convert_lsb_based_tolerances(global_tolerances, resolution):
    """Extracts the lsb-factor and multiplies it with the resolution."""
    lsb_value = _get_converted_lsb(resolution)
    abs_str = str(global_tolerances['abs']).upper()
    if '*LSB' in abs_str:
        atr_index = abs_str.index('*')
        factor = abs_str[0:atr_index]
        global_tolerances['abs'] = str(Decimal(factor) * lsb_value)
    rel_str = str(global_tolerances['rel']).upper()
    if '*LSB' in rel_str:
        atr_index = rel_str.index('*')
        factor = rel_str[0:atr_index]
        global_tolerances['rel'] = str(Decimal(factor) * lsb_value)