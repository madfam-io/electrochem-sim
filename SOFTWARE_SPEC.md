# Galvana — SOFTWARE\_SPEC.md (v0.2)

> **Purpose**
> Specify an enterprise-ready, production-grade **phygital electrochemistry simulator**—real physics + real instruments—built to support R\&D and manufacturing decisions with auditability, security, and scale.

> **Scope (MVP → v1.0)**
> Batteries (DFN/SPM), electrodeposition/plating, basic corrosion; experiment modes (CV, CA/CP, EIS); live instrument streaming; parameter fitting; reproducibility & governance.

---

## 0) Executive Summary

**Outcome:** Users define a scenario (geometry, physics, materials), run a simulation, connect a potentiostat, stream real-time data, and close the loop with calibration—packaged for **Vercel (UI)** + **Railway (APIs/workers/data plane)** by default, with an on-prem option.

**v1.0 Success Metrics**

* Time-to-first-insight: **≤ 5 min** to launch any template; **≤ 60 s** to re-run with new params.
* Physics fidelity: **RMSE ≤ 5–10%** vs bench data on validated templates.
* Performance: **P95 job start ≤ 10 s**; **P95 EIS fit ≤ 30 s** for Randles-type cells.
* Reliability: **≥ 99.5%** control-plane uptime; **every run auditable** (provenance + artifacts).

---

## 1) Definitions & Abbreviations

* **PEP:** Phygital Electrochemistry Platform
* **DFN/SPM:** Doyle–Fuller–Newman / Single-Particle Model
* **PNP/SM:** Poisson–Nernst–Planck / Stefan–Maxwell transport
* **BV/MH:** Butler–Volmer / Marcus–Hush kinetics
* **HAL:** Hardware Abstraction Layer for instruments
* **Run:** Immutable simulation/experiment execution with metadata & artifacts

---

## 2) Personas & Permissions

* **Admin (IT/Sec):** SSO/RBAC, tenant config, audit exports
* **Scientist (R\&D):** Build scenarios, run sims/experiments, fit parameters
* **Lab Tech:** Instrument setup, SOP execution, interlocks
* **Process/Manufacturing Eng.:** Consume models, DoE/sensitivity, generate limits
* **Viewer/Stakeholder:** Read-only dashboards and reports

**RBAC model:** Org → Team → Project scopes; roles {Admin, Maintainer, Editor, Runner, Viewer}; resource tags (e.g., **regulated**, **export-controlled**) drive ABAC policies.

---

## 3) Functional Requirements (RFC-2119)

### F-1 Simulation & Physics

1. MUST support **electroneutral NP** and **Poisson-coupled PNP**; toggle per scenario.
2. MUST support **Stefan–Maxwell** for concentrated electrolytes.
3. MUST provide **Butler–Volmer** kinetics; SHOULD provide **Marcus–Hush** toggle.
4. MUST offer **DFN/SPM** battery templates with importable parameter sets.
5. SHOULD provide **phase-field morphology** (dendrites/corrosion) as optional module.
6. MUST expose **heat coupling** (isothermal MVP; non-isothermal SHOULD be planned).
7. MUST support **pluggable solver backends**: **FEniCSx** and **MOOSE**.

   * **Org default switch:** `engine.default = auto|fenicsx|moose`
   * **auto** = *most-used* backend in the org over a rolling window (configurable; default 90 days)
   * Per-scenario override allowed.

### F-2 Experiment Modes

1. MUST implement **CV, CA, CP, galvanostatic cycling, EIS (small-signal)**.
2. SHOULD implement **GITT** and **OCV** workflows.

### F-3 Hardware-in-the-Loop (Phygital)

1. MUST integrate **Gamry** (ToolkitPy) **and** **BioLogic** (EC-Lab API) at MVP.
2. MUST provide a **runtime vendor switch**: `potentiostat.default = auto|gamry|biologic`

   * **auto** = *most-used* driver in the org over a rolling window (configurable; default 90 days)
   * Per-run override allowed.
3. MUST provide a **HAL** with PyVISA/SCPI + vendor SDK adapters.
4. MUST stream **time-stamped frames** (V, I, T, metadata) at **≥ 10 Hz** with backpressure.
5. MUST support **offline/mock drivers** for CI/testing.

### F-4 Calibration & Fitting

1. MUST fit **j₀, α, D, ε/τ, film R** and DFN parameter subsets (least-squares); SHOULD include Bayesian option.
2. MUST provide **EIS fitting** (Randles, Warburg variants) and small-signal linearization around an operating point.

### F-5 Data, Provenance, Reproducibility

1. MUST capture a **Run Record** (code hash, solver options, mesh, parameters, instrument firmware, timestamp, user, dataset checksums).
2. MUST enforce **SI units** with validation.
3. MUST version **parameter sets** and **scenario specs**.

