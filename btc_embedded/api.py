# Configure logger
import inspect
import logging
import os
import platform
import re
import shutil
import signal
import subprocess
import threading
import time
from datetime import datetime
from urllib.parse import quote, unquote

import requests

from btc_embedded.config import (BTC_CONFIG_ENVVAR_NAME,
                                 get_config_path_from_resources,
                                 get_global_config)
from btc_embedded.helpers import (get_processes_by_name, install_btc_config,
                                  install_report_templates, is_port_in_use)

# Constants
VERSION_PATTERN = r'ep(\d+\.\d+[a-zA-Z]\d+)' # e.g. "ep24.3p1"
HEADERS = {'Accept': 'application/json, text/plain', 'Content-Type' : 'application/json'}
DATE_FORMAT_MESSAGES = '%d-%b-%Y %H:%M:%S'
DATE_FORMAT_LOGFILE = '%Y-%m-%d %H:%M:%S'
MSG_RESOURCE_NOT_FOUND = 'The resource has not been found'
MSG_BAD_REQUEST = 'The provided input does not have a valid format'
EXCLUDED_ERROR_MESSAGES = [
    'The compiler is not valid or is not available.',
    'The compiler is already defined',
    'No message found for the given query.'
]
EXCLUDED_LOG_MESSAGES = [
    'Registry key could not be read: The system cannot find the file specified',
    'The compiler is already defined',
    'EpexCompilerServiceImpl - Compilation failed'
]

LOGGING_DISABLED = 1337

logger = logging.getLogger('btc_embedded')



