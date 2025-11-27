# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability in Galvana, please report it responsibly:

1. **DO NOT** create a public GitHub issue
2. Email security@madfam.io with:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Any suggested fixes

We will acknowledge receipt within 48 hours and provide a detailed response within 7 days.

## Security Measures

### Authentication & Authorization

- **OIDC/SAML SSO**: Enterprise identity provider integration
- **Janua Authentication**: Primary authentication via Janua
- **RBAC/ABAC**: Role and attribute-based access control
- **OPA Policies**: Fine-grained authorization with Open Policy Agent
- **API Key Management**: Scoped API keys for programmatic access

### Data Protection

- **Transport Security**: TLS 1.3 enforced for all connections
- **Database Encryption**: PostgreSQL with encryption at rest (AES-256)
- **Simulation Data**: Research data encrypted with tenant-specific keys
- **Vector Storage**: pgvector embeddings protected by database encryption

### Hardware Abstraction Layer (HAL) Security

- **Plugin Sandboxing**: Instrument drivers run in isolated environments
- **Safety Interlocks**: Hardware operation limits enforced in software
- **Command Validation**: All hardware commands validated before execution
- **Emergency Stop**: Software-triggered E-stop capability
- **Audit Logging**: Complete log of all hardware interactions

### Simulation Security

- **Input Validation**: Scenario YAML files strictly validated
- **Resource Limits**: CPU/memory limits on simulation jobs
- **Output Sanitization**: Simulation results validated before storage
- **Job Isolation**: Each simulation runs in isolated container

### API Security

- **Rate Limiting**: Per-user and per-endpoint rate limits
- **Input Validation**: Pydantic schema validation on all inputs
- **WebSocket Security**: Authenticated streaming connections
- **CORS Configuration**: Strict origin allowlisting

## Enterprise Security Features

### Access Control
```
- Multi-tenant isolation with organization boundaries
- Project-level permissions within organizations
- Read/Write/Admin role hierarchy
- Instrument-specific access grants
```

### Audit Logging
```
- All API calls logged with user context
- Hardware operations logged with timestamps
- Simulation job lifecycle tracking
- Immutable audit trail with 7-year retention
```

### Compliance
- ISO 27001 aligned security controls
- SOC 2 Type II audit preparation
- Data residency controls (configurable per tenant)

## Infrastructure Security

- **Container Security**: Non-root containers, security contexts
- **Network Segmentation**: HAL services isolated from public network
- **Secret Management**: Kubernetes secrets or HashiCorp Vault
- **Dependency Scanning**: Automated CVE detection in CI/CD

## Incident Response

1. **Hardware Incidents**: Immediate HAL shutdown, physical inspection required
2. **Data Incidents**: Tenant isolation, forensic analysis
3. **Service Incidents**: Automated failover, status page updates
4. **Notification**: Affected users notified within 24 hours

## Security Headers

```
Content-Security-Policy: default-src 'self'; script-src 'self'; connect-src 'self' wss://api.galvana.io;
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
Strict-Transport-Security: max-age=31536000; includeSubDomains
```

## Contact

Security Team: security@madfam.io
