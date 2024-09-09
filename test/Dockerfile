# Starting from public image mathworks/matlab
ARG EP_RELEASE=24.2p0
ARG MATLAB_RELEASE=R2023b

# FROM btces/ep-migrator:${EP_RELEASE} as ep-migrator
FROM btces/ep:${EP_RELEASE} as ep
FROM mathworks/matlab:${MATLAB_RELEASE} as matlab

# add arg to make it accessible in this layer
ARG MATLAB_RELEASE

# [ MATLAB 2022b ]
# ARG MATLAB_PRODUCTS="Embedded_Coder AUTOSAR_Blockset MATLAB_Coder Simulink Simulink_Coder Simulink_Coverage Stateflow"
# RUN wget -q https://www.mathworks.com/mpm/glnxa64/mpm \
#    && sudo chmod +x mpm \
#    && sudo ./mpm install \
#       --release ${MATLAB_RELEASE} \
#       --destination /opt/matlab \
#       --products ${MATLAB_PRODUCTS}

# [ MATLAB 2023b ]
USER root
RUN apt update && apt-get install -y wget
RUN wget -q https://www.mathworks.com/mpm/glnxa64/mpm && chmod +x mpm \
    && ./mpm install \
    --release=R2023b  \
    --destination=/opt/matlab  \
    --products Embedded_Coder AUTOSAR_Blockset MATLAB_Coder Simulink Simulink_Coder Simulink_Coverage Stateflow \
    && rm -f mpm /tmp/mathworks_root.log \
    && ln -f -s /opt/matlab/bin/matlab /usr/local/bin/matlab

# License location can alternatively be provided during runtime
# ENV MLM_LICENSE_FILE=27000@matlab.license.server
ARG ML_LIC_PATH=/licenses/matlab.lic
ENV MLM_LICENSE_FILE=${ML_LIC_PATH}

# ----------------------------------------------------------------------------------------
# BTC EmbeddedPlatform specific configurations
# ----------------------------------------------------------------------------------------

# required and variables
ARG EP_RELEASE
ARG EP_INSTALL_PATH=/opt/ep
ENV EP_INSTALL_PATH=${EP_INSTALL_PATH}
ARG EP_WORK_DIR_ROOT=/tmp/ep
ENV EP_WORK_DIR_ROOT=${EP_WORK_DIR_ROOT}
ARG EP_REGISTRY=/opt/Configuration/eplinuxregistry
ENV EP_REGISTRY=${EP_REGISTRY}
ARG EP_LOG_CONFIG=${EP_INSTALL_PATH}/configuration/logback_linux.xml
ENV EP_LOG_CONFIG=${EP_LOG_CONFIG}
ARG REST_PORT
ENV REST_PORT=${REST_PORT:-8080}
EXPOSE ${REST_PORT}

ARG LICENSE_LOCATION=/licenses/btc.lic
ENV LICENSE_LOCATION=${LICENSE_LOCATION}
# ARG LICENSE_LOCATION
# ENV LICENSE_LOCATION=${LICENSE_LOCATION:-27000@srvbtces01.btc-es.local}

ARG LICENSE_PACKAGES
ENV LICENSE_PACKAGES=${LICENSE_PACKAGES:-ET_COMPLETE}
ARG TMP_DIR
ENV TMP_DIR=${TMP_DIR:-${EP_WORK_DIR_ROOT}/tmp}
ARG LOG_DIR
ENV LOG_DIR=${LOG_DIR:-${EP_WORK_DIR_ROOT}/logs}
ARG WORK_DIR
ENV WORK_DIR=${WORK_DIR:-${EP_WORK_DIR_ROOT}/workdir}

# Copy files from public image btces/ep
COPY --chown=1000 --from=ep /opt/jres /opt/jres
COPY --chown=1000 --from=ep /opt/Configuration/eplinuxregistry ${EP_REGISTRY}
COPY --chown=1000 --from=ep /root/.BTC/ep/${EP_RELEASE}/config/compiler_pref/compiler_setup.xml /root/.BTC/ep/${EP_RELEASE}/config/compiler_pref/compiler_setup.xml
COPY --chown=1000 --from=ep /opt/ep ${EP_INSTALL_PATH}

# and some files from the build context
COPY --chown=1000 addMLIntegration.bash /tmp/
RUN sudo chmod +x /tmp/addMLIntegration.bash && sudo /tmp/addMLIntegration.bash && sudo rm /tmp/addMLIntegration.bash

ENV PYTHONUNBUFFERED 1

# ----------------------------------------------------------------------------------------
# Optional settings for BTC
# ----------------------------------------------------------------------------------------
# to be able to migrate old *.epp profiles:
# COPY --chown=1000 --from=ep-migrator /opt/migrator /opt/migrator
# alternative: copy only a single migrator, e.g. if none of the profile are older than 23.3.0
# COPY --chown=1000 --from=ep-migrator /opt/migrator/23.3.0 /opt/migrator/23.3.0

# Logging: activate log level "debug" for problem analysis (default is "warn")
# RUN sed -i '25s/.*/    <root level="debug">/' /opt/ep/configuration/logback_linux.xml

# Example python script to automate BTC tests (for demo purposes)
# COPY --chown=1000 btc_demo_helloworld.py /home/matlab/Documents/
# RUN sudo chmod +x /home/matlab/Documents/btc_demo_helloworld.py

# [ MATLAB 2023b ]
USER matlab

COPY licenses/btc.lic ${LICENSE_LOCATION}
COPY licenses/matlab.lic ${ML_LIC_PATH}

ENTRYPOINT [ ]
CMD [ ]