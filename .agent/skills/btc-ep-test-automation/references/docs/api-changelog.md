## API Version Changelog

Open this guide when scripts must be adapted for endpoint, payload, or breaking-change differences across BTC EmbeddedPlatform versions.

Version-to-version changes that affect automation scripts. Ignore description-only changes.

### Changes: 24.3p0 → 25.1p0

**NEW OPTIONS**
- `PUT /ep/architectures` — new optional `compiler` query param (string, e.g. `"MinGW64"`, `"MSVC150"`). C-Code only; `406` if named compiler not installed.
- `POST /ep/requirements-import` — new optional `filters` field in body (`FilterOptions`). DOORS_NEXT only.
- `PUT /ep/requirements-update` — new optional `filters` field in body. Omit = use saved filters; `{}` = clear saved filters. DOORS_NEXT only.

---

### Changes: 25.1p0 → 25.2p1

**BREAKING**
- `POST /ep/architectures/simulink` — field `importAsToplevel` (boolean) **renamed** to `importForLiveTesting`. Scripts passing `importAsToplevel=True` must rename the key.

**NEW ENDPOINTS**
- `POST /ep/b2b/deviation/analysis/export-report/{b2b-uid}` — export deviation analysis report to file. Required query param: `file-name` (absolute output path).

**NEW OPTIONS**
- `PUT /ep/architectures` — new optional `reuseExistingCode` (boolean) query param. TargetLink / EmbeddedCoder only. `true` = skip code regeneration.

---

### Changes: 25.2p1 → 25.3p0

**REMOVED**
- `POST /ep/rtt-observers-export` — endpoint removed entirely. No replacement. Scripts using RTT observer export will fail with 404.

**NEW ENDPOINTS**
- `GET /ep/openprofile?path=<abs-path>` — preferred way to open a profile. Avoids URL-encoding issues with `/` in paths. Use instead of `GET /ep/profiles/{profile-path}`.
- `GET /ep/progress/cancel?progress-id=<id>` — cancel a running long-running job.
- `POST /ep/stimuli-vectors/convert-to-testcases` — promote stimuli vectors to RBT test cases. Optional `uids` array; omit to convert all. Long-running (202). Result field: `testCaseUIDs`.

**NEW OPTIONS**
- `GET /ep/progress` response — `cancelled` (boolean) field added to `LongRunningResponse`.

---

### Changes: 25.3p0 → 26.1p0

**BREAKING**
- `POST /ep/architectures/targetlink` — enum value `LIMITED_BLOCKSET` removed from `calibrationHandling`. Replace with `OFF` or `EXPLICIT_PARAMETER`.
- `POST /ep/architectures/targetlink-ev` — same as above.

**REMOVED**
- `POST /ep/architectures/sdf` — SDF architecture import endpoint removed entirely. No replacement.
- `GET /ep/profiles/{profile-path}` — removed. Use `GET /ep/openprofile?path=...` instead (available since 25.3p0).

---

### Changes: 26.1p0 → 26.2p0

No breaking changes, no removed endpoints.

**NEW ENDPOINTS**
- `GET /ep/profiles/global-tolerance-rules` — read global tolerance rules. Required query param: `toleranceUseCase` (`RBT` or `B2B`).
- `PUT /ep/profiles/global-tolerance-rules` — set global tolerance rules. Required query param: `toleranceUseCase` (`RBT` or `B2B`). Body (`GlobalToleranceRulesConfig`):
  - `signalRules` — list of `{regex, abs, rel, absUnit}`. `regex` is a Java regex that must match the entire signal name (`.*Out`, not `*Out`); the first matching rule in the list wins. `absUnit` is `UNIT` or `LSB`. `400` for an invalid regex.
  - `floatingPoint` — default `{abs, rel}` for floating-point signals.
  - `fixedPoint` — default `{abs, rel, absUnit}` for fixed-point signals.
  - Signal rules are checked first, then the data-type default applies.

**NEW OPTIONS**
- `PUT /ep/architectures` — new optional `returnUpdateDiff` (boolean, default `false`) query param. `true` = EP creates an architecture update report (even if report creation is disabled via preference) and returns the changes as `ArchitectureUpdateDiff` (scopes, signals by kind, constants added/removed/changed, property changes, artifact counters).
- `GET /ep/scopes/{scope-uid}/coverage-details-rbt`, `GET /ep/scopes/{scope-uid}/coverage-details-b2b`, `GET /ep/requirements-sources/{requirement-source-uid}/coverage-details-rbt` — `CodeCoverageGoal` response objects gain an optional `metadata` map (goal-type-specific fields keyed by display label). Each `CodeCoverageProperty` gains optional `description`, `origin` and `reason` strings.
