## Migration Testing (Structural Regression)

Open this guide when a request involves migration source/target workflows, cross-version regression strategy, or custom C-code migration suite implementation details.

**Purpose**: Verify that software behavior is preserved when switching between tool versions, compiler versions, MATLAB releases, or refactored model variants. A migration test records reference behavior in the original environment (source) and checks it is reproduced in the new environment (target).

**Supported project types**: EmbeddedCoder (EC) and TargetLink (TL) Simulink-based projects — both require MATLAB/Simulink.

**Unsupported project types**:
- **C-code projects** — the built-in migration functions require a Simulink model. Use a custom implementation (see below).
- **Pure MIL-only projects** — migration testing requires code generation (SIL capability). Inform the user and suggest verifying whether the project has EC or TL architecture that can produce SIL code.

### Built-in module (EC / TL only)

```python
from btc_embedded import migration_test, migration_source, migration_target
from btc_embedded import migration_suite_source, migration_suite_target
```

**Model dict** — used by all migration functions:

```python
model = {
    'model':          os.path.abspath('models/MyModel.slx'),      # mandatory
    'script':         os.path.abspath('models/init.m'),            # optional MATLAB init script
    'scopeName':      'MyTopLevelScope',                            # optional; uses first scope if omitted
    'environmentXml': os.path.abspath('models/Environment.xml'),   # optional; TargetLink only
}
```

#### Single-model migration test

```python
result = migration_test(
    old_model=old_model,    # dict with at least 'model' key
    old_matlab= '2024b',    # MATLAB version for old environment
    new_model=new_model,    # same or refactored model dict; defaults to old_model if omitted
    new_matlab='2025b',     # MATLAB version for new environment; defaults to old_matlab if omitted
    test_mil=False,         # True adds MIL–MIL regression on top of SIL–SIL
)
```

What `migration_test()` does internally:
1. **Source**: start EP → detect codegen type (EC/TL) → import model → generate coverage vectors → reference simulation (SIL, optionally MIL) → store execution records in `old-sil`/`old-mil` folders inside the `.epp` profile → save `.epp`
2. If the same model is used for source and target: clears Simulink cache files between phases
3. **Target**: load source `.epp` → update architecture → apply tolerances → regression test (new-SIL vs old-SIL, optionally new-MIL vs old-MIL) → create report → save `.epp`

The test report is saved to `results/<model_name>-migration-test.html`.

#### Multi-model migration suite (two-phase / Docker)

Two separate scripts designed to run in different environments while sharing a `results/` directory:

**`migration_source.py`** (runs in the OLD environment):

```python
from btc_embedded import migration_suite_source
import os

MODELS = [
    {'model': os.path.abspath('models/ModelA.slx'), 'script': os.path.abspath('models/initA.m')},
    {'model': os.path.abspath('models/ModelB.slx')},
]

migration_suite_source(
    MODELS,
    matlab_version='2024b',
    # toolchain_script=os.path.abspath('init_toolchain.m'),  # optional MATLAB toolchain init script
    # test_mil=True,    # also record MIL reference (default: False)
    # reuse_code=True,  # skip code regeneration if already generated (default: False)
)
```

**`migration_target.py`** (runs in the NEW environment):

```python
from btc_embedded import migration_suite_target
import os

MODELS = [  # must match source exactly
    {'model': os.path.abspath('models/ModelA.slx'), 'script': os.path.abspath('models/initA.m')},
    {'model': os.path.abspath('models/ModelB.slx')},
]

migration_suite_target(
    MODELS,
    matlab_version='2025b',
    # toolchain_script=os.path.abspath('init_toolchain.m'),
    # test_mil=True,                   # must match source setting
    # reuse_code=True,
    # accept_interface_changes=False,  # set True to continue when model interface changed
)
```

Both scripts must run from the same working directory so they share `results/`. The live overview report at `results/BTCMigrationTestSuite.html` is updated as each model step completes.

Docker orchestration pattern (model-based: use `btc_start.bash` as entrypoint):

