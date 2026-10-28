# Production deployment (VPS)

Prepared instructions for a single VPS running the compose stack (`db`, `migrate`, `api`, `bot`).

## Prerequisites

- Ubuntu 22.04+ (or similar Linux distribution)
- Docker Engine and the Docker Compose plugin (`docker compose version` must work)
- Git
- nginx with HTTPS (certbot), if the API is exposed publicly

## Secrets setup

```bash
cp .env.example .env
```

Edit `.env` on the server and fill in at least:

- `TELEGRAM_BOT_TOKEN` (from BotFather)
- `OPENROUTER_API_KEY`
- `POSTGRES_PASSWORD` (change the default before the first deploy)

Never commit `.env`, never paste its contents into logs or chats. `.env` is gitignored.

## First deploy on fresh server

Option A (scripted, run once):

```bash
git clone <repo-url> ~/romana
cd ~/romana
sudo ./deploy/init-server.sh      # installs Docker, creates ~/romana/backups, systemd unit romana-compose
# create .env (see "Secrets setup") if not done yet, then:
sudo systemctl start romana-compose
```

Option B (manual):

```bash
docker compose -f deploy/docker-compose.prod.yml up -d --build
```

Verify:

```bash
docker compose -f deploy/docker-compose.prod.yml ps
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

`/health` checks that the process is alive; `/ready` checks readiness (including the database).

## HTTPS with nginx

1. Install nginx and certbot:

   ```bash
   sudo apt-get install -y nginx certbot python3-certbot-nginx
   ```

2. Copy the config and replace `example.com` with your domain:

   ```bash
   sudo cp deploy/nginx.conf /etc/nginx/sites-available/romana
   sudo sed -i 's/example.com/your.domain.tld/g' /etc/nginx/sites-available/romana
   sudo ln -s /etc/nginx/sites-available/romana /etc/nginx/sites-enabled/romana
   sudo rm -f /etc/nginx/sites-enabled/default
   ```

3. Obtain Let's Encrypt certificates (see https://certbot.eff.org for your OS):

   ```bash
   sudo certbot certonly --nginx -d your.domain.tld
   ```

   The certificate paths in `nginx.conf` must match `/etc/letsencrypt/live/<domain>/`.

4. Check and reload:

   ```bash
   sudo nginx -t && sudo systemctl reload nginx
   curl https://your.domain.tld/health
   ```

The API port `8000` is published by compose. Keep it closed to the internet
(`ufw` allow 80/443 and SSH only); nginx reaches it on `127.0.0.1:8000`.

## Routine updates

After pushing changes to the repository, on the server:

```bash
cd ~/romana
./deploy/deploy.sh
```

The script runs `git pull --ff-only`, takes a DB backup (`./deploy/backup.sh`, the deploy stops if it fails),
rebuilds the images, runs `up -d`, and prunes dangling images.

## Backup and restore

Backup (from the repository root):

```bash
./deploy/backup.sh
```

The dump is written to `./backups/romana_YYYYMMDD_HHMMSS.sql.gz`.
Keep backups off the server as well (copy them to a separate location).

Restore (from the repository root; applies into the existing `romana` database,
so take a fresh backup first):

```bash
./deploy/restore.sh backups/romana_*.sql.gz
```

Pass exactly one backup file.

## Notes

- **Telegram mode: polling.** Bot uses polling (`python -m app.bot`). The Telegram webhook is NOT configured in V1.
  No webhook URL, no public Telegram callback and no inbound port forwarding are needed for Telegram.
- **Reverse proxy / HTTPS.** The API port is bound to `127.0.0.1:8000:8000` so the host nginx can reach it.
  Terminate HTTPS in nginx. Do not expose port 8000 directly to the internet; restrict it with a firewall (e.g. ufw).
- **Bot healthcheck.** Disabled for the `bot` service (it has no HTTP port).
- **Logs.** Services use the `json-file` driver with `max-size: 10m` and `max-file: 3`.
  View logs with `docker compose -f deploy/docker-compose.prod.yml logs -f <service>`.

## Troubleshooting

- **Bot doesn't respond:** check the bot logs:

  ```bash
  docker compose -f deploy/docker-compose.prod.yml logs -f bot
  ```

  Verify that `TELEGRAM_BOT_TOKEN` in `.env` is correct and that only one bot instance is polling this token.
- **API not ready:** `docker compose -f deploy/docker-compose.prod.yml logs -f api` and
  `docker compose -f deploy/docker-compose.prod.yml logs migrate` (migrations).
- **Stack not started after reboot:** `systemctl status romana-compose`.
