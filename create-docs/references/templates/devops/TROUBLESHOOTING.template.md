<!-- DIATAXIS: how-to -->
<!-- AUDIENCE: devops -->

# Troubleshooting Guide

<!-- docs-meta: last-updated: {date}, sources: [{source_files}] -->

## Quick Diagnosis
<!-- PURPOSE: A fast triage path for operators who need to identify the
     problem category before diving into specific runbook entries. This
     decision tree should take less than 60 seconds to navigate. -->
<!-- EXAMPLE:
### Triage Decision Tree

```
Is the service responding?
├── No → Is the container running?
│   ├── No → See "Service Won't Start" below
│   └── Yes → Is the port accessible?
│       ├── No → See "Port Not Accessible" below
│       └── Yes → See "Service Unresponsive" below
└── Yes → Is it returning errors?
    ├── 5xx errors → See "Internal Server Errors" below
    ├── 4xx errors → See "Client Errors" below (likely not a service issue)
    └── Slow responses → See "Performance Issues" below
```

### First Steps (Always)

Before diving into specific issues, gather baseline information:

```bash
# 1. Check container status
docker compose ps
# Look for: containers in "Restarting" or "Exit" state

# 2. Check recent logs
docker compose logs --tail=50 --timestamps
# Look for: ERROR lines, stack traces, connection refused

# 3. Check system resources
df -h          # Disk space
free -m        # Memory
uptime         # Load average
# Look for: disk > 90%, available memory < 500MB, load > CPU count
```
-->

## Common Issues
<!-- PURPOSE: Each issue is a self-contained runbook entry that an operator
     can follow to diagnose and fix a specific problem. Every entry includes
     the symptom (what the operator sees), the cause, the fix with exact
     commands, expected output after the fix, and escalation steps if the
     fix does not work. -->
<!-- EXAMPLE:
### Service Won't Start

**Symptom:** `docker compose up -d` completes but the container immediately
exits. `docker compose ps` shows status `"Exit 1"`.

**Likely causes:**
1. Missing environment variable
2. Database not reachable
3. Port already in use

**Diagnosis:**

```bash
# Check exit logs
docker compose logs api --tail=20
# Look for: "KeyError", "ConnectionRefusedError", "Address already in use"
```

**Fix (missing environment variable):**

```bash
# Identify the missing variable from the error message
# Example error: KeyError: 'DATABASE_URL'

# Check .env file
grep DATABASE_URL /opt/app/.env
# If empty or missing, add it:
echo 'DATABASE_URL=postgresql://user:pass@db-01.internal/dataforge' >> /opt/app/.env

# Restart
docker compose up -d
```

**Fix (database not reachable):**

```bash
# Test database connectivity
pg_isready -h db-01.internal -p 5432
# Expected: "db-01.internal:5432 - accepting connections"

# If not accepting connections:
ssh db-01.internal
systemctl status postgresql
# Restart if needed:
systemctl restart postgresql
```

**Fix (port already in use):**

```bash
# Find what's using the port
ss -tlnp | grep 8080
# Kill the conflicting process or change the port in .env:
# API_PORT=8081

docker compose up -d
```

**Expected result after fix:** `docker compose ps` shows all containers `"Up"`,
`curl -s http://localhost:8080/health` returns `{"status": "ok"}`.

**Escalation:** If none of the above fixes work, check Docker daemon status:
`systemctl status docker`. If Docker itself is unhealthy, restart it:
`systemctl restart docker`.

---

### Database Connection Failures

**Symptom:** Application logs show `ConnectionRefusedError` or
`OperationalError: could not connect to server`. API returns 500 errors.

**Diagnosis:**

```bash
# Test connectivity from the app server
pg_isready -h db-01.internal -p 5432
# Expected: "accepting connections"

# If that works, check credentials
PGPASSWORD=YOUR_PASSWORD psql -h db-01.internal -U app_user -d dataforge -c "SELECT 1"
# Expected: returns "1"
```

**Fix (PostgreSQL is down):**

```bash
ssh db-01.internal
systemctl status postgresql
# If not running:
systemctl start postgresql

# Verify
pg_isready -h db-01.internal -p 5432
# Expected: "accepting connections"
```

**Fix (max connections exceeded):**

```bash
# Check active connections
psql -h db-01.internal -U postgres -c "SELECT count(*) FROM pg_stat_activity"
# If close to max_connections (default 100):

# Kill idle connections
psql -h db-01.internal -U postgres -c "
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE state = 'idle' AND query_start < now() - interval '10 minutes'
"

# Long-term fix: increase max_connections in postgresql.conf
```

