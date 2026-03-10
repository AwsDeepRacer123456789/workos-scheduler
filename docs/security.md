# Security

## Threat Model Overview

This system handles job scheduling and execution for internal services. Threats include:

- **Unauthorized access**: Malicious actors creating, modifying, or deleting jobs
- **Data exposure**: Sensitive job data or credentials leaked
- **Denial of service**: Overwhelming the system with too many jobs
- **Code injection**: Malicious code executed in worker processes
- **Privilege escalation**: Workers gaining unauthorized access to resources

## OWASP Top Risks and Mitigations

| OWASP Risk | Mitigation for This Project |
|------------|----------------------------|
| **A01: Broken Access Control** | Implement role-based access control (RBAC). API endpoints require authentication. Workers use service accounts with minimal permissions. Job ownership and tenant isolation enforced. |
| **A02: Cryptographic Failures** | All API traffic over TLS. Secrets stored in secure vault (AWS Secrets Manager). Database connections encrypted. No secrets in logs or code. |
| **A03: Injection** | Job payloads validated and sanitized. Database queries use parameterized statements. Worker execution uses sandboxed environments where possible. |
| **A05: Security Misconfiguration** | Infrastructure as code (Terraform) ensures consistent configs. Security headers on API. Default credentials changed. Regular security audits. |
| **A07: Identification and Authentication Failures** | Multi-factor authentication for admin users. API keys with expiration and rotation. Service accounts for workers. Rate limiting on auth endpoints. |

## Authentication and Authorization

### API Authentication

- REST API uses API keys or OAuth2 tokens
- Keys are scoped to specific tenants or roles
- Keys can be revoked immediately
- All API requests logged with user identity

### Worker Authentication

- Workers use service accounts with IAM roles
- Workers authenticate to broker and database using credentials from secure vault
- Workers cannot access API endpoints directly

## IAM Roles

### API Role

- Read/write access to Postgres (job definitions, state)
- Read access to Redis
- Publish permissions to message broker
- Write access to metrics and logs
- No direct access to worker execution environment

### Worker Role

- Consume permissions from message broker
- Read/write access to Postgres (job state updates)
- Read access to secrets vault (for job credentials)
- No access to API endpoints
- Limited to specific resource quotas

## Secrets Management

- All secrets stored in AWS Secrets Manager (or equivalent)
- Secrets rotated regularly
- Workers fetch secrets at runtime, never stored on disk
- API keys and database passwords never logged
- Secrets access audited

## Audit Logging

- All API requests logged with: user, action, resource, timestamp, IP
- All job state changes logged
- Worker execution failures logged
- Security events (failed auth, privilege violations) logged
- Logs retained for compliance period
- Logs searchable and alertable
