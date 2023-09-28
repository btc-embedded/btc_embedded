## BTC EmbeddedPlatform API files

This folder contains files used by the workflow scripts. A **pip install -r requirements.txt** on the toplevel of the repository installs them as a local package.

### Relevant python scripts:
- [api.py](api.py): the main API layer to interact with the BTC EmbeddedPlatform REST API
- [config.py](config.py): manages global and local (project-specific) configurations in test workflows
- [reporting.py](reporting.py): provides a method **create_test_report_summary** to create a report with a status summary of multiple test projects.
- [util.py](util.py): utility functions to print coverage and test results to the console

### Other relevant files
- [btc_config.yml](btc_config.yml): global configuration file that defines default values for different things relevant to BTC EmbeddedPlatform test workflows. Used by the [config.py](config.py) module.
- [btc_summary_report.template](btc_summary_report.template): Raw text file with HTML, Javascript, CSS and placeholders. Serves as a template for summary reports.