```bash
EP_VERSION_OLD=25.3p0
MATLAB_VERSION_OLD=2024b
MATLAB_VERSION_NEW=2025b

docker build --build-arg EP_RELEASE=${EP_VERSION} --build-arg MATLAB_VERSION=${MATLAB_VERSION_OLD} --tag ep:old -f Dockerfile_old .
docker build --build-arg EP_RELEASE=${EP_VERSION} --build-arg MATLAB_VERSION=${MATLAB_VERSION_NEW} --tag ep:new -f Dockerfile_new .

docker run --rm --volume "$(pwd):/workdir" --workdir "/workdir" \
    ep:old migration_source.py

docker run --rm --volume "$(pwd):/workdir" --workdir "/workdir" \
    ep:new migration_target.py
```

### Custom migration implementation (C-code)

No built-in `migration_test()` supports C-code. Structure the implementation as discrete functions matching the MBD pattern:

- `migration_source_ccode(component, source_epp, ep=None)` — source phase; returns source_epp path
- `migration_target_ccode(component, source_epp, target_epp, ep=None)` — target phase; returns regression result dict
- For multiple components: `migration_suite_source_ccode(components)` and `migration_suite_target_ccode(components)` loop over the component list in one shared EP session (see `migration_suite_ccode.py`)

**Component dict**:

```python
component = {
    'codeModelXml': os.path.abspath('test/CodeModel.xml'),  # mandatory
    'name': 'MyComponent',  # optional; derived from codeModelXml filename if omitted
}
```

**`ep` parameter**: pass an existing `EPRestApi` instance when calling from a suite (shared session); omit to let each function create and close its own instance.

**Source phase** — import architecture, generate vectors, record reference behavior:

```python
ep.post('profiles', message='Creating source profile')
ep.set_compiler()
ep.post('architectures/ccode', {'modelFile': os.path.abspath('test/CodeModel.xml')},
        message='Importing C-code architecture')
scope_uid = ep.get('scopes')[0]['uid']

ep.post('coverage-generation',
        {'scopeUid': scope_uid, 'pllString': 'STM',
         'engineSettings': {'timeoutSeconds': 300}},
        message='Generating coverage vectors')
ep.post(f'scopes/{scope_uid}/testcase-simulation',
        {'execConfigNames': ['SIL']},
        message='Reference simulation (SIL)')

# Move SIL execution records into a named folder
er_records = ep.get('execution-records')
old_sil_folder = ep.post('folders',
                         {'folderKind': 'EXECUTION_RECORD', 'folderName': 'old-sil'},
                         message='Creating old-sil folder')
sil_er_uids = [er['uid'] for er in er_records if er['executionConfig'] == 'SIL']
ep.put(f"folders/{old_sil_folder['uid']}/execution-records",
       {'UIDs': sil_er_uids}, message='Moving SIL records to old-sil folder')

ep.put('profiles', {'path': SOURCE_EPP}, message='Saving source profile')
```

**Target phase** — load source profile, update architecture, regression test:

```python
# Load source .epp — execution records are already inside it
ep.get(f'openprofile?path={SOURCE_EPP}', message='Loading source profile')
ep.set_compiler()

# Update C-code architecture (verify exact endpoint against openapi spec)
ep.put('architectures', message='Updating C-code architecture')

scope_uid = ep.get('scopes')[0]['uid']

# Create new-sil folder and run regression test against old-sil
new_sil_folder = ep.post('folders',
                         {'folderKind': 'EXECUTION_RECORD', 'folderName': 'new-sil'},
                         message='Creating new-sil folder')
er_folders = [f for f in ep.get('folders?kind=EXECUTION_RECORD') if not f['isDefault']]
old_sil_folder = next(f for f in er_folders if f['name'] == 'old-sil')
regression_result = ep.post(
    f"folders/{old_sil_folder['uid']}/regression-tests",
    {'compMode': 'SIL', 'compFolderUID': new_sil_folder['uid']},
    message='Regression Test SIL vs. SIL')
logger.info(f"Regression result: {regression_result['verdictStatus']}")

# Create and export report
report = ep.post(f'scopes/{scope_uid}/project-report',
                 message='Creating test report')
ep.post(f"reports/{report['uid']}",
        {'exportPath': RESULTS_DIR, 'newName': 'migration-test'},
        message='Exporting report')

ep.put('profiles', {'path': TARGET_EPP}, message='Saving target profile')
```

