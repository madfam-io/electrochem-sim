# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Galvana is a phygital electrochemistry platform that combines real physics simulation with real instrument control. It's built as a monorepo with multiple services designed for enterprise deployment on Vercel (web) and Railway (APIs/workers).

## Architecture

### Monorepo Structure
- **apps/web**: Next.js frontend (TypeScript) deployed on Vercel
- **services/api**: FastAPI gateway providing REST + WebSocket endpoints
- **services/hal**: Hardware Abstraction Layer for potentiostat integration (Gamry + BioLogic)
- **services/orchestrator**: Run registry, scheduling, and event management
- **workers/sim-fenicsx**: FEniCSx-based simulation backend
- **workers/sim-moose**: MOOSE-based simulation backend
- **packages/sdk-py**: Python SDK for API interaction
- **packages/sdk-js**: JavaScript/TypeScript client library

### Key Technologies
- **Frontend**: Next.js, TypeScript, React
- **Backend**: FastAPI (Python), WebSocket streaming
- **Simulation Engines**: FEniCSx, MOOSE (containerized)
- **Data Layer**: PostgreSQL (metadata), S3-compatible storage (artifacts), Redis (cache)
- **Deployment**: Vercel (frontend), Railway (backend services)

## Development Commands

### Local Development Setup
```bash
# Initial setup
cp .env.example .env
docker compose -f infra/compose/dev.yml up -d postgres redis minio

# API development
python -m venv .venv && source .venv/bin/activate
pip install -e services/api[dev]
uvicorn services.api.main:app --reload --port 8080

# Web development
cd apps/web
npm install
npm run dev

# HAL mock driver (for testing without real instruments)
python services/hal/mock.py --profile cv-demo
```

### Common Development Tasks
```bash
# Run all tests
make test

# Start local infrastructure
make up

# Run API locally
make api

# Run web frontend locally
make web

# Run a simulation example
python examples/run_sim.py --scenario examples/scenarios/ni_plating.yaml --engine fenicsx
```

### Code Quality
- **Python**: Use Black and ruff for formatting/linting
- **TypeScript/JavaScript**: ESLint and Prettier configured
- **Commit Convention**: Use conventional commits (feat:, fix:, perf:, chore:, docs:)

## Key Concepts

### Scenario YAML
Scenarios define simulation parameters in YAML format. Key sections include:
- **geometry**: Define 1D/2D/3D domains
- **physics**: Transport models (Nernst-Planck, Stefan-Maxwell)
- **kinetics**: Butler-Volmer or Marcus-Hush models
- **materials**: Electrolyte and electrode properties
- **boundaries**: Electrode and insulation boundaries
- **drive**: Experiment mode (potentiostatic, galvanostatic)
- **numerics**: Solver settings and tolerances

### Runtime Configuration
The platform supports runtime switching between:
- **Simulation engines**: `engine.default = auto|fenicsx|moose`
- **Potentiostat drivers**: `potentiostat.default = auto|gamry|biologic`
- "auto" selects the most-used option in the organization over the last 90 days

### Data Model
- **Run**: Immutable simulation/experiment execution with full provenance
- **Scenario**: Physics configuration and parameters
- **Dataset**: Time-series frames and field tensors
- **Calibration**: Parameter fitting results
- All runs capture: code hash, solver options, mesh, parameters, timestamps, user info

## API Integration

### REST Endpoints (base: /api/v1)
- `POST /scenarios`: Create/update scenarios
- `POST /runs`: Start simulation or experiment
- `GET /runs/{run_id}`: Get run status and metadata
- `GET /datasets/{run_id}/frames`: Retrieve time-series data

### WebSocket Streaming
- Connect to `/ws/runs/{run_id}` for real-time updates
- Channels: `status`, `frames`, `logs`, `events`
- Frame rate: 10-50 Hz with backpressure handling

### Python SDK Usage
```python
from galvana import Client
c = Client(token="...")
run = c.runs.start(scenario_yaml=open("scenario.yaml").read())
for frame in c.stream(run.id):
    print(frame.time, frame.current)
```

## Testing Strategy
- **Unit tests**: Physics kernels and API handlers
- **Golden tests**: Regression against analytical benchmarks (Cottrell, Sand's time, Levich)
- **Integration tests**: HAL with mock drivers, WebSocket streaming
- **Validation notebooks**: Located in `examples/notebooks/`

## Security Considerations
- Authentication via OIDC/SAML SSO
- RBAC/ABAC authorization with OPA policies
- TLS 1.3 for transport, AES-256 for storage
- Audit logging with immutable records
- Never commit secrets or API keys

## Performance Targets
- Job start latency: P95 ≤ 10s
- EIS fitting: P95 ≤ 30s for Randles-type cells
- 1D DFN simulation: ≤ 30s for 1-hour cycling
- WebSocket streaming: 10-50 Hz with ≤ 200ms latency