**Expected result after fix:** Application logs stop showing connection errors.
`curl -s http://localhost:8080/health` returns `{"status": "ok"}`.

**Escalation:** If PostgreSQL keeps crashing, check system resources on db-01:
`df -h`, `free -m`, `dmesg | tail -20` (look for OOM killer).

---

### Pipeline Runs Stalling

**Symptom:** Worker processes are running but pipeline jobs do not complete.
Queue depth keeps growing. No error messages in logs.

**Diagnosis:**

```bash
# Check worker status
docker compose logs --tail=20 worker
# Look for: "Processing job..." without corresponding "Job complete"

# Check for stuck database locks
psql -h db-01.internal -U app_user -c "
SELECT pid, state, wait_event_type, query
FROM pg_stat_activity
WHERE state != 'idle'
ORDER BY query_start
"
# Look for: queries in "Lock" wait state
```

**Fix (stuck database locks):**

```bash
# Identify blocking query
psql -h db-01.internal -U app_user -c "
SELECT blocking.pid AS blocking_pid, blocked.pid AS blocked_pid, blocked.query
FROM pg_stat_activity blocked
JOIN pg_stat_activity blocking ON blocking.pid = ANY(pg_blocking_pids(blocked.pid))
"

# Terminate the blocking query (use the blocking_pid from above)
psql -h db-01.internal -U app_user -c "SELECT pg_terminate_backend(BLOCKING_PID)"

# Restart workers
docker compose restart worker
```

**Fix (worker process memory leak):**

```bash
# Check worker memory usage
docker stats --no-stream worker
# If memory usage exceeds 2GB:

docker compose restart worker
```

**Expected result after fix:** `docker compose logs --tail=5 worker` shows
"Job complete" messages. Queue depth starts decreasing.

**Escalation:** If jobs keep stalling after restart, enable DEBUG logging
(`LOG_LEVEL=DEBUG` in .env) and check for deadlock patterns.
-->

## Log Analysis
<!-- PURPOSE: Where to find logs, what patterns to search for, and how to
     interpret common log entries. Operators use this during incident
     investigation to quickly find relevant information. -->
<!-- EXAMPLE:
### Log Locations

| Service | Log Command | Log Format |
|---------|------------|------------|
| API Server | `docker compose logs api` | JSON structured: `{"timestamp": "...", "level": "...", "message": "..."}` |
| Worker | `docker compose logs worker` | JSON structured (same format) |
| PostgreSQL | `ssh db-01.internal && tail /var/log/postgresql/postgresql-14-main.log` | PostgreSQL default format |
| Nginx (if present) | `tail /var/log/nginx/access.log` | Combined log format |

### Useful Log Searches

```bash
# Find all errors in the last hour
docker compose logs --since 1h api 2>&1 | grep '"level":"ERROR"'

# Find slow queries (> 5s)
docker compose logs --since 1h api 2>&1 | grep -E '"duration_ms":[0-9]{4,}'

# Find specific request by ID
docker compose logs api 2>&1 | grep "request_id.*abc123"

# Count errors by type
docker compose logs --since 1h api 2>&1 | grep '"level":"ERROR"' | jq -r '.error_type' | sort | uniq -c | sort -rn
```

### Common Log Patterns

| Pattern | Meaning | Action |
|---------|---------|--------|
| `ConnectionRefusedError` | Database or external service unreachable | Check service connectivity (see Common Issues) |
| `TimeoutError` | External API call exceeded timeout | Check external service status, consider increasing timeout |
| `OperationalError: disk I/O error` | Disk full or filesystem issue | Check disk space: `df -h` |
| `MemoryError` | Process exceeded memory limit | Restart service, investigate memory usage pattern |
| `RateLimitError` | External API rate limit exceeded | Check rate limiter config, reduce concurrency |
-->

## Health Checks
<!-- PURPOSE: A table of all health check endpoints and commands with
     their expected responses. Used for quick verification that the
     system is operating normally after a change or incident. -->
<!-- EXAMPLE:
| Component | Check Command | Expected Response | Failure Response |
|-----------|--------------|-------------------|------------------|
| API Server | `curl -s http://localhost:8080/health` | `{"status": "ok", "version": "1.2.0"}` | Connection refused or `{"status": "degraded"}` |
| Database | `pg_isready -h db-01.internal -p 5432` | `accepting connections` | `no response` or `rejecting connections` |
| Redis | `redis-cli -h cache-01.internal ping` | `PONG` | `Could not connect` |
| Worker | `docker compose exec worker python -c "print('ok')"` | `ok` | Container not running or Python error |
| Disk Space | `df -h / \| awk 'NR==2{print $5}'` | Less than `85%` | `85%` or higher |
| Memory | `free -m \| awk 'NR==2{print $7}'` | Greater than `500` MB available | Less than `500` MB |

