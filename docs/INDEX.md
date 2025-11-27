# ElectroChem-Sim Documentation

> *Electrochemical simulation and anodizing process visualization platform*

## Quick Navigation

| Document | Description |
|----------|-------------|
| [README](../README.md) | Project overview and quick start |
| [CHANGELOG](../CHANGELOG.md) | Version history and changes |
| [CONTRIBUTING](../CONTRIBUTING.md) | Development guidelines |
| [SECURITY](../SECURITY.md) | Security policies |

## Architecture

| Document | Description |
|----------|-------------|
| [Architecture](architecture/) | System design documentation |

## Visualization

| Document | Description |
|----------|-------------|
| [Visualization](visualization/) | 3D visualization documentation |

## Setup & Configuration

| Document | Description |
|----------|-------------|
| [Setup Guide](setup/) | Installation and configuration |

## Reports

| Document | Description |
|----------|-------------|
| [Reports](reports/) | Analysis and audit reports |

## Core Features

### Simulation Engine
- **Anodizing Simulation** - Type II/III anodizing process modeling
- **Electrochemical Models** - Faraday's laws, current distribution
- **Time-Evolution** - Real-time process visualization

### Hardware Abstraction Layer (HAL)
- **Rectifier Interface** - Power supply control
- **Sensor Integration** - Temperature, pH, conductivity
- **Safety Systems** - Emergency shutdown protocols

### Visualization
- **3D Part Rendering** - Real-time oxide layer visualization
- **Process Monitoring** - Live graphs and metrics
- **Color Prediction** - Anodizing color simulation

## Tech Stack

### Frontend
- Next.js 14 (App Router)
- Three.js (3D visualization)
- TypeScript

### Backend
- Python (FastAPI)
- Rust (simulation core)
- PostgreSQL

### Hardware
- Modbus/TCP communication
- Industrial sensor protocols

## MADFAM Ecosystem Integration

| App | Integration |
|-----|-------------|
| [Primavera3D](../../primavera3d) | Manufacturing workflow |
| [Sim4D](../../sim4d) | CAD part geometry |
| [Dhanam](../../dhanam) | Process cost tracking |

## Development

### Prerequisites
- Node.js 18+
- Python 3.10+
- Rust 1.70+ (for simulation core)
- PostgreSQL 15+

### Quick Start
```bash
pnpm install
pnpm dev
```

---

*Last updated: November 2025*
