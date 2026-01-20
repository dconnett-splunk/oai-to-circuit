# Documentation Index

Welcome to the OpenAI to Circuit Bridge documentation!

This documentation is organized into logical sections to help you find what you need quickly.

---

## Quick Links

- 🚀 **[Quick Start Guide](getting-started/quickstart.md)** - Get up and running in minutes
- 📦 **[Installation Guide](getting-started/installation.md)** - Complete systemd setup
- 🏗️ **[Architecture Overview](architecture/architecture.md)** - How the system works
- 🚢 **[Deployment Guide](deployment/deployment-guide.md)** - Deploy updates and manage releases

---

## Documentation Structure

```
docs/
├── getting-started/     Getting up and running
├── deployment/          Deploying and updating
├── architecture/        System design and architecture  
├── operations/          Day-to-day operations and management
├── guides/              Specialized guides and procedures
├── migrations/          Database migrations and changelogs
├── reference/           Reference documentation
└── archive/             Historical status documents
```

---

## Getting Started

New to the bridge? Start here:

| Document | Description |
|----------|-------------|
| **[Quick Start Guide](getting-started/quickstart.md)** | Get started in 5 minutes |
| **[Installation Guide](getting-started/installation.md)** | Complete installation from scratch |
| **[Production Setup](getting-started/production-setup.md)** | Production configuration and best practices |

**Alternative formats:**
- [Quick Start (Org Mode)](getting-started/quickstart.org)

---

## Deployment

Deploying and updating the bridge:

| Document | Description |
|----------|-------------|
| **[Deployment Guide](deployment/deployment-guide.md)** | Complete deployment procedures (merged from 3 docs) |

**Covers:**
- Quick deploy steps
- Standard update procedure
- Configuration updates
- Rollback procedures
- Deployment automation
- Zero-downtime deployment
- Troubleshooting

---

## Architecture

Understanding how the system works:

| Document | Description |
|----------|-------------|
| **[Architecture Overview](architecture/architecture.md)** | System architecture, components, and data flow |
| **[Architecture Diagram](architecture/architecture.html)** | Visual architecture diagram |

**Topics covered:**
- Request flow
- OAuth2 token management
- Quota enforcement
- Splunk HEC integration
- Per-model quotas and blacklisting
- Configuration and secrets

---

## Operations

Day-to-day operations and management:

| Document | Description |
|----------|-------------|
| **[Subkey Management](operations/subkey-management.md)** | Complete subkey guide (merged from 4 docs) |
| **[Key Rotation](operations/key-rotation.md)** | Secure key rotation and lifecycle management |
| **[Diagnostic Logging](operations/diagnostic-logging.md)** | Troubleshooting with logs |
| **[Database Queries](operations/database-queries.md)** | Useful SQL queries |
| **[Dashboard Features](operations/dashboard-features.md)** | Splunk dashboard features |

### Subkey Management

The **[Subkey Management Guide](operations/subkey-management.md)** is a comprehensive resource covering:

- Generating subkeys
- Configuring quotas
- Distributing subkeys securely
- Friendly names system
- Monitoring usage (reports, SQLite, Splunk)
- Revoking access
- Security best practices
- Troubleshooting

### Key Rotation

The **[Key Rotation Guide](operations/key-rotation.md)** covers secure key lifecycle management:

- Revoking compromised keys
- Regular key rotation policies
- Preserving historical data
- Reporting continuity across rotations
- Audit trail and compliance
- **[Quick Start](operations/key-rotation-quickstart.md)** - TL;DR version

---

## Guides

Specialized guides for specific tasks:

| Document | Description |
|----------|-------------|
| **[Backfill Guide](guides/backfill-guide.md)** | Backfilling HEC events and database migrations |
| **[True-Up Guide](guides/trueup-guide.md)** | Reconciling usage data with Azure API |

### Backfill Guide

The **[Backfill Guide](guides/backfill-guide.md)** covers:

- Backfilling HEC events from logs
- Database migration for email support
- Backfilling with email field
- True-up and data reconciliation
- Troubleshooting

---

## Migrations

Database migrations and system changelogs:

| Document | Description |
|----------|-------------|
| **[Email Field Migration](migrations/migration-add-email.md)** | Adding email field to subkey_names |
| **[Splunk/Systemd Changelog](migrations/changelog-splunk-systemd.md)** | Splunk HEC and systemd changes |

---

## Reference

Reference documentation and team-specific information:

| Document | Description |
|----------|-------------|
| **[FIE Team Key](reference/fie-team-key.md)** | Field Innovation Engineering team key information |

---

## Archive

Historical status documents and completion notes:

These documents are archived for historical reference but are no longer actively maintained:

| Document | Description |
|----------|-------------|
| [Phase 1 Complete](archive/phase1-complete.md) | Phase 1 completion status |
| [Implementation Complete](archive/implementation-complete.md) | Implementation completion notes |
| [Changes Summary](archive/changes-summary.md) | Summary of changes |
| [Updates Summary](archive/updates-summary.md) | Summary of updates |
| [Files Changed](archive/files-changed.md) | List of files changed |
| [Summary](archive/summary.md) | General summary |

---

## Common Tasks

Quick links to common tasks:

### For New Users

1. **[Install the bridge](getting-started/installation.md)** - systemd setup
2. **[Generate subkeys](operations/subkey-management.md#generating-subkeys)** - create API keys
3. **[Configure quotas](operations/subkey-management.md#configuring-quotas)** - set limits
4. **[Add friendly names](operations/subkey-management.md#friendly-names-system)** - human-readable names

### For Operators

1. **[Deploy updates](deployment/deployment-guide.md#deploying-updates)** - update procedures
2. **[Monitor usage](operations/subkey-management.md#monitoring-usage)** - reports and queries
3. **[Troubleshoot issues](operations/diagnostic-logging.md)** - debugging
4. **[Backfill data](guides/backfill-guide.md)** - HEC backfilling

### For Administrators

1. **[Production setup](getting-started/production-setup.md)** - production best practices
2. **[Manage subkeys](operations/subkey-management.md)** - full lifecycle
3. **[Rotate keys](operations/key-rotation.md)** - secure key rotation
4. **[Database queries](operations/database-queries.md)** - useful queries
5. **[True-up data](guides/trueup-guide.md)** - reconcile usage

---

## Documentation Maintenance

This documentation was reorganized in January 2026 to:
- Reduce documentation proliferation (30+ files → organized structure)
- Merge overlapping content
- Add cross-links between documents
- Create clear navigation
- Separate active docs from archived status docs

**Previous structure:**
- All docs at repository root
- Multiple overlapping deployment guides
- Four separate subkey guides
- Status documents mixed with operational docs

**Current structure:**
- Organized into logical folders
- Merged overlapping documents
- Comprehensive cross-linking
- Clear navigation path

---

## Contributing to Documentation

When adding or updating documentation:

1. **Place docs in appropriate folders** based on content type
2. **Add breadcrumb navigation** at the top of each document
3. **Include "Related Documentation"** section at the bottom
4. **Update this index** when adding new documents
5. **Use cross-links** to related documents
6. **Keep root README comprehensive** but link to docs/ for details

---

## Need Help?

- **Quick question?** Check the [Quick Start Guide](getting-started/quickstart.md)
- **Installation issue?** See [Installation Guide](getting-started/installation.md)
- **Deployment problem?** Check [Deployment Guide](deployment/deployment-guide.md)
- **Operational question?** Browse [Operations](operations/)
- **Troubleshooting?** See [Diagnostic Logging](operations/diagnostic-logging.md)

---

**[← Back to Repository Root](../README.md)**

