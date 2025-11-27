# Galvana MVP - Quick Start Guide

## 🚀 Get Started in 5 Minutes

### Prerequisites
- Python 3.11+
- Node.js 18+
- Docker & Docker Compose
- Git

### 1. Clone & Setup

```bash
git clone https://github.com/yourusername/galvana.git
cd galvana
cp .env.example .env
```

### 2. Install Dependencies

```bash
# Python dependencies (using pip for quick start)
pip install -r requirements.txt

# Frontend dependencies
cd apps/web && npm install && cd ../..
```

### 3. Start Infrastructure

```bash
# Start PostgreSQL, Redis, and MinIO
make up

# Or manually:
docker compose -f infra/compose/docker-compose.dev.yml up -d
```

### 4. Run the Services

Open **three terminal windows**:

**Terminal 1 - API Server:**
```bash
cd services/api
python main.py
# API will be available at http://localhost:8080
```

**Terminal 2 - Web Interface:**
```bash
cd apps/web
npm run dev
# Web UI will be available at http://localhost:3000
```

**Terminal 3 - Test the System:**
```bash
python examples/run_demo.py
```

## 🎯 What You Can Do

### Via Web Interface (http://localhost:3000)

1. **Start a Simulation**
   - Click "Start New Run" 
   - Watch the status update in real-time
   - View current vs time plot

2. **Configure Scenarios**
   - Adjust voltage, duration, and mesh settings
   - Save custom scenarios

### Via API (http://localhost:8080)

```bash
# Health check
curl http://localhost:8080/health

# Create a run
curl -X POST http://localhost:8080/api/v1/runs \
  -H "Content-Type: application/json" \
  -d '{"type":"simulation","engine":"auto"}'

# List runs
curl http://localhost:8080/api/v1/runs
```

### Via Python

```python
# Run a local simulation
from workers.sim_fenicsx.simple_solver import run_simulation

results = run_simulation()
print(f"Generated {len(results)} frames")
```

## 📁 Project Structure

```
galvana/
├── services/api/        # FastAPI backend
├── apps/web/           # Next.js frontend  
├── workers/            # Simulation engines
├── examples/           # Demo scenarios
└── infra/             # Docker configs
```

## 🧪 Run the Demo

The demo script tests the entire system:

```bash
python examples/run_demo.py
```

This will:
1. Run a local simulation
2. Generate a current vs time plot
3. Test API endpoints (if running)
4. Save results to `demo_results.json`

## 📊 View Results

1. **Web Dashboard**: http://localhost:3000
2. **API Docs**: http://localhost:8080/docs
3. **MinIO Console**: http://localhost:9001 (minioadmin/minioadmin123)

## 🛠️ Development Commands

```bash
make help        # Show all commands
make up          # Start infrastructure
make down        # Stop infrastructure
make api         # Run API server
make web         # Run web frontend
make clean       # Clean build artifacts
```

## 🔧 Configuration

Edit `.env` file to configure:
- Database connection
- Redis URL
- S3/MinIO settings
- API ports

## 📈 Next Steps

1. **Explore the API**: Visit http://localhost:8080/docs for interactive API docs
2. **Modify Scenarios**: Edit `examples/scenarios/ni_plating_mvp.yaml`
3. **Extend the Solver**: Modify `workers/sim-fenicsx/simple_solver.py`
4. **Customize UI**: Edit `apps/web/app/page.tsx`

## 🐛 Troubleshooting

**Port already in use:**
```bash
# Change ports in .env file
API_PORT=8081
NEXT_PUBLIC_API_URL=http://localhost:8081
```

**Docker issues:**
```bash
docker compose -f infra/compose/docker-compose.dev.yml down -v
docker compose -f infra/compose/docker-compose.dev.yml up -d
```

**Dependencies missing:**
```bash
pip install poetry
poetry install
```

## 🎉 Success Checklist

- [ ] Infrastructure running (PostgreSQL, Redis, MinIO)
- [ ] API server responding at http://localhost:8080
- [ ] Web interface loaded at http://localhost:3000
- [ ] Demo simulation completed successfully
- [ ] Results plotted and saved

## 📚 Learn More

- [System Design](SYSTEM_DESIGN.md)
- [API Specification](API_SPEC.yaml)
- [Implementation Guide](IMPLEMENTATION_GUIDE.md)

---

**Need help?** Check the logs:
```bash
# API logs
cd services/api && python main.py

# Frontend logs  
cd apps/web && npm run dev
```