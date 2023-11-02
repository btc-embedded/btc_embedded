import os
import platform
import subprocess
import time

import requests

from btc_embedded.config import BTC_CONFIG_ENVVAR_NAME, get_global_config


class EPRestApi:
    #Starter for the EP executable
    def __init__(self, host='http://localhost', port=1337, version=None, install_root=None, install_location=None, lic='', config=None):
        """
        Wrapper for the BTC EmbeddedPlatform REST API
        - when created without arguments, it uses the default install location & version defined in the global config (btc_config.yml)

        On Mac and Linux operating systems, the tool start is not handled by the wrapper.
        Instead, it tries to connect to a running instance at the specified port.
        You can call something like
           'docker run -p 1337:8080 -v "/my/workdir:/my/workdir" btces/ep'
        to run the BTC EmbeddedPlatform docker image.
        """
        self._PORT_ = str(port)
        self._HOST_ = host
        self.definitively_closed = False
        self.actively_started = False
        # use default config, if no config was specified
        if not config: config = get_global_config()
        # set install location based on install_root and version if set explicitly
        if version and install_root: install_location = f"{install_root}/ep{version}"
        # fallback: determine based on config
        if not (version and install_location) and 'installationRoot' in config and 'epVersion' in config:
            version = config['epVersion']
            install_location = f"{config['installationRoot']}/ep{config['epVersion']}"
        if not self.is_rest_service_available():
            if platform.system() == 'Windows':
                headless_application_id = 'ep.application.headless' if version < '23.3p0' else 'ep.application.headless.HeadlessApplication'
                # check if we have what we need
                if not (version and install_location): raise Exception("Cannot start BTC EmbeddedPlatform. Arguments version and install_location or install_root directory must be specified or configured in a config file (installationRoot)")
                # all good -> prepare start command for BTC EmbeddedPlatform
                appdata_location = os.environ['APPDATA'].replace('\\', '/') + f"/BTC/ep/{version}/"
                print(f'Waiting for BTC EmbeddedPlatform {version} to be available:')
                ml_port = 29300 + (port % 100)
                if ml_port == port:
                    ml_port -= 100
                args = f'"{install_location}/rcp/ep.exe"' + \
                    ' -clearPersistedState' + \
                    ' -application' + ' ' + headless_application_id + \
                    ' -nosplash' + \
                    ' -vmargs' + \
                    ' -Dep.runtime.batch=ep' + \
                    ' -Dep.runtime.api.port=' + str(ml_port) + \
                    ' -Dosgi.configuration.area.default="' + appdata_location + self._PORT_ + '/configuration"' + \
                    ' -Dosgi.instance.area.default="' + appdata_location + self._PORT_ + '/workspace"' + \
                    ' -Dep.configuration.logpath=AppData/Roaming/BTC/ep/' + version + '/' + self._PORT_ + '/logs' + \
                    ' -Dep.runtime.workdir=BTC/ep/' + version + '/' + self._PORT_ + \
                    ' -Dep.licensing.package=' + lic + \
                    ' -Dep.rest.port=' + self._PORT_
                subprocess.Popen(args, stdout=open(os.devnull, 'wb'), stderr=subprocess.STDOUT)
                self.actively_started = True
        else:
            print(f'Connected to BTC EmbeddedPlatform REST API at {host}:{port}')
            self.apply_preferences(config)
            return
        print(f'Connecting to BTC EmbeddedPlatform REST API at {host}:{port}')
        while not self.is_rest_service_available():
            time.sleep(2)
            print('.', end='')
        print('\nBTC EmbeddedPlatform has started.')
        self.apply_preferences(config)

    # closes the application
    def close_application(self):
        print('Exiting EP... please wait while we save your data.')
        request = requests.delete(self._url('/application'))
        print(request.text)
        self.definitively_closed = True

    def __del__(self):
        # might already be closed. not our problem.
        if self.actively_started and not self.definitively_closed:
            try: 
                pass
                #self.close_application()
            except:
                pass

    # wrapper directly returns the relevant object if possible
    def get(self, urlappendix, message=None):
        """Returns the result object, or the response, if no result object is available."""
        response = self.get_req(urlappendix, message)
        return self.extract_result(response)
    
    # wrapper directly returns the relevant object if possible
    def post(self, urlappendix, requestBody=None, message=None):
        """Returns the result object, or the response, if no result object is available."""
        response = self.post_req(urlappendix, requestBody, message)
        return self.extract_result(response)
    
    # wrapper directly returns the relevant object if possible
    def put(self, urlappendix, requestBody=None, message=None):
        """Returns the result object, or the response, if no result object is available."""
        response = self.put_req(urlappendix, requestBody, message)
        return self.extract_result(response)

    # wrapper directly returns the relevant object if possible
    def delete(self, urlappendix, message=None):
        """Performs a delete request and returns the response object"""
        return self.delete_req(urlappendix, message)

    # extracts the response object which can be nested in different ways
    def extract_result(self, response):
        """If the response object contains data, it is accessed via .json().
        If this data has a result field (common for post requests), its content is returned, otherwise the data object itself.
        If the response object has no data, the response iteslf is returned."""
        try:
            result = response.json()
            if 'result' in result:
                return result['result']
            else:
                return result
        except Exception:
            return response

    # Performs a get request on the given url extension
    def get_req(self, urlappendix, message=None):
        """Returns an http response object. If the POST method is expected to return an object,
        it's usually accessed by calling response.json()"""
        if not 'progress' in urlappendix:
            # print this unless it's a progress query (to avoid flooding the console)
            if message: print(message)
        response = requests.get(self._url(urlappendix.replace('\\', '/').replace(' ', '%20')))
        if not response.ok:
            raise Exception(f"Error during request GET {urlappendix}: {response.status_code}: {response.content}")
        return self.check_long_running(response)
    
    # Performs a delete request on the given url extension
    def delete_req(self, urlappendix, message=None):
        if message: print(message)
        response = requests.delete(self._url(urlappendix.replace('\\', '/').replace(' ', '%20')))
        if not response.ok:
            raise Exception(f"Error during request DELETE {urlappendix}: {response.status_code}: {response.content}")
        return self.check_long_running(response)

    # Performs a post request on the given url extension. The optional requestBody contains the information necessary for the request
    def post_req(self, urlappendix, requestBody=None, message=None):
        """Returns an http response object. If the POST method is expected to return an object,
        it's usually accessed by calling response.json()['result']"""
        url = urlappendix.replace('\\', '/').replace(' ', '%20')
        if message: print(message)
        if requestBody == None:
            response = requests.post(self._url(url))
        else:
            response = requests.post(self._url(url),json=requestBody)
        if not response.ok:
            raise Exception(f"Error during request POST {url}: {response.status_code}: {response.content}")
        return self.check_long_running(response)

    # Performs a post request on the given url extension. The optional requestBody contains the information necessary for the request
    def put_req(self, urlappendix, requestBody=None, message=None):
        url = urlappendix.replace('\\', '/').replace(' ', '%20')
        if message: print(message)
        if requestBody == None:
            response = requests.put(self._url(url))
        else:
            response = requests.put(self._url(url),json=requestBody)
        if not response.ok:
            raise Exception(f"Error during request PUT {url}: {response}")
        return self.check_long_running(response)

    # Checks if the REST Server is available
    def is_rest_service_available(self):
        try:
            response = requests.get(self._url('/test'))
        except requests.exceptions.ConnectionError:
            return False
        return response.ok

    # it's not important if the path starts with /, ep/ or directly with a resource
    def _url(self, path):
        return f"{self._HOST_}:{self._PORT_}/ep/{path.lstrip('/')}"

    # This method is used to poll a request until the progress is done.
    def check_long_running(self, response):
        if response.status_code == 202:
            jsonResponse = response.json()
            for key, value in jsonResponse.items():
                if key == 'jobID':
                    while response.status_code == 202:
                        time.sleep(2)
                        print('.', end='')
                        response = self.poll_long_running(value)
                    print('')
        return response

    def poll_long_running(self, jobID):
        return self.get_req('/progress?progress-id=' + jobID)

    def set_compiler(self, config=None, value=None):
        """Sets the configured compiler. If no config object is passed in, the default config will be used.
        For Linux/Docker based scenarios, the config has no effect."""
        try:
            if not value and not (config and 'compiler' in config):
                config = get_global_config()
                value = config['compiler']
            if platform.system() == 'Windows':
                preferences = [ { 'preferenceName' : 'GENERAL_COMPILER_SETTING', 'preferenceValue' : value } ]
                self.put_req('preferences', preferences)
            else: # linux/docker
                self.put_req('preferences', [ { 'preferenceName' : 'GENERAL_COMPILER_SETTING', 'preferenceValue' : 'GCC (64bit)' } ])
        except Exception as e:
            # needed because the API reacts weird when the compiler is already configured
            pass

    def apply_preferences(self, config):
        """Applies the preferences defined in the config object"""
        if config and 'preferences' in config:
            preferences = []
            for pref_key in list(config['preferences'].keys()):
                # special handling for matlab version
                if pref_key == 'GENERAL_MATLAB_CUSTOM_VERSION':
                    preferences.append( { 'preferenceName' : 'GENERAL_MATLAB_VERSION', 'preferenceValue': 'CUSTOM' } )
                    preferences.append( { 'preferenceName' : pref_key, 'preferenceValue': config['preferences'][pref_key] })
                # special handling for compiler
                elif pref_key == 'GENERAL_COMPILER_SETTING':
                    self.set_compiler(value=config['preferences'][pref_key])
                elif pref_key == 'REPORT_TEMPLATE_FOLDER':
                    template_folder = self.rel_to_abs(config['preferences'][pref_key])
                    if template_folder: preferences.append( { 'preferenceName' : pref_key, 'preferenceValue': template_folder })
                # all other cases
                else:
                    preferences.append( { 'preferenceName' : pref_key, 'preferenceValue': config['preferences'][pref_key] })
            
            # apply preferences
            try:
                self.put('preferences', preferences)
                print(f"Applied preferences from the config")
            except (Exception):
                # if it fails to apply all preferences, apply individually
                successfully_applied = 0
                for pref in preferences:
                    try:
                        self.put('preferences', [pref]) # apply single pref
                        successfully_applied += 1
                    except Exception:
                        print(f"Failed to apply preference {pref}")
                print(f"Successfully applied {successfully_applied} out of {len(preferences)} preferences.")

    def rel_to_abs(self, rel_path):
        """Converts a relative path to an absolute path using the
        parent directory of the file indicated by the env var
        BTC_API_CONFIG_FILE as the root dir.
        Returns None if the env var is not set"""
        if os.path.isabs(rel_path):
            # directly return path because it's already absolute
            return rel_path 
        elif BTC_CONFIG_ENVVAR_NAME in os.environ:
            # Create absolute path using root dir
            root_dir = os.path.dirname(os.environ[BTC_CONFIG_ENVVAR_NAME])
            return os.path.join(root_dir, rel_path)
        print(f"Cannot convert relative path to absolute path because the environment variable {BTC_CONFIG_ENVVAR_NAME} is not set.")
        return None


# if called directly, starts EP based on the global config
if __name__ == '__main__':
    EPRestApi()
