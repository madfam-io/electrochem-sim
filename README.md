# Galvana

> **Phygital Electrochemistry Platform** — real physics + real instruments. Simulate, drive, and calibrate electrochemical systems with enterprise‑grade governance.

**Tagline:** *Physics. Instruments. Decisions.*

---

## At a glance

* **What it is:** A production‑ready platform to model electrochemical processes (batteries, plating/corrosion, fuel cells/electrolyzers), run experiments (CV/CA/CP/EIS), and close the loop with instrument‑in‑the‑loop calibration.
* **Core value:** First‑principles models you can audit + live lab control + enterprise controls (SSO/RBAC, audit logs, APIs).
* **Default cloud stack:** **Vercel** (web) + **Railway** (APIs, workers, data plane). On‑prem K8s supported.

---

## Features

* **Physics engine**: Poisson–Nernst–Planck / Stefan–Maxwell transport; Butler–Volmer (Marcus–Hush optional); DFN/SPM for batteries; optional phase‑field morphology.
* **Phygital integration**: Gamry + BioLogic potentiostats via HAL; 10–50 Hz streaming; mock drivers for CI.
* **Calibration**: EIS fitting (Randles/Wárburg variants); parameter fits (j₀, α, D, ε/τ, film R; DFN subsets).
* **Reproducibility**: Run Records (code hash, mesh, solver opts, firmware); versioned parameter sets; strict SI units.
* **Enterprise**: SSO (OIDC/SAML), RBAC/ABAC, audit logs, REST + WebSocket APIs, Python SDK, export to CSV/Parquet/HDF5.

---

## Monorepo layout

```
/                           # root
├─ apps/
│  └─ web/                 # Next.js (Vercel)
├─ services/
│  ├─ api/                 # FastAPI gateway (REST + WebSocket)
│  ├─ hal/                 # Hardware Abstraction Layer (drivers, mock)
│  └─ orchestrator/        # run registry, scheduling, events
├─ workers/
│  ├─ sim-fenicsx/         # FEniCSx backend (PNP/SM/DFN)
│  └─ sim-moose/           # MOOSE backend (multiphysics, phase‑field)
├─ packages/
│  ├─ sdk-py/              # Python SDK
│  └─ sdk-js/              # JS/TS client
├─ infra/
│  ├─ terraform/           # Railway, object storage, secrets plumbing
│  ├─ helm/                # on‑prem deployment
│  └─ compose/             # local docker compose
├─ examples/
│  ├─ scenarios/           # sample Scenario YAMLs
│  └─ notebooks/           # validation & demos
└─ docs/                   # specs, ADRs, V&V notes
```

---

## Quickstart (local dev)

> **Prereqs:** Docker ≥ 24, Python 3.11+, Node 20+, Git, Make (optional). Linux/macOS recommended.

1. **Clone & env**

```bash
git clone https://github.com/madfam/galvana.git
cd galvana
cp .env.example .env
```

2. **Bring up infra (Postgres/Redis/MinIO)**

```bash
docker compose -f infra/compose/dev.yml up -d postgres redis minio
```

3. **API (FastAPI) — dev run**

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e services/api[dev]
uvicorn services.api.main:app --reload --port 8080
```

4. **Web (Next.js) — dev run**

```bash
cd apps/web
npm i
npm run dev   # http://localhost:3000
```

5. **HAL — mock instrument (optional)**

```bash
python services/hal/mock.py --profile cv-demo
```

6. **Try an example run**

```bash
python examples/run_sim.py \
  --scenario examples/scenarios/ni_plating.yaml \
  --engine fenicsx
```

> Tip: Start both backends’ containers for parity tests (`workers/sim-fenicsx`, `workers/sim-moose`).

---

## Configuration

Global config lives in `config/config.yaml` (overridden by `ENV` vars). The most important keys:

```yaml
engine:
  default: auto          # auto|fenicsx|moose
  allow_override: true
potentiostat:
  default: auto          # auto|gamry|biologic
  allow_override: true
defaults:
  popularity_window_days: 90   # basis for 'most-used' auto selection (per org)
  telemetry_opt_in: false      # in-tenant counts only; no external telemetry
network:
  allowed_origins:
    - https://*.vercel.app
    - https://<primary-domain>
```

**Core ENV variables**

```
# API / Data plane
DATABASE_URL=postgresql://...
REDIS_URL=redis://...
S3_ENDPOINT=https://...
S3_BUCKET=galvana-artifacts
S3_ACCESS_KEY=...
S3_SECRET_KEY=...

# Auth
OIDC_ISSUER_URL=...
OIDC_CLIENT_ID=...
OIDC_CLIENT_SECRET=...

