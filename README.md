# BTC EmbeddedPlatform REST API Package for Python

With this API wrapper you can automate your test workflows for embedded software on models and code using BTC EmbeddedPlatform via Python.

## Using the API wrapper
```python
from btc_embedded.api import EPRestApi

# create api object and connects to the default port (1337)
ep = EPRestApi()

# create an empty test project
ep.post('profiles')
```
Further details and examples can be found in our [example repository](https://github.com/btc-embedded/btc-ci-workflow).


## Installing the package
```sh
$ pip install btc_embedded
```
What can I do if my machine doesn't allow pip access to the internet?
- Check with colleagues / the IT team if your company hosts a mirror of the public repository in your local network and use that instead.
- Plan B:
    - download / clone the module's public repository: https://github.com/btc-embedded/btc_embedded
    - open a terminal and navigate into the btc_embedded directory
    - call **pip install .** (including the dot)


## Prerequisites on the runner
- BTC EmbeddedPlatform must be installed incl. the REST Server Addon (unless you use the container image)
- The Matlab versions you intend to use must be integrated with BTC EmbeddedPlatform (can be selected during installation)
- A license server must be configured a value such as 27000@myserver.myorg in one of the following ways:
    - As the value of the property **licenseLocation** in the global or project-specific btc_config.yml
    - As the value of the constructor argument **license_location** when creating the EPRestApi() object in Python
    - As the value of the registry key called **OSCCSD_LICENSE_FILE** in "HKEY_CURRENT_USER/SOFTWARE/FLEXlm License Manager" (automatically set when using the license dialog of the GUI)
