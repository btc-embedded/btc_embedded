# BTC EmbeddedPlatform REST API Package for Python

With this API wrapper you can automate your test workflows for embedded software on models and code using BTC EmbeddedPlatform via Python.

### Installing the package:
```sh
$ pip install btc_embedded
```

### Using the API wrapper
```python
from btc_embedded.api import EPRestApi

# create api object and connects to the default port (1337)
ep = EPRestApi()

# create an empty test project
ep.post('profiles')
```
Further details and examples can be found in our [example repository](https://github.com/btc-embedded/btc-ci-workflow).
