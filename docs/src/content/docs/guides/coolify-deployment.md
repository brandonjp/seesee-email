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

### 5. Persistent storage

Coolify manages Docker volumes automatically. The `seesee-data` volume in the Compose file ensures your SQLite database persists across deployments and restarts.

To verify the volume is mounted:
1. Go to **Storages** in the service settings
2. Confirm `seesee-data:/data` is listed

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
