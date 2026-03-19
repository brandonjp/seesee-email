---
title: Docker Deployment
description: Deploy SeeSee in production with Docker, Docker Compose, and reverse proxies.
---

SeeSee runs as a single Docker container with no external dependencies. The SQLite database is stored on a persistent volume.

## Docker run

```bash
docker run -d \
  --name seesee \
  --restart unless-stopped \
  -p 8080:8080 \
  -p 2525:2525 \
  -e SEESEE_ADMIN_PASSWORD=your-secure-password \
  -e SEESEE_SECRET_KEY=your-random-secret \
  -v seesee-data:/data \
  ghcr.io/brandonjp/seesee-email:latest
```

## Docker Compose

```yaml
services:
  seesee:
    image: ghcr.io/brandonjp/seesee-email:latest
    container_name: seesee
    restart: unless-stopped
    ports:
      - "8080:8080"
      - "2525:2525"
    volumes:
      - seesee-data:/data
    environment:
      SEESEE_ADMIN_PASSWORD: "${SEESEE_ADMIN_PASSWORD:-changeme}"
      SEESEE_SECRET_KEY: "${SEESEE_SECRET_KEY:-}"
      SEESEE_SMTP_ENABLED: "${SEESEE_SMTP_ENABLED:-true}"
      SEESEE_RETENTION_MAX_COUNT: "${SEESEE_RETENTION_MAX_COUNT:-1000}"
      SEESEE_RETENTION_MAX_AGE_DAYS: "${SEESEE_RETENTION_MAX_AGE_DAYS:-90}"
      SEESEE_RETENTION_MAX_STORAGE_MB: "${SEESEE_RETENTION_MAX_STORAGE_MB:-500}"
      SEESEE_RETENTION_CLEANUP_INTERVAL_MINUTES: "${SEESEE_RETENTION_CLEANUP_INTERVAL_MINUTES:-60}"
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8080/api/v1/health')"]
      interval: 30s
      timeout: 5s
      retries: 3

volumes:
  seesee-data:
```

```bash
docker compose up -d
```

## Volume persistence

SeeSee stores its SQLite database at `/data/seesee.db` inside the container. **Always mount a volume at `/data`** to persist data across container restarts and upgrades.

```bash
# Named volume (recommended)
-v seesee-data:/data

# Bind mount to host directory
-v /opt/seesee/data:/data
```

The container runs as a non-root user (`seesee`, UID 1000). If using a bind mount, ensure the directory is writable by UID 1000:

```bash
mkdir -p /opt/seesee/data
chown 1000:1000 /opt/seesee/data
```

## Health check

SeeSee exposes a health endpoint at `GET /api/v1/health` that returns:

```json
{
  "status": "ok",
  "version": "0.18.0",
  "database": "ok"
}
```

The Docker image includes a built-in health check. You can verify container health with:

```bash
docker inspect --format='{{.State.Health.Status}}' seesee
```

## Resource requirements

SeeSee is lightweight:

- **Memory:** ~30–50 MB idle, scales with concurrent connections
- **CPU:** Minimal — SQLite handles queries efficiently
- **Disk:** Depends on email volume and retention settings. The database file grows with stored emails; retention policies keep it under control

For most deployments (thousands of emails/day), a 1-core / 512 MB server is sufficient.

## Environment variable configuration

Create a `.env` file alongside your `docker-compose.yml`:

```bash
SEESEE_ADMIN_PASSWORD=your-secure-password
SEESEE_SECRET_KEY=your-random-secret-key
SEESEE_RETENTION_MAX_COUNT=5000
SEESEE_RETENTION_MAX_AGE_DAYS=180
SEESEE_LOG_LEVEL=info
```

See the [Configuration Reference](/reference/configuration/) for all available variables.

## Reverse proxy setup

In production, place SeeSee behind a reverse proxy for TLS termination and domain routing.

### nginx

```nginx
server {
    listen 443 ssl http2;
    server_name seesee.example.com;

    ssl_certificate     /etc/letsencrypt/live/seesee.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/seesee.example.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Set `SEESEE_BASE_URL=https://seesee.example.com` so SeeSee generates correct URLs.

### Caddy

```
seesee.example.com {
    reverse_proxy localhost:8080
}
```

Caddy automatically handles TLS certificate provisioning via Let's Encrypt.

### Traefik

With Docker labels:

```yaml
services:
  seesee:
    image: ghcr.io/brandonjp/seesee-email:latest
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.seesee.rule=Host(`seesee.example.com`)"
      - "traefik.http.routers.seesee.entrypoints=websecure"
      - "traefik.http.routers.seesee.tls.certresolver=letsencrypt"
      - "traefik.http.services.seesee.loadbalancer.server.port=8080"
    volumes:
      - seesee-data:/data
    environment:
      SEESEE_ADMIN_PASSWORD: "your-secure-password"
      SEESEE_BASE_URL: "https://seesee.example.com"
```

### SMTP port

Reverse proxies handle HTTP traffic. For SMTP (port 2525), you have two options:

1. **Expose directly:** Map port 2525 to the host (`-p 2525:2525`). Suitable when SMTP clients are on your internal network.
2. **TCP proxy:** Use nginx stream module or HAProxy for TCP-level proxying if you need SMTP accessible from outside.

```nginx
# nginx stream block for SMTP TCP proxy
stream {
    server {
        listen 2525;
        proxy_pass 127.0.0.1:2525;
    }
}
```

## Updating

To update SeeSee to the latest version:

```bash
docker compose pull
docker compose up -d
```

SeeSee handles database migrations automatically on startup — no manual steps required.

## Backups

Back up the SQLite database by copying the file from the volume:

```bash
# With named volume
docker run --rm -v seesee-data:/data -v $(pwd):/backup \
  alpine cp /data/seesee.db /backup/seesee-backup.db

# With bind mount
cp /opt/seesee/data/seesee.db /backups/seesee-$(date +%Y%m%d).db
```

SQLite uses WAL mode, so copying the file while SeeSee is running is safe for read-consistent backups. For guaranteed consistency, you can also stop the container briefly.
