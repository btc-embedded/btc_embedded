---
name: btc-ep-test-automation
description: Automate BTC EmbeddedPlatform test workflows by writing Python scripts using the btc_embedded module. Use this skill whenever someone needs to create, fix, or extend a Python script that interacts with the BTC EmbeddedPlatform REST API — including running Requirements-Based Tests (RBT), Back-to-Back Tests (B2B), importing architectures or test cases, generating reports, or saving profiles. Also use this skill when someone asks about btc_embedded API endpoints, request/response formats, or correct usage of EPRestApi.
---

# BTC EmbeddedPlatform Test Automation

This skill helps write Python automation scripts for BTC EmbeddedPlatform CI workflows, including Docker-based orchestration examples for reproducible environments.

## Quick Start Examples

For common workflows, refer to these ready-to-use example scripts in `references/examples/`:

- **`targetlink_rbt_b2b.py`** — TargetLink model with Requirements-Based Testing (TL MIL + SIL) + Back-to-Back tests (TL MIL vs SIL). MATLAB R2024b, EP 25.3p0.
- **`embeddedcoder_rbt_b2b.py`** — EmbeddedCoder-based Simulink model with Requirements-Based Testing (SL MIL + SIL) + Back-to-Back tests (SL MIL vs SIL). MATLAB R2024b, EP 25.3p0.
- **`simulink_rbt_mil_only.py`** — Pure Simulink model (MIL testing only). Loads an existing profile, runs architecture update, then executes RBT. MATLAB R2024b, EP 25.3p0.
- **`ccode_rbt.py`** — C-code project with Requirements-Based Testing (SIL). Uses `CodeModel.xml` for architecture import. EP 25.3p0.
- **`migration_test_mbd.py`** — Single-model migration test for EmbeddedCoder or TargetLink projects using `migration_test()`. Validates SIL behavior is unchanged after a tool version or model change. MATLAB R2024b, EP 25.3p0.
- **`migration_suite_mbd.py`** — Multi-model migration suite using `migration_suite_source()` + `migration_suite_target()`. Two-phase pattern for Docker-based environment testing. MATLAB R2024b, EP 25.3p0.
- **`migration_test_ccode.py`** — Custom migration test for a single C-code component. Defines `migration_source_ccode()` and `migration_target_ccode()` functions, then calls them. EP 25.3p0.
- **`migration_suite_ccode.py`** — Custom migration suite for multiple C-code components. Defines `migration_suite_source_ccode()` and `migration_suite_target_ccode()` which loop over components calling the source/target functions. Two-phase pattern for Docker-based environment testing. EP 25.3p0.

These examples follow all ground rules below and can serve as templates for custom workflows.

## User Interaction Pattern

When assisting with creating a BTC test workflow, follow this interaction style before writing or changing scripts:

1. Start by acknowledging the request and briefly listing the workflow steps you understood.
2. Identify decision points and ask explicit questions before making assumptions.
3. State sensible defaults, but let the user confirm or override them.

Use the following required decision prompts when applicable:

- **Model-based project type is unclear:**
    Ask which model type the user has before choosing endpoints or execution modes:
    - pure Simulink (MIL only)
    - Simulink with EmbeddedCoder code generation
    - Simulink with TargetLink code generation

- **RBT execution for model-based projects:**
    Apply these defaults without asking unless the user asked for a different setup:
    - if both RBT and B2B are requested: run RBT on MIL and SIL before B2B
    - if only RBT is requested for EmbeddedCoder/TargetLink: default to SIL-only
    Ask only when the request is ambiguous.

- **Profile selection (`*.epp` / `*.epx`):**
    Auto-detect profile handling from the workspace:
    - if any `*.epp` or `*.epx` exists -> open an existing profile
    - otherwise -> create a new profile and import architecture based on discovered files (`*.slx` for model-based, `CodeModel.xml` for C-code)
    Do not ask this as a default decision unless multiple candidate profiles exist and a choice is required.

- **RBT project without an existing test project:**
    Auto-discover and import test cases when possible:
    - if a folder contains `*.tc` or `*.tc.json`, import them directly (exclude `*.ui_settings.tc*`)
    Ask only if no test case files can be found.

- **Artifacts and output locations:**
    Propose exporting all standard artifacts into a `results/` folder (`test_report.html`, profile `*.epp`, JUnit XML, logs), then ask:
    - whether they need all artifacts
    - whether any artifact should be written to a different location

- **MATLAB version (model-based projects):**
    If the MATLAB version is already known from user context, set it by default at the start of the script (before any other API calls) without asking again.
    Only ask when Docker signals are detected in the workspace (for example `Dockerfile`, `.dockerignore`, or Docker-oriented scripts) to confirm whether this is a Docker-based workflow; skip MATLAB preference setting for Docker runs.