class EPRestApi:
    #Starter for the EP executable
    def __init__(self,
        host='http://localhost',
        port=1337,
        version=None,
        install_root='C:/Program Files/BTC',
        install_location=None,
        lic='',
        config=None,
        license_location=None,
        additional_vmargs=[],
        timeout=120,
        skip_matlab_start=False,
        skip_config_install=False,
        log_level=logging.INFO,
        force_new_port=False):
        """
        Wrapper for the BTC EmbeddedPlatform REST API.
        When created without arguments, it uses the default install location & version defined in the global config (btc_config.yml).
        The global config is identified by the BTC_API_CONFIG_FILE environment variable or uses the btc_config.yml file shipped with this module as a fallback.
        - host (str): A valid hostname or IP address to connect to the BTC EmbeddedPlatform API (default: 'http://localhost').
        - port (int): The port to use to communicate with the BTC EmbeddedPlatform API (default: 1337).
        - version (str): The BTC EmbeddedPlatform API version (e.g., '24.2p0', default: determined automatically).
        - install_root (str): Root directory of the BTC installation (default: 'C:/Program Files/BTC').
        - install_location (str): Alternative way to specify the BTC executable (default: determined automatically).
        - lic (str): License package to select (e.g., 'ET_BASE' to only use EmbeddedTester BASE).
        - config (dict): Config object to override settings of the global configuration with project-specific values.
        - license_location (str): Path to the FlexNet license server serving the BTC licenses.
        - additional_vmargs (list): Additional VM arguments.
        - timeout (int): Timeout in seconds to start up BTC EmbeddedPlatform (default: 120).
        - skip_matlab_start (bool): Relevant in Docker-based use cases where Matlab is available but shall not be started (default: False).
        - skip_config_install (bool): Skips the automatic installation of a global btc_config.yml on your machine (default: False).
        - log_level (int): The log level to use for the logger (default: logging.INFO).
        - force_new_port (bool): If true will not connect to running instance of EP and instead search for open port. Increments from provided port. (default: False)
        """

        self.log_level = log_level
        self._PORT_ = "8080" if platform.system() == 'Linux' else str(port)
        self._HOST_ = host
        self.definitively_closed = False
        self.actively_started = False
        self.ep_process = None
        self.config = None
        self.start_time = time.time()
        self.force_new_port = force_new_port
        # default message marker date to 1 second before the start time (to be sure to include all following messages)
        self._set_message_marker()
        self._init_logging()

        #Search for open port if enabled
        if self.force_new_port:
            host_no_protocol = self._HOST_.replace("http://","").replace("https://","")
            self._PORT_ = str(self._find_next_port(int(self._PORT_), host_no_protocol))
        #
        # Prepare configuration
        #
        if config: self.config = config
        else: # default to global config
            if platform.system() == 'Windows' and self._is_localhost() and not skip_config_install:
                install_btc_config()
            self.config = get_global_config()
        # apply timeout from config if specified
        if 'startupTimeout' in self.config: timeout = self.config['startupTimeout']
        # set install location based on install_root and version if set explicitly
        if version and install_root and not install_location: install_location = f"{install_root}/ep{version}"
        if install_location and not version:
            match = re.search(VERSION_PATTERN, install_location)
            if match: version = match.group(1)
        # fallback: determine based on config
        if not (version and install_location) and 'installationRoot' in self.config and (version or 'epVersion' in self.config):
            version = version or self.config['epVersion']
            install_location = f"{self.config['installationRoot']}/ep{version}"
        self._set_log_file_location(version)

        #
        # Start / Connect to the BTC EmbeddedPlatform
        #
        if self._is_rest_service_available(version):
            # connect to a running application
            version = self.get('openapi.json')['info']['version']
            logger.info(f'Connected to BTC EmbeddedPlatform {version} at {host}:{self._PORT_}')
        else:
            # start the application
            if platform.system() == 'Windows': self._start_app_windows(version, install_location, port, license_location, lic, additional_vmargs)
            elif platform.system() == 'Linux': version = self._start_app_linux(license_location, lic, skip_matlab_start, additional_vmargs)
            
            logger.info(f'Connecting to BTC EmbeddedPlatform REST API at {host}:{self._PORT_}')
            self._connect_within_timeout(timeout, version)
            
            logger.info('BTC EmbeddedPlatform has started.')
        self._apply_preferences(version)
        self.version = version
        

    # - - - - - - - - - - - - - - - - - - - - 
    #   PUBLIC FUNCTIONS
    # - - - - - - - - - - - - - - - - - - - - 

    # closes the application
    def close_application(self):
        """Closes the BTC EmbeddedPlatform application"""
        logger.info(f'Closing BTC EmbeddedPlatform {self.version}...')
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
        logger.info('BTC EmbeddedPlatform has been closed.')

    # wrapper directly returns the relevant object if possible
    def get(self, urlappendix, message=None, timeout=None):
        """Returns the result object, or the response, if no result object is available."""
        response = self.get_req(urlappendix, message)
        return self._extract_result(response)
    
    # wrapper directly returns the relevant object if possible
    def post(self, urlappendix, requestBody=None, message=None, timeout=None):
        """Returns the result object, or the response, if no result object is available."""
        response = self.post_req(urlappendix, requestBody, message, timeout)
        return self._extract_result(response)

    # wrapper directly returns the relevant object if possible
    def put(self, urlappendix, requestBody=None, message=None, timeout=None):
        """Returns the result object, or the response, if no result object is available."""
        response = self.put_req(urlappendix, requestBody, message, timeout)
        return self._extract_result(response)
    
    def patch(self, urlappendix, requestBody=None, message=None, timeout=None):
        """Returns the result object, or the response, if no result object is available."""
        response = self.patch_req(urlappendix, requestBody, message, timeout)
        return self._extract_result(response)
    
    # wrapper directly returns the relevant object if possible
    def delete(self, urlappendix, requestBody=None, message=None, timeout=None):
        """Performs a delete request and returns the response object"""
        return self.delete_req(urlappendix, requestBody, message, timeout)


    def _get_loglevel(self, severity):


        if severity == 'INFO': return logging.INFO


        if severity == 'WARNING': return logging.WARNING


        if severity == 'ERROR': return logging.ERROR


        return logging.CRITICAL

    def _handle_error(self, e, urlappendix, payload=None):
        """
        Handles an exception by printing the error message and the messages from the API.
        Args:
            e (Exception): The exception that was encountered.
        Behavior:
            - Prints the encountered error message.
            - Retrieves and prints messages from the API, if any.
            - Retrieves and prints errors from the log file, if any.
            - Re-raises the encountered exception.
        """
        # If _handle_error is already in the call stack, raise immediately to avoid recursion
        count = sum(1 for frame in inspect.stack() if frame.function == '_handle_error')
        if count > 2: raise BtcApiException(e)

        # special handling for "resource not found -> give information about request"
        if (MSG_RESOURCE_NOT_FOUND in str(e)):
            logger.error(f"\n\nYou requested a resource that doesn't exist: '{urlappendix}'\n\n")
            raise BtcApiException(e)
        elif (MSG_BAD_REQUEST in str(e)):
            import json
            logger.error(f"\n\nYou sent an invalid request to '{urlappendix}':\n{json.dumps(payload, indent=4)}\n\n")
            raise BtcApiException(e)
        else:
            logger.error(f"\n\nEncountered error: {e}\n\n")
        logger.info('---------------------------------------')
        messages = self.get_messages()
        if messages:
            logger.info(f"\n\nMessages: \n\n")
            for msg in messages:
                log_level = self._get_loglevel(msg['severity'])                
                logger.log(level=log_level, msg=f"[{msg['date']}] {msg['message']}" + (f" (Hint: {msg['hint']})" if 'hint' in msg and msg['hint'] else ""))
        
        logged_errors = self.get_errors_from_log(self.start_time)
        if logged_errors:

            logger.error(f"\n\nErrors from log file:\n{e}\n\n")
            for entry in self.get_errors_from_log(self.start_time): logger.error(entry)

        logger.info('---------------------------------------')
        raise BtcApiException(e)

    def set_compiler(self, config=None, value=None):
        """
        Sets the configured compiler. If no config object is passed in, the default config will be used.
        For Linux/Docker based scenarios, the config has no effect.
        Parameters:
        config (dict, optional): Configuration dictionary that may contain the compiler setting.
        value (str, optional): The compiler value to be set.
        Raises:
        Exception: If an error occurs during the setting of the compiler, it is caught and passed silently.
        """
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
        try:
            messages = self.get_messages(search_string, severity)
            for msg in messages:
                log_level = self._get_loglevel(msg['severity'])
                logger.log(level=log_level, msg=f"[{msg['date']}][{msg['severity']}] {msg['message']}" + (f" (Hint: {msg['hint']})" if 'hint' in msg and msg['hint'] else ""))


            logger.info("\n")
        except:
            logger.info("No messages available.")

    def get_messages(self, search_string=None, severity=None):
        """Returns all messages since the last profile create/profile load.
        Optional filters are available:
        - severity: INFO, WARNING, ERROR or CRITICAL
        - search_string: only prints messages that contain the given string
        
        Returns a list of message objects with date, severity, message and hint
        """
        messages = []
        if hasattr(self, 'message_marker_date') and self.message_marker_date:
            path = f"/message-markers/{self.message_marker_date}/messages"
            if search_string: path += '?search-string=' + search_string
            if severity: path += ('&' if search_string else '?') + f"severity={severity}"
            try:
                messages = self.get(path)
                if isinstance(messages, str):
                    messages = []
                try:
                    messages.sort(key=lambda msg: datetime.strptime(msg['date'], DATE_FORMAT_MESSAGES))
                except:
                    messages.sort(key=lambda msg: msg['date'])
            except:
                pass
        return messages

    # - - - - - - - - - - - - - - - - - - - - 
    #   DEPRICATED PUBLIC FUNCTIONS
    # - - - - - - - - - - - - - - - - - - - - 

    # Performs a get request on the given url extension
    def get_req(self, urlappendix, message=None, timeout=None):
        """Public access to this method is DEPRICATED. Use get() instead, unless you want to get the raw http response"""
        #logger.warning("DEPRICATED: Use get() instead of get_req().")
        url = self._precheck_get(urlappendix, message)
        try:
            response = requests.get(self._url(url))
        except Exception as e:
            self._handle_error(e, urlappendix)
        finally:
            self._the_watch_has_ended(urlappendix)
        return self._check_long_running(response, urlappendix,timeout)
    
    # Performs a delete request on the given url extension
    def delete_req(self, urlappendix, requestBody=None, message=None, timeout=None):
        """Public access to this method is DEPRICATED. Use delete() instead, unless you want to get the raw http response"""
        #logger.warning("DEPRICATED: Use delete() instead of delete_req().")
        if message: logger.info(message)
        try:
            if requestBody == None:
                response = requests.delete(self._url(urlappendix), headers=HEADERS)
            else:
                response = requests.delete(self._url(urlappendix), json=requestBody, headers=HEADERS)
        except Exception as e:
            self._handle_error(e, urlappendix, requestBody)
        return self._check_long_running(response, urlappendix, requestBody, timeout)

    # Performs a post request on the given url extension. The optional requestBody contains the information necessary for the request
    def post_req(self, urlappendix, requestBody=None, message=None, timeout=None):
        """Public access to this method is DEPRICATED. Use post() instead, unless you want to get the raw http response"""
        #logger.warning("DEPRICATED: Use post() instead of post_req().")
        self._precheck_post(urlappendix)
        url = urlappendix.replace('\\', '/').replace(' ', '%20')
        
        if message: logger.info(message)
        try:
            if requestBody == None:
                response = requests.post(self._url(url), headers=HEADERS)
            else:
                response = requests.post(self._url(url), json=requestBody, headers=HEADERS)
        except Exception as e:
            self._handle_error(e, urlappendix, requestBody)
        return self._check_long_running(response, urlappendix, requestBody, timeout)

    # Performs a post request on the given url extension. The optional requestBody contains the information necessary for the request
    def put_req(self, urlappendix, requestBody=None, message=None, timeout=None):
        """Public access to this method is DEPRICATED. Use put() instead, unless you want to get the raw http response"""
        #logger.warning("DEPRICATED: Use put() instead of put_req().")
        url = urlappendix.replace('\\', '/').replace(' ', '%20')
        if message: logger.info(message)
        try:
            if requestBody == None:
                response = requests.put(self._url(url), headers=HEADERS)
            else:
                response = requests.put(self._url(url), json=requestBody, headers=HEADERS)
        except Exception as e:
            self._handle_error(e, urlappendix, requestBody)
        
        finalResponse = self._check_long_running(response, urlappendix, requestBody, timeout)
        self._postcheck_put(urlappendix,finalResponse)
        return finalResponse
    
    # Performs a post request on the given url extension. The optional requestBody contains the information necessary for the request
    def patch_req(self, urlappendix, requestBody=None, message=None, timeout=None):
        """Public access to this method is DEPRICATED. Use patch() instead, unless you want to get the raw http response"""
        url = urlappendix.replace('\\', '/').replace(' ', '%20')
        if message: logger.info(message)
        try:
            if requestBody == None:
                response = requests.patch(self._url(url), headers=HEADERS)
            else:
                response = requests.patch(self._url(url), json=requestBody, headers=HEADERS)
        except Exception as e:
            self._handle_error(e, urlappendix, requestBody)
        return self._check_long_running(response, urlappendix, requestBody, timeout)


    # - - - - - - - - - - - - - - - - - - - - 
    #   PRIVATE HELPER FUNCTIONS
    # - - - - - - - - - - - - - - - - - - - - 

    def _connect_within_timeout(self, timeout, version):
        """Waits until the REST service is available or the timeout is reached. Frequently checks if the EP process is still alive."""
        while not self._is_rest_service_available(version):
            if (time.time() - self.start_time) > timeout:
                logger.error(f"\n\nCould not connect to EP within the specified timeout of {timeout} seconds. \n\n")
                raise BtcApiException("Application didn't respond within the defined timeout.")
            elif (not self._is_ep_process_still_alive()):
                logger.error(f"\n\nApplication failed to start. Please check the log file for further information:\n{self.log_file_path}\n\n")                
                self.print_log_entries()
                raise BtcApiException("Application failed to start.")
            time.sleep(2)
            #print('.', end='')

    
    # extracts the response object which can be nested in different ways
    def _extract_result(self, response):
        """If the response object contains data, it is accessed via .json().
        If this data has a result field (common for post requests), its content is returned, otherwise the data object itself.
        If the response object has no data, the response iteslf is returned."""
        try:
            content_type = response.headers.get('Content-Type')
            if content_type == 'application/json':
                result = response.json()
                if 'result' in result:
                    return result['result']
                else:
                    return result
            elif content_type == 'text/plain':
                return response.text
            else:
                return response
        except Exception:
            return response

    # Checks if the REST Server is available
    def _is_rest_service_available(self, requested_version=None):
        """
        Checks if the REST service is available by sending a GET request to the '/test' endpoint.

        Returns:
            bool: True if the service is available (response status code is 200-299), False otherwise.
        """
        try:
            response = requests.get(self._url('/test'))
            if response.ok:
                if requested_version:
                    version = self.get('openapi.json')['info']['version']
                    if version != requested_version:
                        old_port = self._PORT_
                        new_port = str(int(old_port) + 1)
                        logger.error(f"Port {old_port} is already in use by an instance of BTC EmbeddedPlatform {version}. Trying port {new_port} for version {requested_version}...")
                        self._PORT_ = new_port
                        return False
                return True
        except requests.exceptions.ConnectionError:
            pass
        return False

    # it's not important if the path starts with /, ep/ or directly with a resource
    def _url(self, path):
        return f"{self._HOST_}:{self._PORT_}/ep/{path.lstrip('/')}".replace('/ep/ep/', '/ep/')

    # This method is used to poll a request until the progress is done.
    def _check_long_running(self, response, urlappendix, payload=None, timeout=None):
        """
        Checks the status of a long-running operation and handles errors.

        Args:
            response (requests.Response): The initial response object to check.
            timeout: timeout in seconds

        Returns:
            requests.Response: The final response object after the long-running operation completes.

        Raises:
            Exception: If the response contains an error message not in the excluded list.

        Behavior:
            - If the response is not OK and contains an error message not in the excluded list, it prints the error message, calls `self.print_messages()`, and raises an Exception.
            - If the response status code is 202 (Accepted), it polls the long-running operation using the job ID until the status code is no longer 202.
        """

        start_time = time.time()
        cancelled = False

        if not timeout is None and self.version < '25.3p0':
            logger.warning("Cancellation of long running tasks was added in EP25.3p0. Timeout will not be considered.")
            timeout = None

        if not response.ok:
            response_content = response.content.decode('utf-8')
            # if the error is none of the excluded messages -> print messages, etc.
            if all(msg not in response_content for msg in EXCLUDED_ERROR_MESSAGES):
                self._handle_error(Exception(response_content), urlappendix, payload)
        try:
            job_id = response.json()['jobID']
            response = self._poll_long_running(job_id)
            while response.status_code == 202:
                time.sleep(2)
                response = self._poll_long_running(job_id)
                if not timeout is None and time.time()-start_time > timeout and not cancelled:
                    try:
                        self.get_req("progress/cancel",{"progress-id":job_id})
                        logger.info(f"Cancelling long running task: {urlappendix}")
                        cancelled = True
                    except:
                        logger.warning("Error cancelling long running task. Possibly the task is already completed")
        except BtcApiException as e:
            raise e
        except Exception as e:
            pass
        return response

    def _poll_long_running(self, jobID):
        # before 21.3, the jobID was appended to the URL, after 21.3 it is passed as a query parameter
        if self.version and self.version < '21.3p0':
            return self.get_req('/progress/' + jobID)
        else:
            return self.get_req('/progress?progress-id=' + jobID)

    def _set_log_file_location(self, version):
        if platform.system() == 'Windows':
            appdata_location = os.environ['APPDATA'].replace('\\', '/') + f"/BTC/ep/{version}/"
            self.log_file_path = os.path.join(appdata_location, self._PORT_, 'logs', 'current.log')
        else: #if platform.system() == 'Linux':
            log_dir = os.environ['LOG_DIR'] if 'LOG_DIR' in os.environ else '/tmp/ep/logs'
            self.log_file_path = os.path.join(log_dir, 'current.log')

    def _apply_preferences(self, version):
        """Applies the preferences defined in the config object"""
        config = self.config
        user_defined_datetime_format = False
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
                elif pref_key == 'GENERAL_DATE_FORMAT_PATTERN' or pref_key == 'GENERAL_TIME_FORMAT_PATTERN' and version >= '24.3p0':
                    user_defined_datetime_format = True
                    preferences.append( { 'preferenceName' : pref_key, 'preferenceValue': config['preferences'][pref_key] })
                # all other cases
                else:
                    preferences.append( { 'preferenceName' : pref_key, 'preferenceValue': config['preferences'][pref_key] })

            # set useful datetime format if not user-defined
            if version >= '24.3p0' and not user_defined_datetime_format:
                preferences.append( { 'preferenceName' : 'GENERAL_DATE_FORMAT_PATTERN', 'preferenceValue': 'YYYY-MM-dd' })
                preferences.append( { 'preferenceName' : 'GENERAL_TIME_FORMAT_PATTERN', 'preferenceValue': 'HH:mm:ss' })

            # apply preferences
            try:
                self.put('preferences', preferences)
                logger.debug(f"Applied preferences from the config")
            except (Exception):
                # if it fails to apply all preferences, apply individually
                successfully_applied = 0
                for pref in preferences:
                    try:
                        self.put('preferences', [pref]) # apply single pref
                        successfully_applied += 1
                    except Exception:

                        logger.error(f"Failed to apply preference {pref}")
                logger.debug(f"Successfully applied {successfully_applied} out of {len(preferences)} preferences.")

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
        logger.warning(f"Cannot convert relative path to absolute path because the environment variable {BTC_CONFIG_ENVVAR_NAME} is not set.")
        return None
    
    def _precheck_post(self, urlappendix):
        """Sets the message marker date if the url appendix starts with 'profiles'."""
        if urlappendix[:8] == 'profiles': self._set_message_marker()
    
    def _postcheck_put(self,urlappendix,response):
        if urlappendix == 'architectures?performUpdateCheck=true' : self._post_update_compiler_check(response)
    

    def _post_update_compiler_check(self,reponse):
        """Sets the compiler to config value if no architecture update was performed"""
        if reponse.status_code == 204:
            logger.info("Architecture update was skipped. Setting profile compiler to avoid potential SiL errors. May lead to a different compiler being used than configured MEX compiler.")
            self.set_compiler()
            
    def _precheck_get(self, urlappendix, message):
        """Prepares the URL appendix and sets the message marker date if the url appendix starts with 'profiles'."""
        if not 'progress' in urlappendix:
            # print this unless it's a progress query (to avoid flooding the console)
            if message: logger.info(message)
        url_combined = urlappendix
        if self._is_profile_load_call(urlappendix):
            # set/reset message marker
            self._set_message_marker()
            # ensure profile is available and path is url-safe
            if urlappendix.startswith('openprofile'):
                url_combined = self._get_profilesurl_post253(urlappendix, logger)
            else:
                if self.version and self.version >= '25.3p0':
                    logger.warning("Loading profiles via 'profiles/...' endpoint is deprecated since BTC EmbeddedPlatform 25.3p0. Please use 'openprofile?path=...' instead.")
                    url_combined = self._get_profilesurl_pre253(urlappendix, logger, convert_to_post253=True)
                else:
                    url_combined = self._get_profilesurl_pre253(urlappendix, logger)
                
            # watch profile migration status
            threading.Thread(target=self._watch_profile_migration, daemon=True).start()
        return url_combined

    def _is_profile_load_call(self, urlappendix):
        return urlappendix.startswith('openprofile') or urlappendix.startswith('profiles/')

    def _get_profilesurl_post253(self, urlappendix, logger):
        index_qmark = urlappendix.find('?')
        query_params_string = urlappendix[index_qmark+1:] if index_qmark > 0 else ""
        if query_params_string:
            query_param_pairs = query_params_string.split('&')
            for qpp in query_param_pairs:
                key, value = qpp.split('=')
                if key == 'path':
                    path = unquote(value) # unquote incase caller already quoted the path
                    if path and not os.path.isfile(path) and self._is_localhost():
                        logger.critical(f"\nThe profile '{path}' cannot be found. Please ensure that the file is available.\n")
                        exit(1)
                    path = quote(path, safe="")
                    break
            if path:
                # reconstruct query params string
                new_query_params = []
                for qpp2 in query_param_pairs:
                    key2, _ = qpp2.split('=')
                    if key2 == 'path':
                        new_query_params.append(f"{key2}={path}")
                    else:
                        new_query_params.append(qpp2)
                query_params_string = '&'.join(new_query_params)
            return 'openprofile?' + query_params_string
        raise Exception("Missing 'path' query parameter in openprofile request.")

    # profiles/C:/foo.epp?discardCurrentProfile=true
    def _get_profilesurl_pre253(self, urlappendix, logger, convert_to_post253=False):
        index_qmark = urlappendix.find('?')
        path = urlappendix[9:index_qmark] if index_qmark > 0 else urlappendix[9:]
        suffix = urlappendix[index_qmark:] if index_qmark > 0 else ""
        path = unquote(path) # unquote incase caller already quoted the path
        if path and not os.path.isfile(path) and self._is_localhost():
            logger.critical(f"\nThe profile '{path}' cannot be found. Please ensure that the file is available.\n")
            exit(1)
        path = quote(path, safe="")
        if convert_to_post253:
            return 'openprofile?path=' + path
        else:   
            return 'profiles/' + path + suffix

    def _is_rest_addon_installed(self, version):
        """
        Checks if the REST addon is installed for a given version of the BTC EmbeddedPlatform.

        This method attempts to open specific registry keys to determine if any of the REST addons
        ('REST_Server_EU', 'REST_Server_BASE_EU', 'REST_Server_JP') are installed for the specified
        version of the BTC EmbeddedPlatform.

        Args:
            version (str): The version of the BTC EmbeddedPlatform to check for the REST addon.

        Returns:
            bool: True if any of the REST addons are installed, False otherwise.
        """
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

    def _prepare_env(self):
        props_with_default_values = {
            'EP_INSTALL_PATH' : '/opt/ep',
            'EP_REGISTRY' : '/opt/Configuration/eplinuxregistry',
            'EP_LOG_CONFIG' : '/opt/ep/configuration/logback_linux.xml',
            'LOG_DIR' : '/tmp/ep/logs',
            'WORK_DIR' : '/tmp/ep/workdir',
            'TMP_DIR' : '/tmp/ep/tmp',
            'LICENSE_LOCATION' : '27000@srvbtces01.btc-es.local',
            'LICENSE_PACKAGES' : 'ET_COMPLETE',
            'REST_PORT' : '8080'
        }
        for prop in props_with_default_values.keys():
            if not prop in os.environ:
                os.environ[prop] = props_with_default_values[prop]
        

    def _start_app_linux(self, license_location, lic, skip_matlab_start, additional_vmargs):
        self._prepare_env()
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
        logger.info(f'Waiting for BTC EmbeddedPlatform {version} to be available:')

        args = [ os.environ['EP_INSTALL_PATH'] + '/ep',
            '-clearPersistedState', '-nosplash', '-console', '-consoleLog',
            '-application', headless_application_id,            
            '-vmargs',
            '-Dep.linux.config=' + os.environ['EP_REGISTRY'],
            '-Dlogback.configurationFile=' + os.environ['EP_LOG_CONFIG'],
            '-Dep.configuration.logpath=' + os.environ['LOG_DIR'],
            '-Dep.runtime.workdir=' + os.environ['WORK_DIR'],
            '-Dbtc.root.temp.dir=' + os.environ['TMP_DIR'],
            '-Dep.licensing.location=' + (license_location or os.environ['LICENSE_LOCATION']),
            '-Dep.licensing.package=' + (lic or os.environ['LICENSE_PACKAGES']),
            '-Dep.rest.port=' + os.environ['REST_PORT'],
            '-Dosgi.configuration.area.default=/tmp/ep/configuration',
            '-Dosgi.instance.area.default=/tmp/ep/workspace',
            '-Dep.runtime.batch=ep',
            '-Dep.runtime.api.port=1109',
            '-Dep.matlab.ip.range=' + matlab_ip ]
        if additional_vmargs:
            logger.debug(f"Applying additional vmargs: {additional_vmargs}")
            args.extend(additional_vmargs)
        
        # start ep process
        self.ep_process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.actively_started = True
        
        # if container has matlab -> assume that this shall be started as well
        if shutil.which('matlab') and not skip_matlab_start:
            import pty
            _, secondary_pty = pty.openpty()
            subprocess.Popen('matlab', stdin=secondary_pty)

        return version

    def _start_app_windows(self, version, install_location, port, license_location, lic, additional_vmargs):
        headless_application_id = 'ep.application.headless' if str(version) < '23.3p0' else 'ep.application.headless.HeadlessApplication'
        # check if we have what we need
        if not (version and install_location): raise BtcApiException("Cannot start BTC EmbeddedPlatform. Arguments version and install_location or install_root directory must be specified or configured in a config file (installationRoot)")
        # all good -> prepare start command for BTC EmbeddedPlatform
        appdata_location = os.environ['APPDATA'].replace('\\', '/') + f"/BTC/ep/{version}/"
        ml_port = 29300 + (port % 100)
        if ml_port == port:
            ml_port -= 100
        if not install_location.endswith('.exe'): install_location = f"{install_location}/rcp/ep.exe"
        if not os.path.isfile(install_location):
            logger.critical(f'''\n\nBTC EmbeddedPlatform Executable (ep.exe) could not be found at the expected location ("{install_location}/rcp/ep.exe").- Please provide the correct version and installation root path:
-> either using the version and install_root parameters of the EPRestApi constructor
-> or via the properties epVersion and installationRoot in the config file
- The installation root directory is expected to contain the sub directory ep{version}.\n\n''')
            raise BtcApiException("EP Executable not found, cannot start BTC EmbeddedPlatform.")
        if not self._is_rest_addon_installed(version):
            logger.critical(f'''\n\nThe REST API AddOn is not installed for BTC EmbeddedPlatform {version}\n\n''')
            raise BtcApiException("Addon not installed.")
        logger.info(f'Waiting for BTC EmbeddedPlatform {version} to be available:')
        args = f'"{install_location}"' + \
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
        if additional_vmargs:
            args += " " + " ".join(additional_vmargs)
        self.ep_process = subprocess.Popen(args, stdout=open(os.devnull, 'wb'), stderr=subprocess.STDOUT)
        self.actively_started = True

    def _does_api_support_signalinfo(self):
        """
        Checks if the current EP version supports querying signal info details.

        This method sends a GET request to the endpoint for signal datatype information.
        It determines support by checking if the response content contains the phrase 'No signal'.

        Returns:
            bool: True if the API call is supported, False otherwise.
        """
        # check if the current EP version supports querying signal info details
        r = requests.get(self._url('signals/UNDEFINED/signal-datatype-information'))
        api_call_supported = (b'No signal' in r.content)
        return api_call_supported

    def _is_ep_process_still_alive(self):
        """
        Check if the external process is still running.

        This method checks if the external process (`ep_process`) is still alive by 
        verifying that the process exists and has not terminated.

        Returns:
            bool: True if the external process is still running, False otherwise.
        """
        return self.ep_process and self.ep_process.poll() is None

    def _is_localhost(self):
        return self._HOST_ in [ 'http://localhost', 'http://127.0.0.1']
    
    def get_errors_from_log(self, start_time=None):
        """
        Extracts error log entries from a log file starting from a given time.
        Args:
            start_time (float, optional): The start time in Unix timestamp format (e.g. time.time() ). 
                                          If provided, only log entries after this time will be considered. 
                                          Defaults to None.
        Returns:
            list: A list of error log entries as strings. Each entry includes the timestamp and the error message.
        """
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
                        # create bools for readability:
                        # - recent = no start_time or timestamp > start_time
                        is_recent = not start_time or timestamp > datetime.fromtimestamp(start_time)
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
                            current_entry += line.strip()
                
                # add last entry (if any)
                if current_entry: log_entries.append(current_entry.strip())

        cleaned_log_entries = []
        for entry in log_entries:
            entry_lines = entry.strip().split("\n")
            # exclude stack trace lines and empty lines
            entry_lines = [line.strip() for line in entry_lines if line.strip() and not line.strip().startswith('at ')]
            cleaned_log_entries.append("\n    ".join(entry_lines))
        return cleaned_log_entries

    def print_log_entries(self):
        for entry in self.get_errors_from_log(self.start_time): logger.error(entry)

    def _init_logging(self):
        logger.setLevel(self.log_level)
        # if logging is not disabled and there are no handlers -> add console handler
        if not self.log_level == LOGGING_DISABLED and not logger.hasHandlers():
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.DEBUG)
            console_handler.setFormatter(logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
            logger.addHandler(console_handler)

    def _watch_profile_migration(self):
        """Can be called (async) to report the status of a profile migration."""
        if platform.system() == 'Windows':
            global the_watch_has_ended
            the_watch_has_ended = False
            try:
                seen_versions = set()
                while True:
                    time.sleep(5)
                    if the_watch_has_ended == True: break
                    processes = get_processes_by_name('ep_profilemigrate')
                    if processes:
                        _, path = processes[0]
                        version = os.path.basename(os.path.dirname(path)).rsplit('.', 1)[0]
                        if version not in seen_versions:
                            seen_versions.add(version)
                            logger.info(f"Migrating profile from {version}...")
                    else: break
            except:
                return
            finally:
                the_watch_has_ended = True

    def _the_watch_has_ended(self, urlappendix):
        """In case a watcher has been watching the status of a
        profile migration, it can stop watching now the process has ended."""
        if urlappendix[:8] == 'profiles':
            global the_watch_has_ended
            the_watch_has_ended = True

    def _set_message_marker(self):
        self.message_marker_date = int((time.time() + 1) * 1000)
        if not self.start_time: self.start_time = time.time()
    
    def _find_next_port(self, initial_port: int, host):
        open_port = initial_port

        try:
            port_found = not is_port_in_use(open_port, host)
        except:
            logger.error(f"Error searching for open ports on {host}. Continuing with default port of {initial_port}.")
            return initial_port
        while open_port <= 65535 and not port_found:
            logger.debug(f"Port {open_port} busy. Trying port {open_port+1}.")
            open_port += 1
            port_found = not is_port_in_use(open_port,host)
        
        if open_port > 65535:
            logger.error(f"All ports greater than {initial_port} searched. No open port found. Please provide the specific port to connect to.")
            raise BtcApiException("No open port found.")
        return open_port

        

class BtcApiException(Exception):
    """Custom exception for BTC EmbeddedPlatform API errors."""
    pass

# if called directly, starts EP based on the global config
if __name__ == '__main__':
    EPRestApi()