### Full System Health Check Script

```bash
#!/bin/bash
# Run all health checks and report status
echo "=== System Health Check ==="

echo -n "API Server: "
curl -sf http://localhost:8080/health > /dev/null && echo "OK" || echo "FAIL"

echo -n "Database: "
pg_isready -h db-01.internal -p 5432 -q && echo "OK" || echo "FAIL"

echo -n "Redis: "
redis-cli -h cache-01.internal ping 2>/dev/null | grep -q PONG && echo "OK" || echo "FAIL"

echo -n "Disk: "
DISK_PCT=$(df -h / | awk 'NR==2{print $5}' | tr -d '%')
[ "$DISK_PCT" -lt 85 ] && echo "OK (${DISK_PCT}%)" || echo "WARN (${DISK_PCT}%)"

echo -n "Memory: "
MEM_AVAIL=$(free -m | awk 'NR==2{print $7}')
[ "$MEM_AVAIL" -gt 500 ] && echo "OK (${MEM_AVAIL}MB free)" || echo "WARN (${MEM_AVAIL}MB free)"
```
-->

## Performance Issues
<!-- OPTIONAL -- delete if not applicable -->
<!-- PURPOSE: Diagnosis and remediation for performance-related problems.
     Includes symptoms, diagnostic commands, and specific fixes. -->
<!-- EXAMPLE:
### Slow API Responses

**Symptom:** API response time (p95) exceeds 2 seconds.

**Diagnosis:**

```bash
# Check database query performance
docker compose exec db psql -U app_user -c "
SELECT query, mean_exec_time, calls
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 10
"

# Check if connection pool is saturated
docker compose exec db psql -U app_user -c "
SELECT count(*), state FROM pg_stat_activity GROUP BY state
"
```

**Fix (missing database index):**

```bash
# Add index for the slow query (example)
docker compose exec db psql -U app_user -c "
CREATE INDEX CONCURRENTLY idx_results_batch_id ON results(batch_id)
"
# CONCURRENTLY avoids locking the table during index creation
```

**Fix (connection pool exhaustion):**

```bash
# Increase pool size in config
echo 'DB_POOL_SIZE=20' >> /opt/app/.env
docker compose restart api
```

### High Memory Usage

**Symptom:** Container memory exceeds 2GB, potential OOM kills.

**Diagnosis:**

```bash
docker stats --no-stream
# Look for containers approaching their memory limit
```

**Fix:**

```bash
# Restart the affected service
docker compose restart api

# Long-term: increase memory limit in docker-compose.yml
# deploy:
#   resources:
#     limits:
#       memory: 4G
```
-->

## Recovery Procedures
<!-- OPTIONAL -- delete if not applicable -->
<!-- PURPOSE: Step-by-step procedures for recovering from major failures
     such as data loss, complete system outage, or corrupted state. -->
<!-- EXAMPLE:
### Full System Recovery

**When to use:** Complete system outage, all services down.

**Prerequisites:**
- [ ] Access to backup storage
- [ ] SSH access to all servers
- [ ] Database backup less than 24 hours old

**Steps:**

1. Verify infrastructure:
   ```bash
   # Check all servers are reachable
   for host in app-01 worker-01 db-01 cache-01; do
     ping -c 1 ${host}.internal > /dev/null 2>&1 && echo "$host: OK" || echo "$host: UNREACHABLE"
   done
   ```

2. Start database first:
   ```bash
   ssh db-01.internal
   systemctl start postgresql
   pg_isready
   # Expected: "accepting connections"
   ```

3. Restore database if needed:
   ```bash
   LATEST_BACKUP=$(ls -t /backups/dataforge_*.sql | head -1)
   echo "Restoring from: $LATEST_BACKUP"
   psql -U app_user -d dataforge < "$LATEST_BACKUP"
   ```

4. Start application services:
   ```bash
   ssh app-01.internal
   cd /opt/app
   docker compose up -d
   ```

5. Verify full system:
   ```bash
   # Run the health check script
   bash /opt/app/scripts/health-check.sh
   # Expected: all checks show "OK"
   ```

6. Notify stakeholders:
   ```bash
   echo "System restored at $(date -u). Last backup: $LATEST_BACKUP" >> /var/log/incidents.log
   ```
-->
