import fnmatch
import os
from importlib import resources

import yaml


def get_global_config():
    config, _ = __get_global_config()
    return config

def __get_global_config():
    """Returns the global config from the parent dir of the
    file 'btc_config.py' with the project-specific config."""
    with resources.path("btc_embedded", "btc_config.yml") as global_config_file:
        config = __load_config(str(global_config_file))
        return config, global_config_file

def get_project_specific_config(project_directory=os.getcwd(), project_config=None):
    """Returns the project-specific config, which is the first file
    called 'btc_project_config.yml' that is found when recursively searching
    the specified project directory. If no project directory is specified,
    the current working directory is used."""
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
        print(f"Applying global config from {path}")

    # get the project specific config
    project_specific_config, path = get_project_specific_config(project_directory, project_config)
    if project_specific_config and not silent:
        print(f"Applying project-specific config from {path}")

    # merge them and return the merged config
    config.update(project_specific_config)
    return config


def get_vector_gen_config(scope_uid, config=None):
    """Returns the vector generation payload object for the specified uid and config object.
    If no config object is specified, the global config is used.
    - All relevant properties of the config are applied.
    - Anything not specified in the config is left empty (the API uses default value in those cases)"""
    vector_generation_config = { 'scopeUid' : scope_uid }
    if not config:
        config = get_global_config()
    # engine settings
    engine_settings = {}
    if 'globalTimeout' in config: engine_settings['timeoutSeconds'] = config['globalTimeout']
    if 'threshold' in config: engine_settings['handlingRateThreshold'] = config['threshold']
    
    if 'engines' in config and 'CV' in config['engines']:
        # prepare cv engine
        cv_settings = { 'name' : 'CV' }
        if 'cvTimeoutSeconds' in config: cv_settings['timeoutSecondsPerSubsystem'] = config['cvTimeoutSeconds']
        if 'cvPropertyTimeoutSeconds' in config: cv_settings['timeoutSecondsPerProperty'] = config['cvPropertyTimeoutSeconds']
        if 'cvSearchDepth' in config: cv_settings['searchDepthSteps'] = config['cvSearchDepth']
        if 'loopUnrollLimit' in config: cv_settings['loopUnroll'] = config['loopUnrollLimit']
        if 'maximumNumberOfThreads' in config: cv_settings['maximumNumberOfThreads'] = config['maximumNumberOfThreads']
        if 'parallelExecutionMode' in config: cv_settings['parallelExecutionMode'] = config['parallelExecutionMode']
        if 'modelCheckers' in config:
            cv_settings['coreEngines'] = []
            [cv_settings['coreEngines'].append({ 'name' : model_checker }) for model_checker in config['modelCheckers']]
        # add cv engine to engine settings
        engine_settings['engineCv'] = cv_settings

    if 'engines' in config and 'ATG' in config['engines']:
        # prepare cv engine
        atg_settings = { 'name' : 'ATG' }
        if 'atgTimeoutSeconds' in config: atg_settings['timeoutSecondsPerSubsystem'] = config['atgTimeoutSeconds']
        # add cv engine to engine settings
        engine_settings['engineAtg'] = atg_settings

    vector_generation_config['engineSettings'] = engine_settings
    # pll
    if 'pllString' in config: vector_generation_config['pllString'] = config['pllString']
    return vector_generation_config

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
