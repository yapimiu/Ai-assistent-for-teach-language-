# Transfer project to server

## Option A: rsync (recommended)

From your local machine (where the repo is):

```bash
# 1. Exclude sensitive and generated files
rsync -avz --delete \
  --exclude='.git' \
  --exclude='.venv' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='.pytest_cache' \
  --exclude='backups/' \
  --exclude='.env' \
  -e ssh \
  ./ user@your-server:~/romana/
```

⚠️ **Important**: `.env` is excluded because it contains secrets. Create it directly on the server.

## Option B: git clone on server

```bash
ssh user@your-server
mkdir ~/romana && cd ~/romana
git clone <your-repo-url> .
```

Then create `.env` on the server (see deploy/deploy.md "Secrets setup").

## Option C: zip and upload

```bash
# Locally: create archive excluding secrets
zip -r romana-deploy.zip . \
  -x "*.git*" -x "*.venv*" -x "*__pycache__*" \
  -x "*.pyc" -x "*.pytest_cache*" -x "backups/*" -x ".env"

# Upload
scp romana-deploy.zip user@your-server:~/

# On server
ssh user@your-server
unzip romana-deploy.zip -d ~/romana/
```

## Server checklist after transfer

1. [ ] `.env` created with real `TELEGRAM_BOT_TOKEN`, `OPENROUTER_API_KEY`, strong `POSTGRES_PASSWORD`
2. [ ] `./deploy/init-server.sh` run (or manual Docker installation)
3. [ ] `docker compose -f deploy/docker-compose.prod.yml up -d --build`
4. [ ] `curl http://localhost:8000/health` → `{"status":"ok"}`
5. [ ] `curl http://localhost:8000/ready` → `{"status":"ready"}`
6. [ ] `docker compose -f deploy/docker-compose.prod.yml logs -f bot` → no errors, polling started
7. [ ] Send `/start` to your bot in Telegram → response received
8. [ ] nginx installed, certbot certificates obtained, `deploy/nginx.conf` configured with your domain
9. [ ] `ufw` or firewall: allow 22 (SSH), 80 (HTTP), 443 (HTTPS) only
10. [ ] First `./deploy/backup.sh` run to verify backup works
