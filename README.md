# BTC EmbeddedPlatform REST API Package for Python

With this API wrapper you can automate your test workflows for embedded software on models and code using BTC EmbeddedPlatform via Python.

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

## Using the API wrapper
```python
from btc_embedded.api import EPRestApi

# create api object and connects to the default port (1337)
ep = EPRestApi()

# create an empty test project
ep.post('profiles')
```
Further details and examples can be found in our [example repository](https://github.com/btc-embedded/btc-ci-workflow).
