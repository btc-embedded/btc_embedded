ARG EP_VERSION=25.3p0
FROM btces/ep:${EP_VERSION} AS ep

USER root
RUN apt-get update -y && \
    apt-get install -y python3 python3-venv && \
    python3 -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir --disable-pip-version-check btc_embedded;
ENV PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

USER ep

CMD []
