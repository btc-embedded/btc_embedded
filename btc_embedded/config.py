import fnmatch
import logging
import os
import platform
from importlib import resources

import yaml

logger = logging.getLogger('btc_embedded')

BTC_CONFIG_ENVVAR_NAME = 'BTC_API_CONFIG_FILE'
BTC_CONFIG_DEFAULTLOCATION = 'C:/ProgramData/BTC/ep/btc_config.yml'

def get_global_config():
    config, _ = __get_global_config()
    return config

def __get_global_config():
    """Returns the global config from the parent dir of the
    file 'btc_config.py' with the default configuration"""
    # Option A: set via environment variable
    if BTC_CONFIG_ENVVAR_NAME in os.environ and os.path.isfile(os.environ[BTC_CONFIG_ENVVAR_NAME]):
        global_config_file_path = os.environ[BTC_CONFIG_ENVVAR_NAME]
    # Option B: use btc_config from default location
    elif platform.system() == 'Windows' and os.path.isfile(BTC_CONFIG_DEFAULTLOCATION):
        global_config_file_path = BTC_CONFIG_DEFAULTLOCATION
    # Option C: use defaults shipped with this module
    else:
        global_config_file_path = get_config_path_from_resources()
    # load config
    config = __load_config(global_config_file_path)
    logger.debug(f"Applying global config from '{global_config_file_path}'")
    return config, global_config_file_path

def get_project_specific_config(project_directory=os.getcwd(), project_config=None):
    """Returns the project-specific config, which is the first file
    called 'btc_project_config.yml' that is found when recursively searching
    the specified project directory. If no project directory is specified,
    the current working directory is used."""
    if isinstance(project_config, dict): return project_config, None
    project_specific_config = {}
    path = None
    if project_config: return __load_config(project_config), project_config
    for root, _, files in os.walk(project_directory):
        for name in files:
            if fnmatch.fnmatch(name, 'btc_project_config.yml'):
                path = root + '/' + name
                project_specific_config = __load_config(path)
                break
    return project_specific_config, path

def get_merged_config(project_directory=os.getcwd(), silent=False, project_config=None):
    """Returns a merged config that combines the global config from the
    parent dir of the file 'btc_config.py' with a project-specific config.
    - The project-specific config is the first file called 'btc_project_config.yml'
    that is found when recursively searching the specified project directory.
    If no project directory is specified, the current working directory is
    used.
    - The configs are merged by giving precedence to any project-specific
    settings."""
    # get the global config
    config, path = __get_global_config()
    if config and not silent:
        logger.debug(f"Applying global config from {path}")

    # get the project specific config
    project_specific_config, path = get_project_specific_config(project_directory, project_config)
    if project_specific_config and not silent and path:
        logger.debug(f"Applying project-specific config from {path}")
    elif project_specific_config and not silent:
        logger.debug(f"Applying project-specific config")
    # merge them and return the merged config
    def recursive_update(d, u):
        for k, v in u.items():
            if isinstance(v, dict) and k in d:
                recursive_update(d[k], v)
            else:
                d[k] = v
    recursive_update(config, project_specific_config)
    return config

def get_vector_gen_config(scope_uid, config=None):
    """@DEPRICATED
    Vector generation settings can be specified using the respective preferences.
    Consult the BTC EmbeddedPlatform Preference Configuration Guide.pdf in the
    documentation folder of the BTC EmbeddedPlatform installation for a comprehensive
    list and description of available preferences and their effects.
    """
    return { 'scopeUid' : scope_uid }

def get_config_path_from_resources():
    if platform.system() == 'Windows':
        return get_resource_path('btc_config_windows.yml')
    else:
        return get_resource_path('btc_config_linux.yml')

def __load_config(config_file):
    """Attemps to load a config from the specified yaml file.
    - When successful, this returns the populated config object that was parsed from the file.
    - If anything goes wrong, an empty config object is returned."""
    config = {}
    try:
        if config_file:
            with open(config_file, 'r') as f:
                config = yaml.safe_load(f) or {}
    except:
        pass
    return config

def get_resource_path(filename):
    try:
        # main approach
        return str(os.path.join(resources.files('btc_embedded'), 'resources', filename))
    except:
        # fallback for Python 3.8 and older
        with resources.path('btc_embedded', 'resources') as resource_dir:
            return os.path.join(resource_dir, filename)
