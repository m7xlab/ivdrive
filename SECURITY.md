# Security Policy

## Supported versions

Security fixes go into the latest release; please upgrade to it before reporting.

| Version | Supported          |
| ------- | ------------------ |
| 1.4.x (latest) | Yes         |
| 1.3.x and earlier | No: upgrade to the latest 1.4.x |
| < 1.0   | No                 |

## What we do to keep iVDrive safe

- **Every pull request and every week:** CodeQL (Python and TypeScript), Trivy (container image and filesystem), Gitleaks (secrets), `pip-audit` and `npm audit` on the locked dependencies, plus an automated code review.
- **Repository protections:** GitHub secret scanning with push protection, Dependabot vulnerability alerts, and a protected `main` branch: changes arrive through reviewed pull requests that must pass lint, type checks and the security scans.
- **Design:** the assistant can only read the signed-in user's data (parsed queries, a restricted database role, row-level security and a read-only transaction); sessions can be revoked; sign-in attempts are rate limited; secrets are encrypted at rest. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#security-model).
- **Release v1.4.0** was a dedicated hardening release; see the [changelog](CHANGELOG.md).

## Reporting a vulnerability

We take the security of iVDrive seriously. If you believe you have found a security vulnerability, please report it as described below.

**Do not report security vulnerabilities through public GitHub issues, discussions, or pull requests.**

### How to report

1. **Report privately** using [GitHub Security Advisories](https://github.com/m7xlab/iVDrive/security/advisories/new) for this repository, or contact the maintainers through the [m7xlab/iVDrive](https://github.com/m7xlab/iVDrive) repository (e.g. via repository contact or a private channel if available).
2. **Use a clear subject** such as: `[SECURITY] iVDrive vulnerability report`.
3. **Include** a description of the vulnerability, impact, steps to reproduce, and your environment (OS, how you run iVDrive, versions). If possible, include a proof of concept and any timeline constraints for disclosure.

### What to include

- **Description**: What the vulnerability is and where it occurs.
- **Impact**: What an attacker could do (e.g. access to data, privilege escalation).
- **Steps to reproduce**: Detailed steps so we can verify the issue.
- **Environment**: OS, Docker/Compose version, how you deployed iVDrive.
- **Proof of concept**: If safe to share, code or commands that demonstrate the issue.

### Response timeline

- **Acknowledgment**: We aim to respond within 48 hours.
- **Status update**: We aim to provide an update within 7 days.
- **Resolution**: Depends on severity and complexity; we will work with you on disclosure timing after a fix is available.

### Disclosure

We will disclose the issue after a fix is available and coordinate with you on timing where appropriate. We will credit reporters when they agree to it.

Thank you for helping keep iVDrive and its users safe.
