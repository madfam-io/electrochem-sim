# Contributing to Galvana

Thank you for your interest in contributing to Galvana! This document provides guidelines for contributing to the project.

## Development Setup

### Prerequisites

- Python 3.11+
- Node.js 18+ (for web components)
- Docker and Docker Compose
- FEniCSx (for simulation engine)

### Getting Started

```bash
# Clone the repository
git clone https://github.com/madfam/electrochem-sim.git
cd electrochem-sim

# Create Python virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install Python dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Install Node dependencies (for web)
pnpm install

# Copy environment variables
cp .env.example .env.local

# Start development services
docker-compose up -d

# Run development server
pnpm dev
```

## Branch Strategy

We use a trunk-based development model:

- `main` - Production-ready code
- `feat/` - New features (e.g., `feat/moose-engine-support`)
- `fix/` - Bug fixes
- `chore/` - Maintenance tasks
- `docs/` - Documentation updates

## Commit Messages

We follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>
```

**Types:** `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

**Scopes:** `api`, `hal`, `engine`, `models`, `web`, `drivers`

## Pull Request Process

1. Create a branch from `main`
2. Make changes with clear commits
3. Write/update tests
4. Run validation notebooks if physics changed
5. Update documentation if needed
6. Open a PR with clear description
7. Request review and address feedback

### PR Checklist

- [ ] Python tests pass (`pytest`)
- [ ] JS/TS tests pass (`pnpm test`)
- [ ] Linting passes (`pnpm lint`, `ruff check`)
- [ ] Type checking passes (`mypy`, `pnpm typecheck`)
- [ ] Validation notebooks run successfully
- [ ] CHANGELOG.md updated for significant changes

## Code Standards

### Python

- Type hints required
- Docstrings in Google format
- Black formatting
- Ruff linting
- 80% test coverage minimum

### TypeScript

- Strict mode enabled
- Explicit return types
- Use Zod for validation

## Physics Model Development

When adding or modifying physics models:

### 1. Documentation

- Document all equations with references
- Include units for all parameters
- Describe boundary conditions

### 2. Validation

- Compare against analytical solutions where possible
- Benchmark against published literature
- Include validation notebook in `notebooks/validation/`

### 3. Testing

```python
def test_nernst_planck_diffusion():
    """Test Nernst-Planck diffusion against analytical solution."""
    # Setup
    # Execute
    # Assert within tolerance
```

## HAL Driver Development

When adding instrument drivers:

### 1. Implement the Interface

```python
class MyPotentiostatDriver(PotentiostatInterface):
    async def connect(self) -> None: ...
    async def disconnect(self) -> None: ...
    async def run_cv(self, params: CVParams) -> CVResult: ...
```

### 2. Safety Considerations

- Implement all safety interlocks
- Validate parameter ranges
- Handle connection failures gracefully

### 3. Testing

- Mock hardware for unit tests
- Integration tests with real hardware (manual)
- Document calibration procedures

## Simulation Engine Development

When working with simulation engines:

- Test with small meshes first
- Monitor memory usage
- Add timeout handling
- Document convergence criteria

## Security Guidelines

- Never commit credentials
- Validate all hardware commands
- Sanitize user inputs
- Follow safety interlock requirements
- Report vulnerabilities to security@madfam.io

## Getting Help

- **Issues**: Open a GitHub issue
- **Discussions**: Use GitHub Discussions

## License

By contributing, you agree that your contributions will be licensed under the Mozilla Public License 2.0.
