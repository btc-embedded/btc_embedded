import os
import re
import shutil
from importlib import resources

import yaml

from btc_embedded.config import (BTC_CONFIG_DEFAULTLOCATION,
                                 BTC_CONFIG_ENVVAR_NAME)

VERSION_PATTERN_2 = r'(\d+\.\d+[a-zA-Z]\d+)' # e.g.   "24.3p1"

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
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\BTC")
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

