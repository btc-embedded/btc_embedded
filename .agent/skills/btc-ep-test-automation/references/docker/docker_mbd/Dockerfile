# Starting from public image mathworks/matlab & btces/ep
# with default versions defined below (can be overwritten during build)
ARG EP_RELEASE=25.3p0
ARG MATLAB_RELEASE=R2026a

FROM btces/ep:${EP_RELEASE} AS ep
FROM mathworks/matlab:${MATLAB_RELEASE} AS matlab

# Install required matlab products & set up license
ARG MATLAB_RELEASE
ARG MATLAB_PRODUCTS="Embedded_Coder AUTOSAR_Blockset MATLAB_Coder Simulink Simulink_Coder Simulink_Coverage Stateflow"
USER root
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends wget netcat-openbsd gcc g++; \
    wget -q https://www.mathworks.com/mpm/glnxa64/mpm; \
    chmod +x mpm; \
    ./mpm install \
    --release=${MATLAB_RELEASE} \
    --destination=/opt/matlab \
    --products ${MATLAB_PRODUCTS}; \
    ln -sf /opt/matlab/bin/matlab /usr/local/bin/matlab; \
    rm -f mpm /tmp/mathworks_root.log /home/matlab/Documents/MATLAB/startup.m; \
    apt-get purge -y --auto-remove wget; \
    rm -rf /var/lib/apt/lists/*

COPY --chown=matlab --from=ep /opt /opt
COPY --chown=matlab --from=ep /root/.BTC /root/.BTC
COPY --chown=matlab addMLIntegration.bash /tmp/
RUN set -eux; \
    sudo chmod +x /tmp/addMLIntegration.bash; \
    sudo /tmp/addMLIntegration.bash; \
    sudo rm -f /tmp/addMLIntegration.bash; \
    python3 -m venv /opt/venv; \
    /opt/venv/bin/pip install --no-cache-dir --disable-pip-version-check btc_embedded;

COPY btc_start.bash /opt/ep/btc_start.bash

ENV MLM_LICENSE_FILE=27000@matlab.license.server \
    LICENSE_LOCATION=27000@srvbtces01.btc-es.local \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    LOG_DIR=/workdir

# User / Workdir / Entrypoint
USER matlab
WORKDIR /workdir
ENTRYPOINT [ "bash", "/opt/ep/btc_start.bash" ]
CMD [  ]
