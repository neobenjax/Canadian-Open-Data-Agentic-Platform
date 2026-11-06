# CAN-45: Docker Hardening & GHCR Containerization

**Task:** CAN-45 (BEN-31)  
**Deliverable:** Production multi-stage Dockerfiles, Docker Compose multi-service topology, GHCR CI publishing workflow, and security hardening specifications.

---

## 1. Container Images

The platform provides two hardened, minimal multi-stage OCI images built on `python:3.12-slim-bookworm` with [Astral `uv`](https://github.com/astral-sh/uv):

| Image | Dockerfile | Target Package | Entrypoint |
|---|---|---|---|
| `ghcr.io/neobenjax/canadian-open-data-agentic-platform/candata-mcp` | `docker/Dockerfile.fastmcp` | `candata_mcp` | FastMCP stdio server (`candata-mcp`) |
| `ghcr.io/neobenjax/canadian-open-data-agentic-platform/candata-orchestrator` | `docker/Dockerfile.orchestrator` | `candata_agent` & `apps/agent-ui` | Streamlit interactive UI (`streamlit run apps/agent-ui/app.py`) |

---

## 2. Docker Security Hardening Profile

Both containers enforce defense-in-depth principles:

1. **Non-Root Execution (UID/GID 10001):**
   - The runtime stage provisions a dedicated unprivileged user `candata:candata` with fixed system UID `10001` and GID `10001`.
   - Never runs as root (`USER 10001:10001`).
2. **Read-Only Root Filesystem:**
   - The server container runs with `read_only: true`.
   - Temporary scratch files use an isolated, non-executable tmpfs mount (`/tmp:rw,noexec,nosuid,size=64m`).
3. **Dropped Capabilities:**
   - Drops all Linux kernel capabilities (`cap_drop: [ALL]`).
   - Prevents privilege escalation (`security_opt: [no-new-privileges:true]`).
4. **Isolated Checkpoint Volume:**
   - The orchestrator persists LangGraph time-travel checkpoints in a named Docker volume mounted at `/app/.candata` with permissions restricted to UID 10001.
5. **Deterministic Healthchecks:**
   - `candata-mcp`: Verifies Python runtime, package imports, and an in-memory DuckDB query (`SELECT 1`).
   - `candata-orchestrator`: Probes the Streamlit health endpoint (`http://localhost:8501/_stcore/health`).

---

## 3. Running with Docker Compose

Run the entire platform locally with zero host Python dependencies:

```bash
# Build and run the multi-agent suite in background
docker compose up -d --build

# View container logs
docker compose logs -f

# Verify running services and health status
docker compose ps

# Access the Streamlit multi-agent UI in your browser
# Open: http://localhost:8501

# Stop and clean up containers
docker compose down
```

---

## 4. Automated GHCR Publishing Pipeline

The GitHub Actions workflow `.github/workflows/docker-publish.yml` automatically builds, tags, and publishes OCI-compliant multi-arch images (`linux/amd64`, `linux/arm64`) to the GitHub Container Registry (`ghcr.io`):
- Pushes to `main` tag images with `latest` and short commit SHAs (`sha-<short>`).
- Version tags (e.g. `v1.0.0`) publish tagged semver releases.
- Build caching is accelerated via GitHub Actions cache backend (`type=gha`).
