# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned
- Additional potentiostat driver integrations
- MOOSE engine support
- Advanced EIS fitting algorithms

## [0.1.0] - 2024-11-27

### Added
- **Galvana** - Electrochemical Simulation Platform
- Integration bridge between API and HAL services
- HAL (Hardware Abstraction Layer) microservice
- Plugin architecture for instrument drivers
- Safety interlocks for hardware operations
- Janua authentication module
- Scenario YAML configuration format

### Physics Models
- Nernst-Planck diffusion equations
- Butler-Volmer kinetics
- EIS (Electrochemical Impedance Spectroscopy)
- Cyclic voltammetry simulation
- Chronoamperometry analysis

### Technical
- Python backend with FastAPI
- FEniCSx simulation engine support
- WebSocket real-time streaming
- PostgreSQL with pgvector
- Redis job queue
- Docker containerization

### Security
- OIDC/SAML SSO support
- RBAC/ABAC authorization (OPA policies)
- TLS 1.3 encryption
- Audit logging infrastructure