### F-6 Enterprise Features

1. MUST support **SSO (OIDC/SAML)**, **RBAC/ABAC**, **Audit Logs**, **API keys**, **service accounts**.
2. MUST provide **REST API** and **WebSocket** streams; SHOULD offer **Python SDK**.
3. MUST support **containerized jobs** (Railway services) and **on-prem K8s** packaging.
4. MUST export **CSV/Parquet** (tabular) and **NetCDF/HDF5** (fields).

### F-7 UX & Templates

1. MUST include **Scenario Builder** (form + YAML editor) with validation.
2. MUST ship templates: **DFN Cell**, **Ni Plating Cell**, **Corrosion Coupon**, **RDE Levich**.
3. SHOULD provide **notebook examples** and **one-pager PDF** per run.

### F-8 Governance & Compliance

1. MUST offer **data retention policies** (project-level TTL) and **legal hold**.
2. SHOULD support **e-signature** on SOP templates (regulated labs).

---

## 4) Non-Functional Requirements

* **Security:** TLS 1.3; FIPS-capable crypto; secrets in KMS/Vault; least-privilege; signed containers; SBOM.
* **Reliability:** 99.5% control-plane SLO; zero data loss on committed frames; retry/backfill for streams.
* **Performance:** Targets in §0; **>100k time steps/hr** for 1D DFN on standard HW; **near-linear scaling** across cores.
* **Observability:** OpenTelemetry traces; Prometheus metrics; structured logs; append-only audits.
* **Accessibility:** WCAG 2.1 AA; keyboard-first flows.
* **i18n:** EN/ES UI; SI units default; locale-aware formatting.
* **Maintainability:** ≥80% unit coverage core libs; golden physics tests; mock-instrument integration tests.

---

## 5) System Architecture (logical)

**Front-end (Vercel)**

* Next.js (TypeScript) deployed on **Vercel**; edge caching/CDN.
* Auth via OIDC; tokens stored securely; calls API Gateway.
* Live **WebSocket** client connects to Railway API (WSS).

**API Gateway & Control Plane (Railway)**

* FastAPI/Node REST + WebSocket endpoints; CORS allowlist for Vercel domains.
* AuthZ via RBAC/ABAC (OPA). Rate limiting & request signing for instrument posts.

**Orchestrator (Railway)**

* Queue (NATS or Redis Streams) for run events.
* Scheduler launches worker containers (one per backend/type).
* Run registry & artifact indexing.

**Simulation Workers (Railway; on-prem K8s optional)**

* Backend containers for **FEniCSx/Firedrake** and **MOOSE**; PETSc/SUNDIALS.
* Python bridge: scenario YAML → FE problem assembly; Cantera/PyBaMM interop.
* Backend selection via scenario or org default (`engine.default`).

**Instrument Gateway / HAL (Railway or Remote Connector)**

* Vendor adapters (Gamry, BioLogic), PyVISA/SCPI, normalizer, safety interlocks.
* **Remote Connector mode:** outbound **WSS** from lab → Gateway (no inbound ports).

**Data Plane**

* **OLTP:** PostgreSQL (Railway managed) for runs/metadata (Timescale optional).
* **Artifacts:** S3-compatible object storage (Cloudflare R2 / AWS S3).
* **Cache:** Redis for sessions, cursors, short-lived state.
* **Artifacts & SBOMs:** versioned, immutable; signed URLs for access.

**Security Services**

* OIDC (Okta/Entra/Keycloak), Vault/KMS (cloud KMS if available), OPA for policy.

**Observability**

* Prometheus/Grafana or Grafana Cloud; Loki logs; OpenTelemetry collector sidecar.

---

## 6) Data Model (key entities)

* **Organization, User, Team, Policy**
* **Project** → **Scenario** → **ParameterSet** → **Run** (*SimulationRun | ExperimentRun*)
* **Instrument** (capabilities, firmware, driver) → **Connector**
* **Dataset** (time-series frames, field tensors) → **Artifact** (HDF5/NetCDF/CSV/Plot)
* **Calibration** (method, priors, posterior)
* **AuditLog** (actor, action, resource, before/after, signature)

### 6.1 Scenario YAML (v0.1)

