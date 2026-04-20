<!-- DIATAXIS: how-to + reference -->
<!-- AUDIENCE: devops -->

# Operations Guide

## Infrastructure Overview
<!-- PURPOSE: Operators need a single-page mental model of the system's
     deployment topology. What runs where, how components connect, and
     what external dependencies exist. This is the first thing to check
     during an incident. -->
<!-- EXAMPLE:
### Deployment Topology

| Component | Host | Port | Health Check |
|-----------|------|------|-------------|
| API Server | app-01.internal | 8080 | GET /health |
| Worker Pool | worker-01.internal | -- | Prefect agent heartbeat |
| PostgreSQL | db-01.internal | 5432 | pg_isready |
| Redis Cache | cache-01.internal | 6379 | redis-cli ping |

### External Dependencies

| Service | Purpose | Timeout | Fallback |
|---------|---------|---------|----------|
| OpenAI API | LLM scoring | 30s | Cached results from last successful run |
| S3 (data lake) | Input file storage | 10s | Local file fallback in /data/raw/ |
| SendGrid | Alert email delivery | 15s | Log to stderr, trigger PagerDuty instead |

### Architecture Diagram

```
                      ┌─────────────┐
                      │  Load       │
                      │  Balancer   │
                      │  :443       │
                      └──────┬──────┘
                             │
                    ┌────────┴────────┐
                    │                 │
              ┌─────┴─────┐    ┌─────┴─────┐
              │  API-01   │    │  API-02   │
              │  :8080    │    │  :8080    │
              └─────┬─────┘    └─────┬─────┘
                    │                │
              ┌─────┴────────────────┴─────┐
              │         PostgreSQL         │
              │         :5432              │
              └────────────────────────────┘
```
-->

## Deployment
<!-- PURPOSE: Step-by-step deployment procedure that an operator can follow
     at 3am without prior context. Every command must be copy-paste-ready.
     Must include both deploy and rollback. -->
<!-- EXAMPLE:
### Deploy

**Prerequisites:**
- [ ] SSH access to app-01.internal
- [ ] Latest `.env.production` values confirmed
- [ ] Database migrations applied (check `alembic heads`)
- [ ] Previous deployment healthy (check health endpoint)

1. Pull latest code:
   ```bash
   ssh app-01.internal
   cd /opt/app && git pull origin main
   ```

2. Check for database migrations:
   ```bash
   alembic heads
   # Expected: single head matching latest migration
   alembic upgrade head
   # Expected: "Running upgrade ... -> ..." or "Nothing to upgrade"
   ```

3. Rebuild containers:
   ```bash
   docker compose build --no-cache api worker
   ```
   Expected output:
   ```
   [+] Building 45.2s (12/12) FINISHED
   => exporting to image
   ```

4. Deploy with zero-downtime restart:
   ```bash
   docker compose up -d --remove-orphans
   ```

5. Verify deployment:
   ```bash
   curl -s http://localhost:8080/health | jq .status
   # Expected: "ok"

   docker compose ps
   # Expected: all containers show "Up" status

   docker compose logs --tail=20 api
   # Expected: no ERROR lines, "Listening on port 8080"
   ```

### Rollback

**When to rollback:** Health check fails after deploy, error rate exceeds 5%,
or critical functionality is broken.

1. Identify the previous working version:
   ```bash
   git log --oneline -5
   # Note the commit hash of the previous working version
   ```

2. Revert to previous version:
   ```bash
   git checkout PREVIOUS_COMMIT_HASH
   docker compose build --no-cache api worker
   docker compose up -d --remove-orphans
   ```

3. If database migrations need rollback:
   ```bash
   alembic downgrade -1
   # Expected: "Running downgrade ... -> ..."
   ```

4. Verify rollback:
   ```bash
   curl -s http://localhost:8080/health | jq .status
   # Expected: "ok"
   ```

5. Notify the team:
   ```bash
   echo "ROLLBACK: Deployed $(git rev-parse --short HEAD) at $(date -u)" >> /var/log/deploy.log
   ```
-->

## Service Management
<!-- PURPOSE: How to start, stop, restart individual services. Operators
     need this during maintenance windows and partial outages. -->
<!-- EXAMPLE:
| Action | Command | Expected Output |
|--------|---------|-----------------|
| Start all services | `docker compose up -d` | All containers show "Started" |
| Stop all services | `docker compose down` | All containers show "Stopped" |
| Restart API only | `docker compose restart api` | API container shows "Started" |
| Restart worker only | `docker compose restart worker` | Worker container shows "Started" |
| View API logs | `docker compose logs -f --tail=100 api` | Streaming log output |
| View worker logs | `docker compose logs -f --tail=100 worker` | Streaming log output |
| Check status | `docker compose ps` | Container status table |
| Force recreate | `docker compose up -d --force-recreate api` | Container recreated from scratch |

### Graceful Shutdown

The API server handles SIGTERM for graceful shutdown. Active requests complete
before the process exits (30s timeout).

```bash
# Graceful stop (waits for in-flight requests)
docker compose stop api
# Expected: "Gracefully stopping... done" within 30 seconds

# Force stop (kills immediately -- use only if graceful fails)
docker compose kill api
# Expected: immediate stop, may drop in-flight requests
```

