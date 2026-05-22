# PHR Backend Dependency Management

Date: 2026-05-02

## Overview

All Python dependencies in `phr_backend1/requirements.txt` are now pinned to specific versions for reproducible builds and security posture tracking.

## Why pinning matters

1. **Security**: Pinned versions make dependency vulnerabilities traceable and fixable.
2. **Reproducibility**: All environments (local, dev, prod) run exactly the same code.
3. **Supply chain safety**: Prevents surprise breaking changes in minor version bumps.

## Current pinned versions

See `requirements.txt` for the full list. Key dependencies:

- **FastAPI** `0.104.1` — Web framework
- **SQLAlchemy** `2.0.23` — ORM
- **asyncpg** `0.29.0` — PostgreSQL async driver
- **Pydantic** `2.5.0` — Data validation
- **google-cloud-storage** `2.14.0` — GCS integration
- **python-jose** `3.3.0` — JWT handling

## Updating dependencies

### Monthly security updates

1. Run audit for CVE updates:
   ```bash
   pip-audit -r requirements.txt
   ```

2. For a specific package update:
   ```bash
   pip install --upgrade fastapi==0.110.0
   pip freeze > requirements-new.txt
   # Review diff and test
   ```

3. Test in CI before merging:
   - Unit tests
   - Integration tests (if applicable)
   - Smoke test on staging

### Quarterly version bumps

Plan quarterly updates for minor/patch versions to stay current with security and performance fixes.

## Next steps

Add CI/CD step to run `pip-audit` on every PR against `requirements.txt` to catch new CVEs.
