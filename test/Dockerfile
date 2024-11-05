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
ARG LICENSE_LOCATION=/licenses/btc.lic
ENV LICENSE_LOCATION=${LICENSE_LOCATION}
# ARG LICENSE_LOCATION
# ENV LICENSE_LOCATION=${LICENSE_LOCATION:-27000@srvbtces01.btc-es.local}

# Copy files from public image btces/ep
COPY --chown=1000 --from=ep /opt /opt
COPY --chown=1000 --from=ep /root/.BTC /root/.BTC

# and some files from the build context
COPY --chown=1000 addMLIntegration.bash /tmp/
RUN sudo chmod +x /tmp/addMLIntegration.bash && sudo /tmp/addMLIntegration.bash && sudo rm /tmp/addMLIntegration.bash

ENV PYTHONUNBUFFERED 1

USER matlab
COPY licenses/btc.lic ${LICENSE_LOCATION}
COPY licenses/matlab.lic ${ML_LIC_PATH}

ENTRYPOINT [ ]
CMD [ ]