## Docker-Based CI Orchestration

Open this guide when you need Docker-specific setup, constraints, and troubleshooting for model-based or C-code BTC EmbeddedPlatform runs.

Use the Docker references whenever users need reproducible CI environments for BTC EmbeddedPlatform workflows.

### Reference folders

- Model-based example: `references/docker/docker_mbd`
    - Contains `Dockerfile`, `addMLIntegration.bash`, `btc_start.bash`, `docker-build-run.sh`, and `run_tests.py`.
    - Build and run via `docker-build-run.sh`.
- C-code example: `references/docker/docker_ccode`
    - Contains `Dockerfile`, `docker-build-run.sh`, and `run_tests.py`.
    - Build and run via `docker-build-run.sh`.

### Required assistant behavior for Docker topics

- Always ask the user to review the model-based `Dockerfile` before finalizing changes.
- If the user already has a prepared MATLAB image, propose using it as the base image instead of reinstalling MATLAB toolboxes.
- Warn that newer `mathworks/matlab` image releases frequently introduce breaking changes.
    - Be prepared to add missing tools/packages such as `gcc`, `g++`, `python3`, `python3-venv`, `wget`, `nc`, or other Linux utilities.
- For model-based Docker execution, explain that `btc_start.bash` is essential because it starts both services:
    - BTC EmbeddedPlatform service
    - MATLAB service
- If users try to replace the image entrypoint and directly run a Python script, explicitly warn that this can break the workflow because required services may not be started.

