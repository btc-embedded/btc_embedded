#!/usr/bin/env bash
set -euo pipefail

log_start() {
	printf '[%s] [INFO] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

if [ "$#" -eq 0 ]; then
	echo " "
	echo "BTC EmbeddedPlatform docker image usage:"
	echo " "
	echo ">> docker run [docker options] <image> <path-to-script.py> [script arguments...]"
	echo " "
	echo "- point to the python script you want to execute as the first argument"
	echo "- pass any additional arguments to the script after that"
	echo "- in your python script, make use of the btc_embedded python module to interact with the BTC EP API"
	echo " "
	exit 1
fi

# Start BTC EP service
nohup /opt/ep/ep -clearPersistedState -nosplash -console -consoleLog -application ep.application.headless.HeadlessApplication -vmargs -Dep.licensing.location=$LICENSE_LOCATION -Dep.linux.config=${EP_REGISTRY:-/opt/configuration/eplinuxregistry} -Dep.configuration.logpath=${LOG_DIR:-/tmp/ep/logs} -Dep.licensing.package=${LICENSE_PACKAGES:-ET_COMPLETE} -Dep.runtime.workdir=${WORKDIR:-/tmp/ep/workdir} -Dbtc.root.temp.dir=${TMP_DIR:-/tmp/ep/tmp} -Dosgi.configuration.area.default=/tmp/ep/configuration -Dosgi.instance.area.default=/tmp/ep/workspace -Dep.runtime.batch=ep -Dep.runtime.api.port=1109 -Dep.rest.port=8080 -Dlogback.configurationFile=/opt/ep/configuration/logback_linux.xml -Dep.matlab.ip.range=127.0.0.1 > ep_startup.log 2>&1 &
export BTC_STARTED=1
	
# Start Matlab service
tail -f /dev/null | nohup /opt/matlab/bin/matlab > matlab.log 2>&1 &

ep_available=false
matlab_available=false

echo " "
log_start "Waiting for BTC EmbeddedPlatform and Matlab services to start up..."
while [ "$ep_available" != "true" ] || [ "$matlab_available" != "true" ]; do
	if [ "$ep_available" != "true" ] && nc -z localhost 8080 >/dev/null 2>&1; then
		log_start "BTC EmbeddedPlatform service is available."
		ep_available=true
		rm -f ep_startup.log
	fi

	if [ "$matlab_available" != "true" ] && nc -z localhost 1099 >/dev/null 2>&1; then
		log_start "MATLAB service is available."
		matlab_available=true
	fi

	if [ "$ep_available" != "true" ] || [ "$matlab_available" != "true" ]; then
		sleep 2
	fi
done

SCRIPT="${1}"
shift || true

log_start "BTC EmbeddedPlatform and MATLAB services are up and running."
log_start "- the MATLAB output will be logged to 'matlab.log'"
log_start "- the BTC EmbeddedPlatform output will be logged to 'current.log'"
log_start "- the output of the btc_embedded python module prints to STDOUT by default but can be configured using python logging: https://github.com/btc-embedded/btc_embedded#logging"

# if script doesn't end in .py, just ignore it and exit, otherwise print the "executing script message" below
if [[ "$SCRIPT" == *.py ]]; then
	log_start "Executing the provided script '$SCRIPT'"
	# Pass remaining arguments to the provided script
	python "$SCRIPT" "$@"
else
	tail -f /dev/null
fi