- **CI environment preparation is unclear:**
    Ask whether the user wants a Docker-based workflow. If yes, pick one of the provided references and adapt it:
    - model-based projects: `references/docker/docker_mbd`
    - C-code projects: `references/docker/docker_ccode`

## Ground Rules

- **Always verify endpoints against `references/openapi-specs/openapi*.json`** before writing or fixing API calls (if EP version is unknown, ask the user). The spec is authoritative; do not rely on memory or the `btc_embedded` source for endpoint paths and field names.
- By default, propose exporting standard artifacts to a `results/` subfolder (`test_report.html`, `test_run.log`, `test_results.xml`, `test_project.epp`), but confirm with the user which artifacts are required and whether any paths should differ.
- All file paths passed to the API must be absolute (`os.path.abspath(...)`).
- **Do not call `ep.delete('profiles')` before `ep.post('profiles')`** — `ep.post('profiles')` automatically discards any currently active profile.
- **When an endpoint requires a scope UID, retrieve it from the scopes list:**
    ```python
    scopes = ep.get('scopes')
    toplevel_scope = scopes[0]          # first item is the toplevel scope
    toplevel_scope_uid = toplevel_scope['uid']
    ```

- **When importing test cases for RBT, include only real test case files and explicitly exclude UI settings companions:**
    ```python
    tc_files = sorted(
        p for p in glob.glob(os.path.join(TESTCASES_DIR, '*.tc.json'))
        if not p.endswith('.ui_settings.tc.json')
    )
    ```
    Include: files ending with `.tc.json`. Exclude: files ending with `.ui_settings.tc.json`. Do not include all `*.json` files — `*.tcm.json` are test macros imported automatically if referenced by test cases.

    When there are `.tc` files instead of `*.tc.json` files, include `*.tc` files and exclude `*.ui_settings.tc` files similarly.

- **Add `message=` to `ep.post`, `ep.put`, and `ep.delete` calls** so runtime logs clearly describe each step. `ep.get(...)` calls do not need messages (they are fast). Message text should state intent, for example:
    ```python
    ep.post('profiles', message='Creating a new profile')
    ep.post('architectures/ccode', payload, message='Importing C-code architecture')
    ep.put('test-cases-rbt', payload, message='Importing test cases')
    ep.post(f'scopes/{scope_uid}/test-execution-rbt', payload, message='Running RBT (SIL)')
    ep.post(f'scopes/{scope_uid}/b2b', payload, message='Running Back-to-Back test (MIL vs SIL)')
    ep.post(f'scopes/{scope_uid}/project-report', message='Creating test report')
    ep.put('profiles', payload, message='Saving profile')
    ```

- **For every B2B workflow, always generate stimuli vectors for full MCDC coverage immediately before B2B execution** so B2B runs with a fully covering data set (existing test cases + generated vectors as needed):
    ```python
    ep.post(
        'coverage-generation',
        {
            'scopeUid': scope_uid,
            'targetDefinitions': [{'label': 'C/DC and MC/DC'}],
        },
        message='Generating vectors for full MCDC coverage before B2B',
    )
    ep.post(
        f'scopes/{scope_uid}/b2b',
        {'refMode': 'SL MIL', 'compMode': 'SIL'},  # or TL MIL for TargetLink
        message='Running Back-to-Back test (MIL vs SIL)',
    )
    ```
    The generation is incremental: it only adds vectors if required to reach the configured threshold (100% by default).

- **When both RBT and B2B are requested for model-based workflows, run RBT on MIL and SIL before B2B.**
    Use SIL-only as default RBT mode for C-code workflows and for model-based workflows where only RBT (no B2B) is requested.

- **Always log achieved coverage for SIL (plain C-code, TargetLink, EmbeddedCoder profiles):**
    - For RBT, after test execution, query the coverage endpoint and use `print_rbt_results(rbt_response, rbt_coverage)`:
        ```python
        rbt_response = ep.post('scopes/{scope_uid}/test-execution-rbt', rbt_exec_payload, ...)
        rbt_coverage = ep.get(f"scopes/{scope_uid}/coverage-results-rbt")
        util.print_rbt_results(rbt_response, rbt_coverage)
        ```
    - For B2B, use `print_b2b_results(b2b_response, b2b_coverage)` after querying the appropriate coverage endpoint.