### Log Rotation

Logs are written to stdout/stderr and captured by Docker's JSON log driver.

```bash
# Check log file sizes
du -sh /var/lib/docker/containers/*/
# If any container log exceeds 500MB, rotate:
docker compose down && docker compose up -d
```
-->

## Configuration Reference
<!-- PURPOSE: Complete reference of all configuration knobs. Operators
     need to know what can be changed, where to change it, and what
     effect it has. -->
<!-- EXAMPLE:
### Environment Variables

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `DATABASE_URL` | -- | Yes | PostgreSQL connection string (`postgresql://user:pass@host/db`) |
| `OPENAI_API_KEY` | -- | Yes | API key for LLM scoring |
| `LOG_LEVEL` | `INFO` | No | Logging verbosity: DEBUG, INFO, WARNING, ERROR |
| `WORKER_CONCURRENCY` | `4` | No | Number of parallel worker threads |
| `API_PORT` | `8080` | No | Port for the API server |
| `REDIS_URL` | `redis://localhost:6379` | No | Redis connection for caching |
| `SENTRY_DSN` | -- | No | Sentry error tracking DSN (disabled if unset) |

### Configuration Files

| File | Purpose | Restart Required | Location |
|------|---------|-----------------|----------|
| `.env` | Environment variables for Docker Compose | Yes | `/opt/app/.env` |
| `config.yaml` | Application settings (scoring models, timeouts) | Yes | `/opt/app/config.yaml` |
| `docker-compose.yml` | Service definitions, ports, volumes | Yes | `/opt/app/docker-compose.yml` |
| `alembic.ini` | Database migration configuration | No (only affects migrations) | `/opt/app/alembic.ini` |

### Changing Configuration

1. Edit the configuration file:
   ```bash
   vim /opt/app/.env
   ```

2. Validate the change:
   ```bash
   docker compose config --quiet
   # Expected: no output means valid. Errors printed to stderr.
   ```

3. Apply the change:
   ```bash
   docker compose up -d
   # Only affected containers restart
   ```
-->

### Changing Configuration
<!-- PURPOSE: How to change a configuration value and make it take effect.
     Operators need clear steps covering edit, validate, and restart/reload
     to prevent misconfigurations. -->
<!-- EXAMPLE:
1. Edit the configuration file:
   ```bash
   ...
   ```

2. Validate the change:
   ```bash
   ...
   # Expected: ...
   ```

3. Apply the change:
   ```bash
   ...
   ```
-->

## Monitoring & Alerting
<!-- OPTIONAL -- delete if not applicable -->
<!-- PURPOSE: What to monitor, where alerts are configured, and how to
     respond to common alerts. Only applicable for projects with
     monitoring infrastructure. -->
<!-- EXAMPLE:
### Key Metrics

| Metric | Alert Threshold | Response |
|--------|----------------|----------|
| API response time (p95) | > 2s for 5min | Check database query performance: `docker compose exec db pg_stat_activity` |
| Worker queue depth | > 100 pending for 10min | Scale worker pool: `docker compose up -d --scale worker=4` |
| Disk usage | > 85% | Rotate logs, clean temp files: `docker system prune -f` |
| Error rate (5xx) | > 5% for 5min | Check API logs: `docker compose logs --tail=50 api \| grep ERROR` |
| Database connections | > 90% of max_connections | Check for connection leaks: `SELECT count(*) FROM pg_stat_activity` |

### Alert Response Procedure

1. **Acknowledge** the alert in PagerDuty
2. **Diagnose** using the quick diagnosis guide in [Troubleshooting](./TROUBLESHOOTING.md#quick-diagnosis)
3. **Fix** using the relevant runbook entry
4. **Verify** the fix resolved the alert condition
5. **Document** the incident in the incident log
-->

### Health Check Script
<!-- OPTIONAL -- delete if not applicable -->
<!-- PURPOSE: Composite script that checks all components in one run.
     Provides a single command for operators to validate full system health
     after a change or during an incident. -->
<!-- EXAMPLE:
```bash
#!/bin/bash
echo "=== Health Check ==="
for component in ...; do
  echo -n "$component: "
  ... && echo "OK" || echo "FAIL"
done
```
-->

## Backup & Recovery
<!-- OPTIONAL -- delete if not applicable -->
<!-- PURPOSE: How backups are performed, verified, and restored. Operators
     need this for disaster recovery and before risky maintenance. -->
<!-- EXAMPLE:
### Database Backup

```bash
# Create a backup
pg_dump -h db-01.internal -U app_user dataforge > /backups/dataforge_$(date +%Y%m%d_%H%M%S).sql
# Expected: file created, size should be > 1MB for non-empty database

# Verify backup integrity
pg_restore --list /backups/dataforge_TIMESTAMP.sql | head -5
# Expected: shows table list, no errors
```

### Database Restore

```bash
# Stop the application first
docker compose stop api worker

# Restore from backup
psql -h db-01.internal -U app_user dataforge < /backups/dataforge_TIMESTAMP.sql
# Expected: "COPY NNN" lines for each table

# Restart the application
docker compose start api worker

# Verify
curl -s http://localhost:8080/health | jq .status
# Expected: "ok"
```
-->
