# BTC EmbeddedPlatform REST API Package for Python
The BTC REST API wrapper for Python is designed to facilitate the automation of test workflows using the BTC EmbeddedPlatform REST API

- handle startup of the headless BTC EmbeddedPlatform application on windows and linux (docker)
- separation of concerns: configuration ←→ workflow steps
- error handling (showing relevant messages on error, etc.)
- uniform responses: api wrapper calls such as "ep.get(...)", "ep.post(...)", etc.) will always return one of the following: an object, a list of objects or nothing

## Getting Started
The python module btc_embedded lets you start & stop a headless BTC EmbeddedPlatform and allows you to define your test workflows for automation and CI purposes.

- Installing the module works like for any other python module: pip install btc_embedded (You can always use the latest version of this module, as it's designed to remain compatible with older versions of BTC EmbeddedPlatform)
- Importing it in your Python script: **from btc_embedded import EPRestApi**
- Creating the API object: **ep = EPRestApi()**

When creating the API object without further parameters, the module looks for an instance of BTC EmbeddedPlatform on http://localhost:1337. If it doesn't find a running instance, it will start one and return once it connected to it. The console output will look roughly like this:

```Applying global config from 'C:\ProgramData\BTC\ep\btc_config.yml'
Waiting for BTC EmbeddedPlatform 24.2p0 to be available:
Connecting to BTC EmbeddedPlatform REST API at http://localhost:1337
....
BTC EmbeddedPlatform has started.
Applied preferences from the config
```

Once the console indicates that "BTC EmbeddedPlatform has started", you can access the api documentation by opening http://localhost:1337 in your browser. If you'd like to check the docs without running BTC EmbeddedPlatform, you can use the static PDF docs that are part of the public btc-ci-workflow GitHub repository. 


## Configuration
You'd like to use a specific BTC version or specify preferences such as the Matlab version to be used, settings for vector generation, etc.? Although you can do this directly in your script, we recommend to keep this sort of configuration separate from the actual test workflow. For this purpose you can use a YAML-based configuration file (btc_config.yml):
Windows

- If the environment variable **BTC_API_CONFIG_FILE** is set and points to a config file, it is being considered and any preferences defined inside are applied automatically when the API object is created
- Otherwise, the API wrapper will add a config file “C:/ProgramData/BTC/ep/config.yml” with some reasonable defaults (e.g., the EP install directory, the latest compatible Matlab version, etc.)
- Examples of the config file can be found here:
    - https://github.com/btc-embedded/btc_embedded/blob/main/btc_embedded/resources/btc_config_windows.yml
    - https://github.com/btc-embedded/btc-ci-workflow/blob/main/btc_config.yml
- Some report templates are also added and can be used when creating a project report

## Tolerances
Tolerances for requirements-based testing (RBT) and back-to-back testing (B2B) can be specified as part of the btc_config.yml file for BTC EmbeddedPlatform versions 24.1 and higher (see comments in [btc_config.yml](https://github.com/btc-embedded/btc_embedded/blob/main/btc_embedded/resources/btc_config_windows.yml) for more details).
When configured in the config, they will automatically be applied to the test project(supported with EP 24.1 and beyond).

For each scope, for each DISP/OUT the signal is checked:
1. Does the signal name match any of the "signal-name-based" tolerance definitions?
    - first matching tolerance definition is applied (based on regex <-> signal-name)
    - If no signal-name based tolerance was defined, default tolerances based on data type are considered:
2. Does the signal use a floating point data type? [ 'double', 'single', 'float', 'float32', 'float64', 'real' ]
    - apply default tolerances for floats (if defined)
3. Does the signal use a fixed-point data type? (integer with LSB < 1)
    - apply default tolerances for fixed-point (if defined)
    - tolerance can also be defined as a multiple of the LSB (e.g. 1*LSB)

**abs**: absolute tolerance - a deviation <= **abs** will be accepted as PASSED

**rel**: relative tolerance - accepted deviation <= (reference value * **rel**) will be accepted as PASSED
     useful for floats to compensate for low precision on high float values

```yaml
tolerances:
  B2B: 
    # specific tolerances for matching signals
    signal-name-based:
      - regex: .*_write.*
        rel: 2e-1
      - regex: .*dsout_.*
        abs: 4e-6
        rel: 4e-4

    # default tolerances for anything else
    floating-point:
      abs: 0.001
      rel: 0.01
    fixed-point:
      abs: 1*LSB
```

## Docker/Linux
- the config & the env variable are part of the build
- the report-templates should also be part of the image
- the tests for the btc_embedded module also run on Docker, check out the repo if you're interested: https://github.com/btc-embedded/btc_embedded/blob/main/test/Dockerfile

## Licensing & Prerequisites (on Windows)
- BTC EmbeddedPlatform must be installed incl. the REST Server Addon
- The Matlab versions you intend to use must be integrated with BTC EmbeddedPlatform (can be selected during installation)
- A license server must be configured a value such as 27000@myserver.myorg in one of the following ways:
- As the value of the property licenseLocation in the global or project-specific btc_config.yml
- As the value of the constructor argument license_location when creating the EPRestApi() object in Python
- As the value of the registry key called OSCCSD_LICENSE_FILE in "HKEY_CURRENT_USER/SOFTWARE/FLEXlm License Manager" (automatically set when using the license dialog of the GUI)

## Reporting

### Project Report & Templates
- When creating the project report the user can add the name of a report template by appending '?template-name=rbt-ec' to the API call
- This expects a report template xml file to be present in the report templates directory which is indicated by the preference REPORT_TEMPLATE_FOLDER (part of the btc_config.yml)
- If the user didn’t configure it differently, some default templates are automatically placed into “C:/ProgramData/BTC/ep/report-templates”
    - rbt-b2b-ec.xml
    - rbt-b2b-tl.xml
    - rbt-ec.xml
    - rbt-sil-only.xml
    - rbt-tl.xml
    - b2b-only-ec.xml
    - b2b-only-tl.xml
    - regression-test-ec.xml
    - regression-test-sil-only.xml
    - regression-test-tl.xml
- Users can create report templates according to their own needs via the GUI, save them in the report template folder and refer to them by name when creating a project report.


## BTC Summary Report

- When testing multiple projects in batch it’s helpful to have a summary report that lists all project, their overall status and allows to drill down into the respective project reports.
- Two things are needed to achieve this:
1. For each individual project (e.g., a workflow that works on one model/epp), a result object must be created (see https://github.com/btc-embedded/btc-ci-workflow/blob/main/examples/btc_test_workflow.py#L58).
2. The result objects for each project needs to be added to a list and this list will then be passed used for creating the report (see https://github.com/btc-embedded/btc-ci-workflow/blob/main/examples/test_multiple_projects.py)

## Logging 
This module uses a logger named 'btc_embedded' which you can access by its name.

### Configure custom logging
```python
import logging

# Access btc_embedded logger
logger = logging.getLogger('btc_embedded')

# Collect logging output in a file
log_file = os.path.join(os.path.dirname(__file__), 'btc_embedded.log')
file_handler = logging.FileHandler(log_file)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
logger.addHandler(file_handler)
```
### Configure log level
Chosing a log level lower than the one configured for the logger will have no effect. By default, the module will log using the INFO level. You can adapt this when creating the API object:
```python
# Create BTC API object with a customized log level
ep = EPRestApi(log_level=logging.DEBUG)
```
### Disable logging
If you wish to disable logging entirely, simply set the log level to LOGGING_DISABLED:
```python
from btc_embedded import EPRestApi, LOGGING_DISABLED

# disable logging
ep = EPRestApi(log_level=LOGGING_DISABLED)
```