- **When calling `dump_testresults_junitxml`, provide the correct arguments:**
    - **`rbt_results`** — response from `ep.post('scopes/{uid}/test-execution-rbt')`. Include whenever RBT was executed.
    - **`b2b_result`** — response from `ep.post('scopes/{uid}/b2b')`. Include whenever B2B was executed.
    - **`regression_results`** — response from `ep.post(...)` for regression test execution. Include whenever regression tests were executed.
    - **`test_cases`** — result of `ep.get('test-cases-rbt')`. **Mandatory when `rbt_results` is provided.**
    - **`scopes`** — result of `ep.get('scopes')`. **Mandatory when `rbt_results` is provided.**
    - **`project_name`** — derive as follows (in order):
        1. Strip path and extension from the `*.epp` or `*.epx` file name if one is used.
        2. Otherwise use the model name; if the model file is a wrapper (`Wrapper_*.slx`), strip the `Wrapper_` prefix.
    - **`start_time`** *(optional)* — `datetime.now()` captured at the beginning of the script, used to calculate total workflow duration.
    - **`output_file`** *(optional)* — absolute path for the JUnit XML output file. Defaults to `'test_results.xml'` in the working directory; prefer `os.path.join(RESULTS_DIR, 'test_results.xml')`.

    Only pass the result arguments that match the tests actually run (e.g. `rbt_results` + `b2b_result` for a workflow that runs both RBT and B2B, but not `regression_results`).

---

## Model-Based (EmbeddedCoder / TargetLink) Rules

### MATLAB Version Preference

**Do not set the MATLAB version preference when the script runs inside a Docker image** — Docker images are always prepared with exactly one MATLAB installation, so EP will find it automatically.

For non-Docker workflows, set the MATLAB version preference at the start of the script (before any other API calls) whenever the version is known from context. Ask only if the version is unknown or Docker signals require clarifying execution mode:

```python
ep.put(
    'preferences',
    [
        {'preferenceName': 'GENERAL_MATLAB_VERSION',        'preferenceValue': 'CUSTOM'},
        {'preferenceName': 'GENERAL_MATLAB_CUSTOM_VERSION', 'preferenceValue': 'MATLAB R2024b (64-bit)'},
    ],
    message='Setting MATLAB version preference to R2024b',
)
```

The `GENERAL_MATLAB_CUSTOM_VERSION` value must use the full display string (e.g. `"MATLAB R2026a (64-bit)"`), not the short release tag (`R2026a`).

### EmbeddedCoder Model & Init Script Selection

When building the `architectures/embedded-coder` payload, apply these rules to select model and init script:

- **Model file (`ecModelFile`):** If a `Wrapper_*.slx` file exists in the model directory, always use it — never the bare model file.
- **Init script (`ecInitScript`):** Apply in order:
  1. If a `Wrapper_*.m` file exists → use it.
  2. Else if any `*.m` file whose name contains `start`, `init`, or `load` exists → use it.
  3. Otherwise → omit `ecInitScript` from the payload.

### MIL Execution Config Names

The string for model-level (MIL) execution depends on the model type:

| Model type | `execConfigNames` string |
|---|---|
| EmbeddedCoder (Simulink) | `"SL MIL"` |
| TargetLink | `"TL MIL"` |

### B2B Test Reference / Comparison Ordering

Always use MIL as the reference and SIL as the comparison:

```python
ep.post(f'scopes/{scope_uid}/b2b',
        {'refMode': 'SL MIL', 'compMode': 'SIL'})  # or 'TL MIL' for TargetLink
```

Override only when explicitly asked.

---

## Core API Wrapper

```python
from btc_embedded import EPRestApi
from btc_embedded.util import print_rbt_results, dump_testresults_junitxml

ep = EPRestApi()        # connects to or starts EP; port 8080 on Linux/Docker
ep.get(url)             # GET — returns parsed result
ep.post(url, body)      # POST — transparently polls 202 long-running jobs
ep.put(url, body)       # PUT
ep.delete(url)          # DELETE
ep.close_application()  # always call in a finally block
```

Long-running operations return HTTP 202 with a `jobID`; `ep.post/put` poll until complete and return the final result directly.

## Logging Setup

Set up handlers on the `btc_embedded` logger **before** creating `EPRestApi`. The library only adds its own console handler when none exist — preempt it so output goes to both console and file:

```python
logger = logging.getLogger('btc_embedded')
logger.setLevel(logging.INFO)
fmt = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
for handler in [logging.StreamHandler(),
                logging.FileHandler('results/test_run.log')]:
    handler.setFormatter(fmt)
    logger.addHandler(handler)
```

---

## On-Demand Deep Dives

Use these only when the user specifically needs deeper guidance:

- Docker CI details: [references/docs/docker-ci.md](references/docs/docker-ci.md)
- Migration testing (EC/TL + custom C-code): [references/docs/migration-testing.md](references/docs/migration-testing.md)
- API version-to-version breaking changes: [references/docs/api-changelog.md](references/docs/api-changelog.md)
