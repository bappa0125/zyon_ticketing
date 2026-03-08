# Deployment Guide

The GitHub Actions pipeline deploys the app to a server via SSH when you push to `main`.

## Pipeline flow

1. **Lint** → **Test** → **Build** (push images to GHCR)
2. **Deploy** (SSH to server, pull images, `docker compose up`)

## Server setup

1. **Provision a server** (DigitalOcean, AWS EC2, etc.) with:
   - Docker and Docker Compose
   - SSH access

2. **Clone the repo** on the server:
   ```bash
   git clone -b develop https://github.com/bappa0125/zyon_ticketing.git ~/zyon_ticketing
   cd ~/zyon_ticketing
   ```

3. **Make GHCR images accessible:**
   - In GitHub: **Settings → Packages** → set your packages to **Public**, or
   - Create a Personal Access Token (PAT) with `read:packages` and add it as `GHCR_TOKEN` secret

## GitHub Secrets

In the repo: **Settings → Secrets and variables → Actions**, add:

| Secret | Description |
|--------|-------------|
| `DEPLOY_HOST` | Server hostname or IP |
| `DEPLOY_USER` | SSH username |
| `DEPLOY_SSH_KEY` | Private SSH key for authentication |
| `GHCR_TOKEN` | PAT with `read:packages` (if images are private) |
| `OPENROUTER_API_KEY` | Your OpenRouter API key |
| `DEPLOY_PATH` | (Optional) Path to repo on server, e.g. `~/zyon_ticketing` |

## GitHub Environment

1. Create an environment named **production**:
   - Repo **Settings → Environments → New environment** → name: `production`
2. The deploy job uses `environment: production`, so it only runs when that environment exists and approves.

## After setup

Each push to `develop` will:

- Run lint and tests
- Build and push Docker images to GHCR
- SSH to your server and run `docker compose -f docker-compose.deploy.yml pull && up -d`

Your app will be available at `http://<your-server-ip>` (port 80).
