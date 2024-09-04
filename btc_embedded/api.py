import os
import platform
import re
import shutil
import signal
import subprocess
import time
from datetime import datetime
from urllib.parse import quote, unquote

import requests

from btc_embedded.config import (BTC_CONFIG_ENVVAR_NAME,
                                 get_config_path_from_resources,
                                 get_global_config)
from btc_embedded.helpers import install_btc_config, install_report_templates

VERSION_PATTERN = r'ep(\d+\.\d+[a-zA-Z]\d+)' # e.g. "ep24.3p1"
HEADERS = {'Accept': 'application/json, text/plain', 'Content-Type' : 'application/json'}
DATE_FORMAT_MESSAGES = '%d-%b-%Y %H:%M:%S'
DATE_FORMAT_LOGFILE = '%Y-%m-%d %H:%M:%S'
EXCLUDED_ERROR_MESSAGES = [
    'The compiler is already defined',
    'No message found for the given query.'
]
EXCLUDED_LOG_MESSAGES = [
    'Registry key could not be read: The system cannot find the file specified'
]

class EPRestApi:
    #Starter for the EP executable
    def __init__(self, host='http://localhost', port=1337, version=None, install_root='C:/Program Files/BTC', install_location=None, lic='', config=None, license_location=None, timeout=120, skip_matlab_start=False, skip_config_install=False):
        """
        Wrapper for the BTC EmbeddedPlatform REST API
        - when created without arguments, it uses the default install 
        location & version defined in the global config (btc_config.yml)
        - the global config is identified by the BTC_API_CONFIG_FILE 
        env variable or uses the btc_config.yml file shipped with this module as a fallback
        
        Parameters (all optional):
        - host: a valid hostname or IP address to connect to the BTC EmbeddedPlatform API (default: 'http://localhost')
        - port: the port to use to communicate with the BTC EmbeddedPlatform API (default: 1337)
        - version: the BTC EmbeddedPlatform API (like '24.2p0', default: determined automatically)
        - install_root: root directory of the BTC installation (default: 'C:/Program Files/BTC')
        - install_location: alternative way to specify the BTC executable (default: determined automatically)
        - lic can optionally be defined to select a license package (e.g. lic='ET_BASE' to only use EmbeddedTester BASE)
        - license_location should point to the flexnet license server serving the btc licenses
        - config: you can pass in a config object to override settings of the global configuration with project specific values
        - timeout: timeout in seconds to start up BTC EmbeddedPlatform (default: 120)
        - skip_config_install: skips the automatic installation of a global btc_config.yml on your machine (default: False)
        - skip_matlab_start: only relevant in Docker-based use cases where Matlab is available but shall not be started (default: False)
        """
        self._PORT_ = "8080" if platform.system() == 'Linux' else str(port)
        self._HOST_ = host
        self.definitively_closed = False
        self.actively_started = False
        self.ep_process = None
        self.config = None
        # use default config, if no config was specified
        if config:
            self.config = config
        else:
            if platform.system() == 'Windows' and self._is_localhost() and not skip_config_install:
                install_btc_config()
            self.config = get_global_config()
        # apply timeout from config if specified
        if 'startupTimeout' in self.config: timeout = self.config['startupTimeout']
        # set install location based on install_root and version if set explicitly
        if version and install_root: install_location = f"{install_root}/ep{version}"
        if install_location and not version:
            match = re.search(VERSION_PATTERN, install_location)
            if match: version = match.group(1)
        # fallback: determine based on config
        if not (version and install_location) and 'installationRoot' in self.config and 'epVersion' in self.config:
            version = version or self.config['epVersion']
            install_location = f"{self.config['installationRoot']}/ep{version}"
        if not self._is_rest_service_available():
            if platform.system() == 'Windows': self._start_app_windows(version, install_location, port, license_location, lic)
            elif platform.system() == 'Linux': self._start_app_linux(skip_matlab_start)
        else:
            print(f'Connected to BTC EmbeddedPlatform REST API at {host}:{self._PORT_}')
            self._apply_preferences()
            return
        start_time = time.time()
        print(f'Connecting to BTC EmbeddedPlatform REST API at {host}:{self._PORT_}')
        while not self._is_rest_service_available():
            if (time.time() - start_time) > timeout:
                print(f"\n\nCould not connect to EP within the specified timeout of {timeout} seconds. \n\n")
                raise Exception("Application didn't respond within the defined timeout.")
            elif (not self._is_ep_process_still_alive()):
                print(f"\n\nApplication failed to start. Please check the log file for further information:\n{self.log_file_path}\n\n")
                self.print_log_entries(start_time)
                raise Exception("Application failed to start.")
            time.sleep(2)
            print('.', end='')
        print('\nBTC EmbeddedPlatform has started.')
        self._apply_preferences()

    # - - - - - - - - - - - - - - - - - - - - 
    #   PUBLIC FUNCTIONS
    # - - - - - - - - - - - - - - - - - - - - 

    # closes the application
    def close_application(self):
        self.delete('application?force-quit=true')
        start_time = time.time()
        if self.ep_process:
            while self._is_rest_service_available():
                if (time.time() - start_time) > 10:
                    # kill by PID if it didn't close within 10s
                    try:
                        os.kill(self.ep_process.pid, signal.SIGINT)
                    except:
                        pass # silently continue
                else:
                    time.sleep(2)
            self.definitively_closed = True

    # wrapper directly returns the relevant object if possible
    def get(self, urlappendix, message=None):
        """Returns the result object, or the response, if no result object is available."""
        response = self.get_req(urlappendix, message)
        return self._extract_result(response)
    
    # wrapper directly returns the relevant object if possible
    def post(self, urlappendix, requestBody=None, message=None):
        """Returns the result object, or the response, if no result object is available."""
        response = self.post_req(urlappendix, requestBody, message)
        return self._extract_result(response)
    
    # wrapper directly returns the relevant object if possible
    def put(self, urlappendix, requestBody=None, message=None):
        """Returns the result object, or the response, if no result object is available."""
        try:
            response = self.put_req(urlappendix, requestBody, message)
        except Exception as e:
            self.print_messages()
            print("\n")
            raise e
        return self._extract_result(response)

    # wrapper directly returns the relevant object if possible
    def delete(self, urlappendix, message=None):
        """Performs a delete request and returns the response object"""
        return self.delete_req(urlappendix, message)

    def set_compiler(self, config=None, value=None):
        """Sets the configured compiler. If no config object is passed in, the default config will be used.
        For Linux/Docker based scenarios, the config has no effect."""
        try:
            if not value and not (config and 'compiler' in config):
                config = self.config
                value = config['compiler']
            if platform.system() == 'Windows':
                preferences = [ { 'preferenceName' : 'GENERAL_COMPILER_SETTING', 'preferenceValue' : value } ]
                self.put_req('preferences', preferences)
            else: # linux/docker
                self.put_req('preferences', [ { 'preferenceName' : 'GENERAL_COMPILER_SETTING', 'preferenceValue' : 'GCC (64bit)' } ])
        except Exception as e:
            # needed because the API reacts weird when the compiler is already configured
            pass

    def print_messages(self, search_string=None, severity=None):
        """Prints all messages since the last profile create/profile load.
        Optional filters are available:
        
        - severity: INFO, WARNING, ERROR or CRITICAL
        - search_string: only prints messages that contain the given string"""
        if hasattr(self, 'message_marker_date') and self.message_marker_date:
            path = f"/message-markers/{self.message_marker_date}/messages"
            if search_string: path += '?search-string=' + search_string
            if severity: path += ('&' if search_string else '?') + f"severity={severity}"
            try:
                messages = self.get(path)
                messages.sort(key=lambda msg: datetime.strptime(msg['date'], DATE_FORMAT_MESSAGES))
                for msg in messages:
                    print(f"[{msg['date']}][{msg['severity']}] {msg['message']}" + (f" (Hint: {msg['hint']})" if 'hint' in msg and msg['hint'] else ""))
                print("\n")
            except:
                pass

    # - - - - - - - - - - - - - - - - - - - - 
    #   DEPRICATED PUBLIC FUNCTIONS
    # - - - - - - - - - - - - - - - - - - - - 

    # Performs a get request on the given url extension
    def get_req(self, urlappendix, message=None):
        """Public access to this method is DEPRICATED. Use get() instead, unless you want to get the raw http response"""
        url = self._precheck_get(urlappendix, message)
        response = requests.get(self._url(url))
        return self._check_long_running(response)
    
    # Performs a delete request on the given url extension
    def delete_req(self, urlappendix, message=None):
        """Public access to this method is DEPRICATED. Use delete() instead, unless you want to get the raw http response"""
        if message: print(message)
        response = requests.delete(self._url(urlappendix), headers=HEADERS)
        return self._check_long_running(response)

    # Performs a post request on the given url extension. The optional requestBody contains the information necessary for the request
    def post_req(self, urlappendix, requestBody=None, message=None):
        """Public access to this method is DEPRICATED. Use post() instead, unless you want to get the raw http response"""
        self._precheck_post(urlappendix)
        url = urlappendix.replace('\\', '/').replace(' ', '%20')
        if message: print(message)
        try:
            if requestBody == None:
                response = requests.post(self._url(url), headers=HEADERS)
            else:
                response = requests.post(self._url(url), json=requestBody, headers=HEADERS)
        except Exception as e:
            self.print_messages()
            print("\n")
            raise e
        return self._check_long_running(response)

    # Performs a post request on the given url extension. The optional requestBody contains the information necessary for the request
    def put_req(self, urlappendix, requestBody=None, message=None):
        """Public access to this method is DEPRICATED. Use put() instead, unless you want to get the raw http response"""
        url = urlappendix.replace('\\', '/').replace(' ', '%20')
        if message: print(message)
        if requestBody == None:
            response = requests.put(self._url(url), headers=HEADERS)
        else:
            response = requests.put(self._url(url), json=requestBody, headers=HEADERS)
        return self._check_long_running(response)


    # - - - - - - - - - - - - - - - - - - - - 
    #   PRIVATE HELPER FUNCTIONS
    # - - - - - - - - - - - - - - - - - - - - 

    # extracts the response object which can be nested in different ways
    def _extract_result(self, response):
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

    # Checks if the REST Server is available
    def _is_rest_service_available(self):
        try:
            response = requests.get(self._url('/test'))
        except requests.exceptions.ConnectionError:
            return False
        return response.ok

    # it's not important if the path starts with /, ep/ or directly with a resource
    def _url(self, path):
        return f"{self._HOST_}:{self._PORT_}/ep/{path.lstrip('/')}".replace('/ep/ep/', '/ep/')

    # This method is used to poll a request until the progress is done.
    def _check_long_running(self, response):
        if not response.ok:
            response_content = response.content.decode('utf-8')
            # if the error is none of the excluded messages -> print messages, etc.
            if all(msg not in response_content for msg in EXCLUDED_ERROR_MESSAGES):
                print(f"\n\nError: {response_content}\n\n")
                self.print_messages()
                raise Exception(response_content)
        if response.status_code == 202:
            jsonResponse = response.json()
            for key, value in jsonResponse.items():
                if key == 'jobID':
                    while response.status_code == 202:
                        time.sleep(2)
                        print('.', end='')
                        response = self._poll_long_running(value)
                    print('')
        return response

    def _poll_long_running(self, jobID):
        return self.get_req('/progress?progress-id=' + jobID)

    def _apply_preferences(self):
        """Applies the preferences defined in the config object"""
        config = self.config
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
                    if BTC_CONFIG_ENVVAR_NAME in os.environ:
                        template_folder = self._rel_to_abs(config['preferences'][pref_key])
                    else:
                        template_folder = os.path.join(os.path.dirname(get_config_path_from_resources()), 'projectreport_templates')
                    if not (template_folder and os.path.isdir(template_folder)):
                        install_report_templates(template_folder)
                    preferences.append( { 'preferenceName' : pref_key, 'preferenceValue': template_folder })
                elif pref_key == 'ARCHITECTURE_EC_CUSTOM_USER_CONFIGURATION_FOLDER':
                    ec_cfg_folder  = self._rel_to_abs(config['preferences'][pref_key])
                    preferences.append( { 'preferenceName' : pref_key, 'preferenceValue': ec_cfg_folder })
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

    def _rel_to_abs(self, rel_path):
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
    
    def _precheck_post(self, urlappendix):
        # create message marker 
        if urlappendix[:8] == 'profiles': self.message_marker_date = self.post('message-markers')['date']
            
    def _precheck_get(self, urlappendix, message):
        if not 'progress' in urlappendix:
            # print this unless it's a progress query (to avoid flooding the console)
            if message: print(message)
        url_combined = urlappendix
        if urlappendix[:8] == 'profiles':
            # set/reset message marker
            self.message_marker_date = self.post('message-markers')['date']
            # ensure profile is available and path is url-safe
            index_qmark = urlappendix.find('?')
            path = urlappendix[9:index_qmark] if index_qmark > 0 else urlappendix[9:]
            suffix = urlappendix[index_qmark:] if index_qmark > 0 else ""
            path = unquote(path) # unquote incase caller already quoted the path
            if not os.path.isfile(path) and self._is_localhost():
                print(f"\nThe profile '{path}' cannot be found. Please ensure that the file is available.\n")
                exit(1)
            path = quote(path, safe="")
            url_combined = 'profiles/' + path + suffix
        
        return url_combined

    def _is_rest_addon_installed(self, version):
        import winreg
        keys = [ 'REST_Server_EU', 'REST_Server_BASE_EU', 'REST_Server_JP' ]
        for key in keys:
            try:
                # Attempt to open the registry key
                reg_key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, rf'SOFTWARE\BTC\EmbeddedPlatform {version}\Addons\{key}', access=winreg.KEY_READ | winreg.KEY_WOW64_64KEY)
                winreg.CloseKey(reg_key)
                return True
            except OSError:
                continue
        return False

    # start commands depending on OS

    def _start_app_linux(self, skip_matlab_start):
        # container use case -> start EP and Matlab
        try:
            ep_ini_path = os.path.join(os.environ['EP_INSTALL_PATH'], 'ep.ini')
            with open(ep_ini_path, 'r') as file:
                content = file.read()
            version = re.search(r'/ep/(\d+\.\d+[a-zA-Z]*\d+)/', content).group(1)
        except:
            version = '24.2p0'
        headless_application_id = 'ep.application.headless' if version < '23.3p0' else 'ep.application.headless.HeadlessApplication'
        matlab_ip = os.environ['MATLAB_IP'] if 'MATLAB_IP' in os.environ else '127.0.0.1'
        print(f'Waiting for BTC EmbeddedPlatform {version} to be available:')

        args = [ os.environ['EP_INSTALL_PATH'] + '/ep',
            '-clearPersistedState', '-nosplash', '-console', '-consoleLog',
            '-application', headless_application_id,            
            '-vmargs',
            '-Dep.linux.config=' + os.environ['EP_REGISTRY'],
            '-Dlogback.configurationFile=' + os.environ['EP_LOG_CONFIG'],
            '-Dep.configuration.logpath=' + os.environ['LOG_DIR'],
            '-Dep.runtime.workdir=' + os.environ['WORK_DIR'],
            '-Dbtc.root.temp.dir=' + os.environ['TMP_DIR'],
            '-Dep.licensing.location=' + os.environ['LICENSE_LOCATION'],
            '-Dep.licensing.package=' + os.environ['LICENSE_PACKAGES'],
            '-Dep.rest.port=' + os.environ['REST_PORT'],
            '-Dosgi.configuration.area.default=/tmp/ep/configuration',
            '-Dosgi.instance.area.default=/tmp/ep/workspace',
            '-Dep.runtime.batch=ep',
            '-Dep.runtime.api.port=1109',
            '-Dep.matlab.ip.range=' + matlab_ip ]
        
        # start ep process
        self.ep_process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.log_file_path = os.environ['LOG_DIR'] + '/current.log'
        self.actively_started = True
        
        # if container has matlab -> assume that this shall be started as well
        if shutil.which('matlab') and not skip_matlab_start:
            import pty
            _, secondary_pty = pty.openpty()
            subprocess.Popen('matlab', stdin=secondary_pty)

    def _start_app_windows(self, version, install_location, port, license_location, lic):
        headless_application_id = 'ep.application.headless' if version < '23.3p0' else 'ep.application.headless.HeadlessApplication'
        # check if we have what we need
        if not (version and install_location): raise Exception("Cannot start BTC EmbeddedPlatform. Arguments version and install_location or install_root directory must be specified or configured in a config file (installationRoot)")
        # all good -> prepare start command for BTC EmbeddedPlatform
        appdata_location = os.environ['APPDATA'].replace('\\', '/') + f"/BTC/ep/{version}/"
        ml_port = 29300 + (port % 100)
        if ml_port == port:
            ml_port -= 100
        if not os.path.isfile(f"{install_location}/rcp/ep.exe"):
            print(f'''\n\nBTC EmbeddedPlatform Executable (ep.exe) could not be found at the expected location ("{install_location}/rcp/ep.exe").
- Please provide the correct version and installation root path:
-> either using the version and install_root parameters of the EPRestApi constructor
-> or via the properties epVersion and installationRoot in the config file
- The installation root directory is expected to contain the sub directory ep{version}.\n\n''')
            raise Exception("EP Executable not found, cannot start BTC EmbeddedPlatform.")
        if not self._is_rest_addon_installed(version):
            print(f'''\n\nThe REST API AddOn is not installed for BTC EmbeddedPlatform {version}\n\n''')
            raise Exception("Addon not installed.")
        print(f'Waiting for BTC EmbeddedPlatform {version} to be available:')
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
        if license_location or self.config and 'licenseLocation' in self.config:
                args += f" -Dep.licensing.location={(license_location or self.config['licenseLocation'])}"
        self.ep_process = subprocess.Popen(args, stdout=open(os.devnull, 'wb'), stderr=subprocess.STDOUT)
        self.log_file_path = appdata_location + self._PORT_ + '/logs/current.log'
        self.actively_started = True

    def _does_api_support_signalinfo(self):
        # check if the current EP version supports querying signal info details
        r = requests.get(self._url('signals/UNDEFINED/signal-datatype-information'))
        api_call_supported = (b'No signal' in r.content)
        return api_call_supported

    def _is_ep_process_still_alive(self):
        return self.ep_process and self.ep_process.poll() is None

    def _is_localhost(self):
        return self._HOST_ in [ 'http://localhost', 'http://127.0.0.1']
    
    def get_errors_from_log(self, start_time):
        log_entries = []
        if self.log_file_path and os.path.isfile(self.log_file_path):
            # Regular expression pattern to match timestamp lines
            timestamp_pattern = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")
            with open(self.log_file_path, 'r') as logfile:
                current_entry = None
                for line in logfile:
                    timestamp_pattern_match = timestamp_pattern.match(line)
                    if timestamp_pattern_match:
                        # store previous entry
                        if current_entry: log_entries.append(current_entry.strip())
                        # start new entry if time matches
                        timestamp_str = timestamp_pattern_match.group(0)
                        timestamp = datetime.strptime(timestamp_str, DATE_FORMAT_LOGFILE)
                        # create bools for readability
                        is_recent = timestamp > datetime.fromtimestamp(start_time)
                        is_error = 'ERROR' in line.upper()
                        is_not_excluded = not any(bad_string in line for bad_string in EXCLUDED_LOG_MESSAGES)
                        # check if line is relevant
                        if is_error and is_recent and is_not_excluded:
                            current_entry = line
                        else:
                            current_entry = None
                    else:
                        # Continuation of the current log entry
                        if not current_entry == None:
                            current_entry += line + "\n"
                
                # add last entry (if any)
                if current_entry: log_entries.append(current_entry.strip())

        return log_entries

    def print_log_entries(self, start_time):
        for entry in self.get_errors_from_log(start_time): print(entry)


# if called directly, starts EP based on the global config
if __name__ == '__main__':
    EPRestApi()