```yaml
version: 0.1
name: Ni plating cell — baseline
geometry:
  type: 1D   # 1D|2D|3D
  length: 1e-3  # m
mesh:
  elements: 400
physics:
  transport: nernst_planck     # nernst_planck|stefan_maxwell
  electroneutral: true
  potential_model: poisson      # poisson|none
  heat: false
kinetics:
  model: butler_volmer
  exchange_current_density: 2.0   # A/m^2
  alpha_a: 0.5
  alpha_c: 0.5
  film_resistance: 0.0
materials:
  electrolyte:
    species:
      - {name: Ni2+, D: 6.7e-10, z: 2}
      - {name: SO4--, D: 1.07e-9, z: -2}
      - {name: H+, D: 9.3e-9, z: 1}
    activity_model: ideal         # ideal|debye_huckel|pitzer
    conductivity: 8.5
  electrode:
    porosity: 0.5
    tortuosity: 2.0
boundaries:
  left_electrode:
    type: electrode
    reaction: Ni2+ + 2e- -> Ni(s)
  right_electrode:
    type: counter
  walls:
    type: insulation
drive:
  mode: potentiostatic            # potentiostatic|galvanostatic
  waveform:
    type: step
    V: -0.8
    t_end: 120.0
numerics:
  time_integrator: BDF
  dt_initial: 1e-3
  dt_max: 0.5
  newton_tol: 1e-8
  linear_solver: gmres
outputs:
  save:
    - current_density
    - concentration(Ni2+)
    - potential
  cadence: 0.1
```

### 6.2 Global Configuration (defaults & switches)

```yaml
engine:
  default: auto          # auto|fenicsx|moose
  allow_override: true
potentiostat:
  default: auto          # auto|gamry|biologic
  allow_override: true
defaults:
  popularity_window_days: 90   # basis for 'most-used' auto selection (per org)
  telemetry_opt_in: false      # counts computed in-tenant; no external telemetry by default
network:
  allowed_origins:
    - https://*.vercel.app
    - https://<primary-domain>
```

---

## 7) Public API (v1)

**Auth:** OAuth2/OIDC; bearer tokens; scopes (runs\:write, datasets\:read, instruments\:control)

### 7.1 REST

* `POST /api/v1/scenarios` → create/update (schema-validated) → `scenario_id`
* `POST /api/v1/runs` → start: `{scenario_id|scenario_yaml, mode: simulation|experiment, instrument_id?, tags[]}` → `run_id`
* `GET /api/v1/runs/{run_id}` → status/metadata
* `GET /api/v1/runs/{run_id}/artifacts` → signed URLs
* `GET /api/v1/datasets/{run_id}/frames?from=...` → paged time-series
* `POST /api/v1/calibrations` → start fit job for a run or dataset
* `GET /api/v1/instruments` → discover/list
* `POST /api/v1/instruments/{id}/program` → upload waveform/SOP
* `POST /api/v1/instruments/{id}/start|stop`

### 7.2 WebSocket

* `/ws/runs/{run_id}` → multiplexed channels: `status`, `frames`, `logs`, `events`

### 7.3 Python SDK (sketch)

```python
from galvana import Client
c = Client(token="...")
run = c.runs.start(scenario_yaml=open("cell.yaml").read())
for frame in c.stream(run.id):
    print(frame.time, frame.current)
```

---

## 8) Physics & Numerics (implementation notes)

* **Discretization:** FEM (CG; DG where needed), adaptive mesh in 1D/2D; implicit time stepping (BDF 1–2).
* **Solvers:** Newton–Krylov with PETSc (GMRES/FGMRES + AMG); SUNDIALS IDA for DAEs.
* **Stability:** Damped Newton; line search; residual/step safeguards; consistent ICs.
* **Units:** Strong typing; fail-fast on dimension errors.
* **Validation:** Golden tests (Cottrell, Sand’s time, Levich, Randles EIS); DFN parity vs reference sets; plating thickness vs charge (planar).

---

## 9) UI/UX Requirements

* **Scenario Builder:** form + YAML editor; inline schema help; unit chips; error badges.
* **Run Console:** live charts (I–t, V–t, state vars), status, logs, artifacts; pause/resume (simulation only).
* **Instrument Panel:** connect/test, SOP templates (CV, CA, CP, EIS), interlocks, live telemetry.
* **Calibration Workbench:** pick dataset, choose model (Randles/DFN subset), fit, residuals, posteriors.
* **Library:** searchable templates; pin favorites; provenance badges.
* **Reports:** one-click PDF with scenario, params, plots, error bars, audit footer.

---

## 10) Security & Compliance

* **AuthN/Z:** OIDC/SAML SSO; RBAC + ABAC (OPA); service accounts for CI.
* **Data:** AES-256 at rest; TLS 1.3 in transit; frame-level signing for streams.
* **Secrets:** Vault/KMS; short-lived tokens for instruments; optional mTLS for on-prem HAL.
* **Audit:** Immutable logs (WORM-capable bucket); SIEM export; hash-chained run logs.
* **Compliance posture:** SOC 2 readiness checklist; configurable data residency; deletion SLA ≤ 30 days.

---

## 11) Deployment & Ops

**Environments:** Dev, Staging, Prod; optional Air-gapped Package (on-prem registry + offline docs)

**Default cloud stack**