#### Reporting for C-code migration suites

When generating a C-code migration **suite** (not a single-component test), include a live HTML report updated by each migration step — mirroring the `initialize_report` / `update_report` / `update_report_running` pattern from `migration.py`.

**Additional imports and module-level global:**

```python
import json
from datetime import datetime
from btc_embedded.reporting import create_report_from_json

# Global variable to store the report path for update_report calls; set by the source phase and used by both source and target phases
report_json = None  # set by _initialize_report (source) or migration_suite_target_ccode (target)
```

**Three helper functions — define once at module level:**

```python
def _get_comp_name(component):
    return component.get('name', os.path.splitext(os.path.basename(component['codeModelXml']))[0])

def _initialize_report(components, results_dir):
    global report_json
    report_json = os.path.join(results_dir, 'report.json')
    report_data = {
        'title': 'BTC Migration Test Suite (C-Code)', 'filename': 'BTCMigrationTestSuite.html',
        'results': {}, 'additionalStats': {},
    }
    for component in components:
        comp_name = _get_comp_name(component)
        report_data['results'][comp_name] = {'projectName': comp_name, 'status': 'SCHEDULED'}
    with open(report_json, 'w') as f:
        json.dump(report_data, f, indent=4)
    create_report_from_json(json_path=report_json)

def _update_report(project_item=None, additional_stats=None):
    if not report_json or not os.path.isfile(report_json):
        return  # no-op when called standalone (report_json not set)
    with open(report_json, 'r') as f:
        report_data = json.load(f)
    if project_item:
        comp_name = project_item['projectName']
        if comp_name in report_data['results']:
            report_data['results'][comp_name].update(project_item)
        else:
            report_data['results'][comp_name] = project_item
    if additional_stats:
        report_data.setdefault('additionalStats', {}).update(additional_stats)
    with open(report_json, 'w') as f:
        json.dump(report_data, f, indent=4)
    create_report_from_json(json_path=report_json)

def _update_report_running(comp_name, step_name):
    _update_report({'projectName': comp_name, 'status': 'RUNNING', 'info': f'{step_name}...'})
```

**`migration_source_ccode` (suite version)** — add `comp_name`, `start_time`, `_update_report_running` calls at each step, and `_update_report` at completion and in `except`:

```python
def migration_source_ccode(component, source_epp, ep=None):
    comp_name = _get_comp_name(component)
    start_time = datetime.now()
    owns_ep = ep is None
    if owns_ep:
        ep = EPRestApi()
        ep.set_compiler()
    try:
        _update_report_running(comp_name, 'Importing C-code architecture')
        # ep.post('profiles', ...)
        # ep.post('architectures/ccode', ...)
        # ...

        _update_report_running(comp_name, 'Generating coverage vectors')
        # ep.post('coverage-generation', ...)

        _update_report_running(comp_name, 'Reference simulation (SIL)')
        # ep.post(f'scopes/{scope_uid}/testcase-simulation', ...)

        # ... move SIL ERs to old-sil folder, save profile ...

        duration = (datetime.now() - start_time).seconds
        # status: 'RUNNING' — not 'COMPLETED'; target phase is still pending
        _update_report({'projectName': comp_name, 'status': 'RUNNING',
                        'info': 'Migration Source step completed.', 'duration': duration})
    except Exception as e:
        _update_report({'projectName': comp_name, 'status': 'ERROR',
                        'info': str(e).split('\n')[0], 'duration': (datetime.now() - start_time).seconds})
        raise
    finally:
        if owns_ep:
            ep.close_application()
    return source_epp
```

