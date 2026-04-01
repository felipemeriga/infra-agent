# infra-agent

LangGraph-based infrastructure management agent exposed as an MCP server. Monitors Docker containers, auto-responds to failures, and provides diagnostic/deploy/restart workflows — all accessible via server-guardian's Claude Code integration.

## Architecture

Four LangGraph workflows orchestrate infrastructure operations:

- **diagnose** — linear pipeline: inspect container → get logs → read compose → LLM analysis → report
- **restart** — retry loop with health checks, escalates after max attempts
- **deploy** — pull image → stop old → start new → health check → verify (with automatic rollback on failure)
- **auto_respond** — autonomous: assess → LLM decides (restart/escalate/wait) → act → verify → notify only on failure

Two background tasks run continuously:

- **Docker event watcher** — listens for `die`, `oom`, `health_status: unhealthy` events → triggers auto_respond
- **Health monitor** — periodic checks for memory threshold breaches and restart loops → triggers auto_respond

All workflows use `RetryPolicy(max_attempts=3)` on external-call nodes and track a `status` field through execution.

## Setup

### Build

```bash
docker buildx build --platform linux/amd64 -t felipemeriga1/infra-agent:latest -f Dockerfile --push .
```

### Run with docker-compose

```yaml
services:
  infra-agent:
    image: felipemeriga1/infra-agent:latest
    container_name: infra-agent
    restart: unless-stopped
    expose:
      - "8002"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - ${COMPOSE_DIR:-./compose}:/compose:ro
    environment:
      - GUARDIAN_URL=http://server-guardian:3000
      - GUARDIAN_API_KEY=${GUARDIAN_API_KEY}
      - INTERNAL_API_KEY=${INTERNAL_API_KEY}
    networks:
      - guardian-net

networks:
  guardian-net:
    external: true
    name: guardian-net
```

### Volumes

| Mount | Purpose |
|-------|---------|
| `/var/run/docker.sock:/var/run/docker.sock:ro` | Docker SDK access (inspect, restart, deploy containers) |
| `${COMPOSE_DIR}:/compose:ro` | Directory with your docker-compose files (for diagnose workflow) |

## Config Reference

### Required

| Variable | Description |
|----------|-------------|
| `GUARDIAN_URL` | server-guardian URL (e.g. `http://server-guardian:3000`) |
| `GUARDIAN_API_KEY` | Auth key for server-guardian `/api/ask` and `/api/notify` |
| `INTERNAL_API_KEY` | Bearer token for MCP clients connecting to this agent |

### Optional

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_PORT` | `8002` | MCP server port |
| `COMPOSE_DIR` | `/compose` | Path to docker-compose files inside container |
| `PROTECTED_SERVICES` | `server-guardian` | Comma-separated, cannot be stopped/restarted/deployed |

### Monitoring

| Variable | Default | Description |
|----------|---------|-------------|
| `MONITOR_INTERVAL` | `60` | Health check frequency (seconds) |
| `NOTIFICATION_COOLDOWN` | `900` | Throttle duplicate alerts (seconds) |
| `MEMORY_THRESHOLD_PCT` | `90` | Memory usage alert trigger (%) |
| `MAX_RESTARTS_WINDOW` | `600` | Window for restart loop detection (seconds) |
| `MAX_RESTARTS_COUNT` | `3` | Restarts in window before alerting |
| `STRIKE_THRESHOLD` | `2` | Consecutive checks before taking action |

### Production Hardening

| Variable | Default | Description |
|----------|---------|-------------|
| `SUPABASE_DB_URL` | `""` | PostgreSQL URL for LangGraph checkpointing (empty = no persistence) |
| `CIRCUIT_BREAKER_FAILURES` | `3` | Consecutive LLM failures before circuit opens |
| `CIRCUIT_BREAKER_TIMEOUT` | `60` | Seconds before recovery probe |
| `SHUTDOWN_TIMEOUT` | `30` | Graceful shutdown wait (seconds) |

### LLM Fallback

Optional direct LLM when server-guardian is down. Server-guardian remains primary; the fallback is only used when it fails.

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `""` | `anthropic`, `openai`, or `google` (empty = no fallback) |
| `LLM_MODEL` | `""` | e.g. `claude-sonnet-4-20250514`, `gpt-4o` |
| `LLM_API_KEY` | `""` | Provider-specific API key |

When using a fallback provider, install the corresponding package in your Dockerfile:

```bash
uv add langchain-anthropic  # or langchain-openai, langchain-google-genai
```

## MCP Tools

### Docker

| Tool | Description |
|------|-------------|
| `mcp_list_containers` | All containers with status, image, ports, uptime |
| `mcp_container_logs(name, lines=100)` | Recent logs |
| `mcp_container_stats(name)` | CPU, memory, network I/O snapshot |
| `mcp_container_inspect(name)` | Full config (env, mounts, restart policy) |
| `mcp_list_images` | Images with tags and sizes |

### Compose

| Tool | Description |
|------|-------------|
| `mcp_list_compose_files` | `.yml`/`.yaml` files in compose directory |
| `mcp_read_compose_file(filename)` | File content |
| `mcp_search_compose_files(query)` | Search across files (service name, image, config) |

### Workflows

| Tool | Description |
|------|-------------|
| `diagnose_service(name)` | Full diagnostic workflow with LLM analysis |
| `restart_service(name)` | Restart with health checks and escalation |
| `deploy_service(name, image_tag="latest")` | Deploy with automatic rollback |

### Agent Status

| Tool | Description |
|------|-------------|
| `get_agent_status` | Monitor interval, cooldown, thresholds, circuit breaker state |

## Monitoring

The agent runs two background tasks that automatically detect and respond to issues:

**Docker event watcher** listens for:
- `die` — container crashed
- `oom` — out of memory kill
- `health_status: unhealthy` — Docker healthcheck failed

**Health monitor** checks every `MONITOR_INTERVAL` seconds for:
- Memory usage above `MEMORY_THRESHOLD_PCT`
- More than `MAX_RESTARTS_COUNT` restarts within `MAX_RESTARTS_WINDOW`

Both trigger the **auto_respond** workflow, which:
1. Gathers container status, logs, and crash history
2. Asks the LLM what to do (restart / escalate / wait)
3. Executes the decision
4. Notifies via WhatsApp only if the action failed or escalation is needed (silent on success)

The notification throttler prevents spam — same service+event won't alert again within `NOTIFICATION_COOLDOWN` seconds.

## Development

```bash
uv sync                          # install deps
uv run pytest -v                 # run tests
uv run ruff check --fix          # lint
uv run ruff format               # format
```