* **Frontend:** Vercel projects (per environment); environment-scoped secrets.
* **Backend/services:** Railway environments (API, orchestrator, workers, HAL, Redis, Postgres).
* **Networking:** WSS from Vercel → Railway for run streams; CORS allowlist; rate-limit + backpressure.

**CI/CD:** GitHub Actions → Vercel (UI) + Railway (API/workers); SBOM; container scanning; IaC (Terraform) for Railway + object storage.

**Observability:** Grafana Cloud dashboards (API latency, queue depth, run throughput, solver timings); Loki logs; OTel traces; alerting via PagerDuty.

**Backups/DR:** Nightly Postgres snapshots + object storage versioning; **RPO ≤ 24h**; **RTO ≤ 4h**; restore runbooks.

**On-prem option:** Helm charts for K8s; bring-your-own Postgres/S3; Remote Connector for labs behind firewalls.

---

## 12) Performance & Capacity Targets (v1)

* **Single run:** 1D DFN ≤ **30 s** for 1-hour equivalent cycling (simulated) on a 16-core VM.
* **Streaming:** Sustain **10–50 Hz** frames with **≤ 200 ms** P95 end-to-end latency.
* **Scale:** **50 concurrent runs**; worker autoscaling on queue depth; queue latency P95 **≤ 5 s**.

---

## 13) Integrations (initial matrix)

* **Potentiostats:** **Gamry** (ToolkitPy) **and** **BioLogic** (EC-Lab API) at MVP; runtime-selectable driver; roadmap: Metrohm Autolab.
* **OPC UA:** Connector for plant-level integration (TwinBridge).
* **Data Science:** Python SDK; Jupyter; export Parquet/CSV/HDF5.
* **Identity:** Okta, Entra ID, Keycloak.

---

## 14) Packaging & Licensing

* **Editions:** Lab, Team, Enterprise (feature flags via Unleash).
* **Licensing:** Named user + compute hours + connector packs; online license check with offline grace.
* **Third-party:** OSS notices; dual-licensing for proprietary kernels if needed.

---

## 15) Testing Strategy

* **Unit tests:** physics kernels, schema validators, API handlers.
* **Golden tests:** regression against analytical benchmarks; locked tolerances.
* **Integration tests:** HAL with mock drivers; stream backpressure; resume after network blips.
* **Load tests:** k6/Gatling for APIs; synthetic frame generators (10–50 Hz).
* **Security tests:** SAST, DAST, dependency scanning; secrets scanning; OPA policy tests.

---

## 16) Risks & Mitigations

* **Numerical stiffness:** Start 1D; robust preconditioners; safe defaults + diagnostics.
* **Parameter uncertainty:** Sensitivity + priors; calibration workflows; dataset QC.
* **Vendor API volatility:** Abstract via HAL; mock drivers; pinned SDK versions.
* **Scope creep:** Template-first roadmap; publish out-of-scope list for v1.1+.
* **Perf regressions:** CI golden perf suite; perf budgets per PR.

---

## 17) Roadmap Snapshot

* **M0–M1:** Core engine spike (PNP/BV 1D), HAL skeleton, Scenario Builder alpha.
* **M2:** DFN template parity; **Gamry + BioLogic live** with runtime switch; EIS fitting beta.
* **M3 (v1.0 RC):** Concentrated transport option, reports, security hardening, on-prem package.

---

## 18) Out of Scope (until v1.1+)

* Full 3D moving-mesh deposition; large-deformation mechanics coupling.
* AI surrogate auto-training pipelines (manual only in v1).
* Multi-instrument synchronization (>1 device per run).

---

## 19) Open Questions

1. **Regions/data residency:** choose **Vercel + Railway** regions for pilot customers (latency/compliance).
2. **Default ‘auto’ window:** confirm rolling window (90 days?) for most-used backend/driver per org.
3. Any labs require **offline/air-gapped** connector constraints beyond Remote Connector mode?
4. Preferred **IdP** for SSO in pilots (Okta/Entra/Keycloak).
5. DFN parameter sets to ship at v1 (chemistries list).

---

## 20) Appendices

### A) Error Codes (excerpt)

* `E-SIM-INIT-001`: Invalid scenario schema
* `E-SIM-SOLVE-010`: Newton convergence failure
* `E-HAL-IO-020`: Instrument I/O timeout
* `E-SEC-AUTH-040`: Token expired

### B) Event Schema (Run Event)

```json
{
  "type": "run.status",
  "run_id": "r_123",
  "status": "running|failed|succeeded",
  "timestamp": "2025-08-26T12:34:56Z",
  "meta": {"scenario_id": "sc_456", "commit": "abc123"}
}
```

### C) Report Footer (audit)

> Run **r\_123** • Scenario **sc\_456** • Commit **abc123** • Solver **BDF(2)** • Mesh **400 el** • Generated **2025-08-26** • Signed by **Galvana**