**`migration_target_ccode` (suite version)** — add `_update_report_running` at each step, accumulate total duration from the JSON, and set `COMPLETED` with the final result:

```python
def migration_target_ccode(component, source_epp, target_epp, ep=None):
    comp_name = _get_comp_name(component)
    start_time = datetime.now()
    results_dir = os.path.dirname(target_epp)
    owns_ep = ep is None
    if owns_ep:
        ep = EPRestApi()
        ep.set_compiler()
    try:
        _update_report_running(comp_name, 'Loading source profile')
        # ... ep.get('openprofile', ...) ...

        _update_report_running(comp_name, 'Updating C-code architecture')
        # ... ep.put('architectures/ccode', ...), ep.put('architectures') ...

        _update_report_running(comp_name, 'Regression Test SIL vs. SIL')
        # ... create folders, run regression test, get verdict ...

        _update_report_running(comp_name, 'Creating report')
        # ... create and export report, save profile ...

        # Accumulate total duration (source duration was stored by migration_source_ccode)
        src_duration = 0
        if report_json and os.path.isfile(report_json):
            with open(report_json, 'r') as f:
                rd = json.load(f)
            src_duration = rd.get('results', {}).get(comp_name, {}).get('duration', 0)
        _update_report({
            'projectName': comp_name, 'status': 'COMPLETED', 'testResult': verdict,
            'reportPath': f'{comp_name}-migration-test.html',
            'eppPath': os.path.basename(target_epp),
            'duration': (datetime.now() - start_time).seconds + src_duration, 'info': '',
        })
    except Exception as e:
        _update_report({'projectName': comp_name, 'status': 'ERROR',
                        'info': str(e).split('\n')[0], 'duration': (datetime.now() - start_time).seconds})
        raise
    finally:
        if owns_ep:
            ep.close_application()
    return regression_result
```

**`migration_suite_source_ccode`** — call `_initialize_report` before the component loop:

```python
def migration_suite_source_ccode(components, results_dir=None, ep=None):
    ...
    _initialize_report(components, results_dir)  # creates results/BTCMigrationTestSuite.html, marks all SCHEDULED
    # ... EP session + loop: migration_source_ccode(component, source_epp, ep=ep) per component
```

**`migration_suite_target_ccode`** — set `report_json` at the start so `_update_report` works when running as a separate process:

```python
def migration_suite_target_ccode(components, results_dir=None, ep=None):
    global report_json
    ...
    report_json = os.path.join(results_dir, 'report.json')  # resolve path even in a new process
    # ... EP session + loop: migration_target_ccode(component, source_epp, target_epp, ep=ep) per component
```

The live overview report is written to `results/BTCMigrationTestSuite.html` and re-rendered after each component step. See `migration_suite_ccode.py` for the complete implementation.

---

### Correct API payloads for custom implementations

| Operation | Call | Payload |
|---|---|---|
| Create ER folder | `ep.post('folders', ...)` | `{'folderKind': 'EXECUTION_RECORD', 'folderName': 'old-sil'}` |
| Move ERs to folder | `ep.put(f'folders/{uid}/execution-records', ...)` | `{'UIDs': [er_uid, ...]}` |
| Import ERs from files | `ep.post('execution-records', ...)` | `{'paths': [...], 'kind': 'SIL', 'folderUID': folder_uid}` |
| Regression test | `ep.post(f'folders/{old_uid}/regression-tests', ...)` | `{'compMode': 'SIL', 'compFolderUID': new_uid}` |
| Create report (with template) | `ep.post(f'scopes/{scope_uid}/project-report?template-name={tmpl}')` | — |
| Export report | `ep.post(f'reports/{report_uid}', ...)` | `{'exportPath': results_dir, 'newName': 'name'}` |

**Report template names** (model-based migration only):

| Template | When to use |
|---|---|
| `regression-test-ec` | EmbeddedCoder with MIL (SL MIL) |
| `regression-test-tl` | TargetLink with MIL (TL MIL) |
| `regression-test-sil-only` | SIL-only (no MIL) |

---

