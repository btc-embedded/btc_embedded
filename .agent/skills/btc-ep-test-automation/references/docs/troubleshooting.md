# Troubleshooting

## Common setup / configuration issues on Windows

### 1. ModuleNotFoundError: No module named 'btc_embedded'

The `btc_embedded` module is not installed in the Python environment used to run the script — either it was never installed, or it was installed into a different Python installation.

**Recommended action:**
- Install using the same Python that runs the script: `python -m pip install btc_embedded` (not just `pip install`)
- Alternatively, use Python virtual environments to avoid interpreter mismatches.

### 2. REST API AddOn not installed (`BtcApiException: Addon not installed.`)

The REST API AddOn was not selected during BTC EmbeddedPlatform installation. This is detected via registry keys, for example for EP 25.2p1:
- `Computer\HKEY_LOCAL_MACHINE\SOFTWARE\BTC\EmbeddedPlatform 25.2p1\Addons\REST_Server_EU`
- `Computer\HKEY_LOCAL_MACHINE\SOFTWARE\BTC\EmbeddedPlatform 25.2p1\Addons\REST_Server_BASE_EU`

**Recommended action:**
Uninstall and reinstall BTC EmbeddedPlatform, making sure to select the REST Server AddOn during setup.

### 3. Unexpected version of BTC EmbeddedPlatform is started

- If the env var `BTC_API_CONFIG_FILE` is set, that file controls which EP version is used.
- On first use on Windows, `EPRestApi()` installs a default config at `%PROGRAMDATA%/BTC/ep/btc_config.yml` that sets the active EP version and highest compatible MATLAB version based on the registry.

**Recommended action:**
- Override via constructor: `ep = EPRestApi(version="25.3p0")`
- Or edit `%PROGRAMDATA%/BTC/ep/btc_config.yml` (or whichever file `BTC_API_CONFIG_FILE` points to) to change the default version.

### 4. `tasklist` fails with "Access is denied" for a restricted Windows user (e.g. Jenkins service account)

`EPRestApi()` uses the `tasklist` command internally to clean up its port registry (an optimization used to avoid port collisions when multiple EP instances run on the same machine). On hardened Windows systems, a non-admin service account can be blocked from enumerating processes (via AppLocker/Software Restriction Policies, WMI permissions on `root\cimv2`, or an EDR/AV policy) even without needing admin rights.

**Recommended action:**
- Update to `btc_embedded` >= 26.1.5 — it catches this failure and skips the (non-essential) port registry cleanup with a warning instead of aborting the script.
- Running the Jenkins agent as a non-admin user is fine and does not need to change; a full fix on very old versions would require granting that account rights to enumerate processes, but is no longer necessary once updated.

---

## Common runtime errors for model-based projects

### 1. Architecture Import or Update fails

Architecture Import/Update for EmbeddedCoder or TargetLink models requires:
- The model must compile (Model initialization / Update Diagram: `Ctrl+D` in MATLAB)
- Code generation must succeed
- Generated code must compile

**Recommended action:**
1. Ensure the script initializes the same MATLAB workspace as your manual workflow (load project files, add paths, etc.).
2. Manually load the model in MATLAB and run `Ctrl+D`.
3. If that succeeds, generate code manually.
4. These steps reproduce the issue — which is typically unrelated to EP itself.
