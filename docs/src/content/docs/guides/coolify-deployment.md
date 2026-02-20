---
title: Coolify Deployment
description: Deploy SeeSee on Coolify with persistent storage and SSL.
---

[Coolify](https://coolify.io) is an open-source, self-hosted platform for deploying applications. SeeSee's Docker Compose file is Coolify-compatible out of the box.

## Prerequisites

- A Coolify instance (v4+) running on your server
- A domain name pointed at your server (for SSL)

## Step-by-step setup

### 1. Create a new service

1. In your Coolify dashboard, click **New Resource**
2. Select **Docker Compose**
3. Choose your target server

### 2. Add the Docker Compose configuration

Paste the following into the Compose editor:

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

### 3. Configure environment variables

In the Coolify **Environment Variables** section, set:

| Variable | Value | Notes |
|----------|-------|-------|
| `SEESEE_ADMIN_PASSWORD` | *(your password)* | **Required** — choose a strong password |
| `SEESEE_SECRET_KEY` | *(random string)* | For session cookie signing |
| `SEESEE_BASE_URL` | `https://seesee.yourdomain.com` | Must match your domain |

Optional variables (with defaults):

| Variable | Default | Description |
|----------|---------|-------------|
| `SEESEE_SMTP_ENABLED` | `true` | Enable SMTP capture |
| `SEESEE_RETENTION_MAX_COUNT` | `1000` | Max emails per app |
| `SEESEE_RETENTION_MAX_AGE_DAYS` | `90` | Email age limit |
| `SEESEE_RETENTION_MAX_STORAGE_MB` | `500` | Storage cap |

See the [Configuration Reference](/reference/configuration/) for all available variables.

### 4. Domain and SSL setup

1. Go to the **Domain** settings for your service
2. Add your domain (e.g., `seesee.yourdomain.com`)
3. Coolify will automatically provision an SSL certificate via Let's Encrypt
4. Set the container port to `8080` for HTTP routing
5. Update `SEESEE_BASE_URL` to match your domain with `https://`

### 5. Persistent storage (required)

The `seesee-data` volume in the Compose file tells Docker where to store data, but **you must verify that Coolify has created a matching storage mount**. Without this, your apps and emails will be lost on every redeploy.

1. Go to the **Storages** tab in your SeeSee service settings
2. If a mount for `/data` is already listed, you're set
3. If **no mount is listed**, click **Add** and configure:

| Field | Value |
|-------|-------|
| **Name** | `seesee-data` |
| **Source Path** | *(leave empty for a Docker named volume, or use a host path like `/opt/seesee/data`)* |
| **Destination Path** | `/data` |

4. Redeploy after adding the storage

:::caution
If you skip this step, SeeSee will appear to work but will lose all data (apps, emails, settings) every time you redeploy. The Compose file's `volumes:` section alone is not always sufficient — Coolify's **Storages** UI is the authoritative source for volume configuration.
:::

### 6. SMTP port

Coolify's built-in proxy handles HTTP/HTTPS traffic. For SMTP (port 2525), you need to expose the port directly:

1. In the service settings, ensure port `2525` is mapped
2. The SMTP port will be available at `your-server-ip:2525`
3. SMTP does not go through the Coolify proxy — it's a direct TCP connection

### 7. Deploy

Click **Deploy** and wait for the health check to pass. Once healthy:

1. Visit `https://seesee.yourdomain.com`
2. Log in with your admin credentials
3. Create your first app and start logging emails

## Updating

Coolify can pull the latest image automatically:

1. Go to your SeeSee service settings
2. Click **Redeploy** or enable **Auto Deploy** if using a webhook
3. SeeSee handles database migrations on startup — no manual steps needed

## Troubleshooting

### Service won't start

- Check that `SEESEE_ADMIN_PASSWORD` is set — SeeSee requires it
- Review container logs in Coolify's **Logs** tab
- Ensure the volume mount is writable

### Can't access the UI

- Verify your domain DNS points to the Coolify server
- Check that Coolify's proxy is routing to port `8080`
- Confirm SSL certificate provisioning completed

### SMTP not reachable

- Port 2525 must be opened in your server's firewall
- SMTP traffic bypasses Coolify's HTTP proxy — connect directly to the server IP on port 2525
- Check that `SEESEE_SMTP_ENABLED` is not set to `false`

### Data lost after redeploy

If your apps and emails disappear after hitting **Redeploy** in Coolify, the database volume is not persisting. This is a Coolify configuration issue, not a SeeSee bug.

**Step 1: Check the debug endpoint**

SeeSee includes a built-in persistence diagnostics endpoint:

```bash
curl -u admin:your-password \
  https://seesee.yourdomain.com/api/v1/admin/debug/persistence
```

Key fields to check:

| Field | What to look for |
|-------|------------------|
| `volume_mounted` | Must be `true`. If `false`, no volume is mounted at `/data` |
| `app_count` | Should match your expected number of apps |
| `hostname` | Changes after each redeploy (expected — it's the container ID), but data should still persist if the volume is mounted |
| `mount_info` | Should show a device like `overlay` or a named volume, not the root filesystem |

**Step 2: Verify Coolify Storages**

1. Go to your SeeSee service → **Storages** tab
2. Confirm there is an entry with **Destination Path** set to `/data`
3. If missing, add one (see [Persistent storage](#5-persistent-storage-required) above)
4. Redeploy after adding

**Step 3: Check startup logs**

SeeSee logs persistence diagnostics on every startup. In Coolify's **Logs** tab, look for:

```
SeeSee Persistence Diagnostics
Database file: NEW ...
DATABASE APPEARS FRESHLY CREATED (0 apps)
```

If you see this after a redeploy where you expected existing data, the volume is not mounted correctly.

**Common Coolify volume pitfalls:**

- **Storages vs. Compose volumes:** Declaring `volumes:` in the Docker Compose alone may not be enough. Coolify's **Storages** UI is the authoritative source.
- **Volume name prefixing:** Coolify prefixes volume names with the project/service name. Renaming your service or project creates a new volume, leaving old data in the old volume.
- **Bind mounts for maximum control:** For the most predictable behavior, use a host path in Coolify Storages (e.g., Source Path: `/opt/seesee/data`, Destination Path: `/data`). This makes the database file directly visible on the host.
