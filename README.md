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
Waiting for BTC EmbeddedPlatform 24.1p0 to be available:
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
    - https://github.com/btc-embedded/btc_embedded/blob/main/btc_embedded/resources/btc_config.yml
    - https://github.com/btc-embedded/btc-ci-workflow/blob/main/btc_config.yml
- Some report templates are also added and can be used when creating a project report

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
