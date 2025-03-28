# Using BTC EmbeddedPlatform with Docker
![BTC EmbeddedPlatform Logo](https://github.com/btc-embedded/btc_embedded/blob/main/public/btc-logo.png?raw=true)

BTC EmbeddedPlatform docker image for ISO 26262 certified test of safety critical Simulink models and C code.

# What is BTC EmbeddedPlatform?

BTC EmbeddedPlatform is an ISO 26262-qualified test solution for Simulink models and production code. For further information, check out the product summary on our website: https://www.btc-embedded.com/btc-embeddedplatform/.

This docker image enables you to easily package your toolchain for CI. Whether you have a lean handcode development process or a sophisticated model-based development toolchain, using Docker you can easily control the tool versions and roll out an immutable toolchain that delivers reproducible results.
<br><br>

# Table of Contents
1. [What is BTC EmbeddedPlatform?](#what-is-btc-embeddedplatform)
2. [Supported versions](#supported-versions)
3. [Access the OpenAPI docs](#access-the-openapi-docs)
4. [Testing C-Code](#testing-c-code)
    - [Create the image](#create-the-image)
    - [Run the tests](#run-the-tests)
5. [Testing MATLAB Simulink Models](#testing-matlab-simulink-models)
    - [Create the image](#create-the-image-1)
    - [Run the tests](#run-the-tests-1)
6. [Technical support](#technical-support)

# Supported versions
| Tag               | Supported MATLAB versions | Supported TargetLink versions |
|-------------------|---------------------------|-------------------------------|
| `latest` `24.3p0` | R2022b - R2024b           | TL 5.2 - TL 23.1              |
| `24.2p0`          | R2022b - R2024a           | TL 5.2 - TL 23.1              |
| `24.1p0`          | R2022b - R2023b           | TL 5.2 - TL 23.1              |
| `23.3p0`          | R2022b - R2023b           | TL 5.2 - TL 23.1              |
| `23.2p0`          | R2022b - R2023a           | TL 5.2 - TL 22.1              |
| `23.1p0`          | R2022b                    | TL 5.2 - TL 22.1              |

For more information on working with MATLAB and TargetLink check out the section "Testing MATLAB Simulink Models" below.
<br><br>

# Access the OpenAPI docs

The recommended approach to automate test workflows with BTC EmbeddedPlatform is to use the `btc_embedded` python module. The module provides a simple interface to the REST API of BTC EmbeddedPlatform. The REST API is documented using OpenAPI.

Running the command below will start the BTC EmbeddedPlatform image and make the REST API available on port 8080. You can then access the API documentation by opening http://localhost:8080 in your browser:

```bash
docker run -p 8080:8080 -e LICENSE_LOCATION=27000@MyLicenseServer btces/ep
```

![BTC api docs](https://github.com/btc-embedded/btc_embedded/blob/main/public/rest-api-docs.png?raw=true)

<br><br>

# Testing C-Code

(For more information on the general use case check out our the summary on our website: https://www.btc-embedded.com/test_environments/c-code/)

The BTC EmbeddedPlatform container image already comes with the gcc compiler and is ready to be used out of the box. For automating the tests from python we recommend to add the btc_embedded python module using pip, as shown in the Dockerfile example below:

## Create the image

```Dockerfile
FROM btces/ep

# add the btc_embedded module for python
USER root
RUN apt-get update -y && apt-get install -y python3 python3-pip && pip3 install btc_embedded
# default value for license server (can be overwritten on docker run)
ENV LICENSE_LOCATION=27000@MyLicenseServer
USER ep

CMD []
```

You can now build your image like this (assuming you’re in the same directory as the Dockerfile):
```bash
docker build -t btc-embedded .
```
This creates an image called `btc-embedded` based on the Dockerfile above. We'll use this image to run the tests in the next step.

## Run the tests

Let’s assume you’ve checked out the git repository with your code in the current directory and it has a structure like this:
```
.
├── incl
│   └── my-code.h
├── src
│   └── my-code.c
└── test
    ├── my-code.epp
    └── run_tests.py
```

You can now run the tests like this:
```bash
docker run -v "$(pwd):$(pwd)" btc-embedded python3 "test/run_tests.py"
```
- the `-v "$(pwd):$(pwd)"` option mounts the current directory into the container so that the test script can access the code and the test profile.
- the `python3 "test/run_tests.py"` command runs the test script in the container.
<br><br>

For more detailed examples of automating BTC test steps in Python, please check out our examples on GitHub https://github.com/btc-embedded/btc-ci-workflow/blob/main/examples/test_workflow_c.py.

A simple version of the `run_tests.py` script could look like the snippet below:

```python
import os
from btc_embedded import EPRestApi

# connect to BTC EmbeddedPlatform REST API
ep = EPRestApi() # by default this connects to http://localhost:1337

# load a profile & update code
epp_file = os.path.abspath("test/profile.epp")
ep.get(f'profiles/{epp_file}')
ep.put('architectures?performUpdateCheck=true')

# run functional tests on the code
scopes = ep.get('scopes')
ep.post('scopes/test-execution-rbt', {
    'UIDs': [scope['uid'] for scope in scopes],
    'data' : {
        'execConfigNames' : [ 'SIL' ]
    }
})

# Create and export test report and export to a file called 'report.html'
report = ep.post(f"scopes/{scopes[0]['uid']}/project-report?template-name=rbt-sil-only")
ep.post(f"reports/{report['uid']}", { 'exportPath': os.path.dirname(epp_file) })

# Save *.epp
ep.put('profiles', { 'path': epp_file })
```
<br>

# Testing MATLAB Simulink Models
When testing Simulink models (optionally with auto-code generation with TargetLink (dSPACE) or EmbeddedCoder (The MathWorks)) the most common concept is to create a container that packages all required tools using the following steps:
1. Start with `mathworks/matlab` as the base image
2. Add required toolboxes
3. Add dSPACE TargetLink and integrate it with MATLAB (only required if TargetLink is used)
4. Add BTC EmbeddedPlatform (incl. `btc_embedded` python module) and integrate it with MATLAB

## Create the image
For details on how to add TargetLink to the container, please refer to dSPACE. Let's have a look at an example for a Simulink model using EmbeddedCoder as the code generator (description below):

```Dockerfile
# Configure versions
ARG MATLAB_RELEASE=R2024b
ARG BTC_RELEASE=24.3p0
ARG GCC_VERSION=11

# Starting from public image mathworks/matlab and btces/ep
FROM btces/ep:${BTC_RELEASE} AS ep
FROM mathworks/matlab:${MATLAB_RELEASE} AS matlab

# ml toolboxes and licenses
ARG MATLAB_LICENSE_SERVER=27000@matlab.license.server
ARG BTC_LICENSE_SERVER=27000@MyLicenseServer
ARG MATLAB_PRODUCTS="Embedded_Coder AUTOSAR_Blockset MATLAB_Coder Simulink Simulink_Coder Simulink_Coverage Stateflow"
ARG MATLAB_RELEASE
ARG GCC_VERSION
ENV MLM_LICENSE_FILE=$MATLAB_LICENSE_SERVER
ENV LICENSE_LOCATION=${BTC_LICENSE_SERVER}

# -------------------------------
# MATLAB-specific configurations:
# -> Install required matlab products/toolboxes
# -------------------------------
USER root
RUN apt update && apt-get install -y wget
RUN wget -q https://www.mathworks.com/mpm/glnxa64/mpm && chmod +x mpm \
    && ./mpm install \
    --release=${MATLAB_RELEASE}  \
    --destination=/opt/matlab  \
    --products ${MATLAB_PRODUCTS} \
    && rm -f mpm /tmp/mathworks_root.log \
    && ln -f -s /opt/matlab/bin/matlab /usr/local/bin/matlab
RUN rm -f /home/matlab/Documents/MATLAB/startup.m

# -------------------------------
# COMPILER-specific configurations (gcc)
# -------------------------------
RUN export DEBIAN_FRONTEND=noninteractive && apt-get install -y gcc-$GCC_VERSION && update-alternatives --install /usr/bin/gcc gcc /usr/bin/gcc-$GCC_VERSION 100 && update-alternatives --config gcc && apt-get install -y g++-$GCC_VERSION && update-alternatives --install /usr/bin/g++ g++ /usr/bin/g++-$GCC_VERSION 100 && update-alternatives --config g++ && apt-get install -y cpp-$GCC_VERSION && update-alternatives --install /usr/bin/cpp cpp /usr/bin/cpp-$GCC_VERSION 100 && update-alternatives --config cpp

# ----------------------------------------------------------------------------------------
# BTC-specific configurations:
# -> Copy files from btces/ep, integrate BTC with MATLAB and add btc_embedded python module
# ----------------------------------------------------------------------------------------
COPY --chown=1000 --from=ep /opt /opt
COPY --chown=1000 --from=ep /root/.BTC /root/.BTC
RUN sudo chmod +x /opt/ep/addMLIntegration.bash && sudo /opt/ep/addMLIntegration.bash
RUN apt-get install -y python3 python3-pip && pip3 install --no-cache-dir btc_embedded
ENV PYTHONUNBUFFERED=1

# Reset user and override default entrypoint
USER matlab
ENTRYPOINT [ ]
CMD [ ]
```

Here's a short summary of what the Dockerfile does:
- **General:** define ARGs to:
    - specify the desired MATLAB, BTC EmbeddedPlatform and gcc versions
    - configure the required license servers
    - specify the desired MATLAB toolboxes
- **MATLAB installation:**
    - use wget to download the MATLAB package manager (mpm)
    - use mpm to install the required MATLAB products
- **GCC installation:**
    - install the desired gcc version
- **BTC EmbeddedPlatform installation:**
    - copy the required files from the BTC EmbeddedPlatform image
    - run the addMLIntegration.bash script to integrate BTC EmbeddedPlatform with MATLAB
    - install the btc_embedded python module

## Run the tests
Let’s assume you’ve checked out the git repository with your code in the current directory and it has a structure like this:
```
.
├── model
    ├── my-swc.slx
│   └── my-swc.sldd
└── test
    ├── my-swc.epp
    └── run_tests.py
```

You can now run the tests like this:
```bash
docker run -v "$(pwd):$(pwd)" btc-embedded python3 "test/run_tests.py"
```
For more detailed examples of automating BTC test steps in Python, please check out our examples on GitHub https://github.com/btc-embedded/btc-ci-workflow/blob/main/examples/test_workflow_ec.py. 

A simple version of the `run_tests.py` script could look like the snippet below:

```python
import os
from btc_embedded import EPRestApi

# connect to BTC EmbeddedPlatform REST API
ep = EPRestApi() # by default this connects to http://localhost:1337

# load a profile & update model
epp_file = os.path.abspath("test/profile.epp")
ep.get(f'profiles/{epp_file}')
ep.put('architectures?performUpdateCheck=true')

# run functional tests on the code
scopes = ep.get('scopes')
ep.post('scopes/test-execution-rbt', {
    'UIDs': [scope['uid'] for scope in scopes],
    'data' : {
        'execConfigNames' : [ 'SL MIL', 'SIL' ]
    }
})

# Create and export test report and export to a file called 'report.html'
report = ep.post(f"scopes/{scopes[0]['uid']}/project-report?template-name=rbt-ec")
ep.post(f"reports/{report['uid']}", { 'exportPath': os.path.dirname(epp_file) })

# Save *.epp
ep.put('profiles', { 'path': epp_file })
```

# Technical support

If you require assistance or have a request for additional features or capabilities, contact the [BTC Embedded Systems AG technical support](https://www.btc-embedded.com/contact-support/).