# CORS
ALLOWED_ORIGINS=https://*.vercel.app,https://app.<domain>
```

---

## Deployment

### Default cloud (recommended)

* **Web:** Vercel (per‑env projects). Set secrets via Vercel dashboard. Point to Railway API.
* **APIs/workers/data:** Railway services (api, orchestrator, workers, hal, postgres, redis). Use Terraform in `infra/terraform/` to provision.
* **Streaming:** WebSocket (WSS) from Vercel → Railway; sticky sessions enabled.

### On‑prem / air‑gapped

* Helm charts in `infra/helm/` for K8s; bring your own Postgres/S3/Redis.
* **Remote Connector**: outbound WSS from lab networks → API; no inbound ports.

---

## API & SDKs

* **REST base:** `/api/v1`
* **WebSocket:** `/ws/runs/{run_id}` → channels: `status`, `frames`, `logs`, `events`
* **Python SDK** (`packages/sdk-py`):

```python
from galvana import Client
c = Client(token="...")
run = c.runs.start(scenario_yaml=open("examples/scenarios/ni_plating.yaml").read())
for frame in c.stream(run.id):
    print(frame.time, frame.current)
```

* **JS Client** (`packages/sdk-js`): idiomatic fetch/WebSocket helpers for the web app.

---

## Scenario YAML (example)

```yaml
version: 0.1
name: Ni plating cell — baseline
geometry: {type: 1D, length: 1e-3}
mesh: {elements: 400}
physics:
  transport: nernst_planck
  electroneutral: true
  potential_model: poisson
kinetics:
  model: butler_volmer
  exchange_current_density: 2.0
materials:
  electrolyte:
    species:
      - {name: Ni2+, D: 6.7e-10, z: 2}
      - {name: SO4--, D: 1.07e-9, z: -2}
      - {name: H+, D: 9.3e-9, z: 1}
    activity_model: ideal
boundaries:
  left_electrode: {type: electrode, reaction: "Ni2+ + 2e- -> Ni(s)"}
  right_electrode: {type: counter}
drive:
  mode: potentiostatic
  waveform: {type: step, V: -0.8, t_end: 120.0}
numerics: {time_integrator: BDF, dt_initial: 1e-3}
outputs: {save: [current_density, concentration(Ni2+), potential], cadence: 0.1}
```

---

## Security & compliance

* **AuthN/Z:** OIDC/SAML SSO; RBAC + ABAC (OPA); service accounts for CI.
* **Data:** AES‑256 at rest; TLS 1.3 in transit; frame‑level signing.
* **Audit:** WORM‑capable buckets; SIEM export; hash‑chained run logs.
* **Posture:** SOC 2 readiness; configurable data residency.

---

## Development

* **Code style:** Black/ruff (Python), ESLint/Prettier (JS/TS).
* **Tests:** `pytest` (unit/integration), golden physics tests in `examples/notebooks/`.
* **Makefile:**

```bash
make up        # compose up dev infra
make api       # run FastAPI locally
make web       # run Next.js locally
make test      # run all tests
```

* **Conventional commits**: `feat:`, `fix:`, `perf:`, `chore:`, `docs:` etc.

---

## Validation (V\&V)

* Analytical: Cottrell, Sand’s time, Levich, Randles → regressions in CI.
* Model parity: DFN vs reference parameter sets.
* Phygital: CA/CP/CV/EIS hardware loops with mock + real instruments.

---

## Roadmap (snapshot)

* **M0–M1:** PNP/BV 1D engine spike, HAL skeleton, Scenario Builder alpha.
* **M2:** DFN parity; **Gamry + BioLogic live** with runtime switch; EIS fitting beta.
* **M3 (v1.0 RC):** Concentrated transport, reports, security hardening, on‑prem package.

---

## Contributing

1. Open an issue with context, acceptance criteria, and impact.
2. Create a feature branch, write tests, keep PRs < 400 LOC when possible.
3. Add/update docs and changelog entries.

**Code of Conduct:** Be respectful. No sensitive customer data in issues/PRs.

---

## License & provenance

* **License:** © Innovaciones MADFAM S.A.S. de C.V. — All rights reserved (proprietary). *(Change if OSS decision.)*
* Every run records code commit, solver options, mesh, parameters, instrument firmware, and dataset checksums.

---

## Contact

* **Product/Engineering:** [engineering@galvana.com](mailto:engineering@galvana.com)
* **Security:** [security@galvana.com](mailto:security@galvana.com) (PGP key TBD)
* **Sales/Partnerships:** [hello@galvana.com](mailto:hello@galvana.com)
