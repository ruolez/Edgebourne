#!/usr/bin/env bash
#
# EdgeBourne — one-file installer for a clean Ubuntu 24.04 server.
#
#   curl -fsSL https://raw.githubusercontent.com/ruolez/Edgebourne/main/install.sh | sudo bash
#
# Options:
#   1) Install       — Docker + app + Let's Encrypt SSL (auto-renewing)
#   2) Update        — pull latest from GitHub, keep all data, apply migrations
#   3) Renew SSL     — force a certificate renewal check right now
#   4) Remove        — cleanly remove the installation
#
set -euo pipefail

REPO_URL="https://github.com/ruolez/Edgebourne.git"
APP_DIR="/opt/edgebourne"
BACKUP_DIR="/var/backups/edgebourne"
WEBROOT="/var/www/certbot"
RENEW_HOOK="/etc/letsencrypt/renewal-hooks/deploy/edgebourne-reload.sh"
KEEP_BACKUPS=14

C_TEAL='\033[0;36m'; C_RED='\033[0;31m'; C_GRN='\033[0;32m'; C_YLW='\033[1;33m'; C_OFF='\033[0m'
log()  { echo -e "${C_TEAL}[edgebourne]${C_OFF} $*"; }
ok()   { echo -e "${C_GRN}[ok]${C_OFF} $*"; }
warn() { echo -e "${C_YLW}[warn]${C_OFF} $*"; }
die()  { echo -e "${C_RED}[error]${C_OFF} $*" >&2; exit 1; }

# stdin may be a pipe (curl | bash) — always talk to the terminal.
ask() { # ask "Prompt" [default] -> $REPLY
  local prompt="$1" default="${2:-}"
  if [ -n "$default" ]; then prompt="$prompt [$default]"; fi
  read -r -p "$(echo -e "${C_TEAL}?${C_OFF} ") $prompt: " REPLY < /dev/tty || true
  REPLY="${REPLY:-$default}"
}

confirm() { # confirm "Prompt" -> 0/1
  ask "$1 (y/n)" "n"
  [[ "$REPLY" =~ ^[Yy] ]]
}

need_root() { [ "$(id -u)" -eq 0 ] || die "Run as root: sudo bash install.sh"; }

compose() { (cd "$APP_DIR" && docker compose "$@"); }

env_get() { grep -E "^$1=" "$APP_DIR/.env" 2>/dev/null | head -1 | cut -d= -f2- || true; }

# ---------------------------------------------------------------- prerequisites

install_prereqs() {
  log "Installing prerequisites (git, curl, certbot, docker)…"
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq ca-certificates curl git certbot >/dev/null
  if ! command -v docker >/dev/null 2>&1; then
    log "Installing Docker from get.docker.com…"
    curl -fsSL https://get.docker.com | sh >/dev/null
  fi
  systemctl enable --now docker >/dev/null 2>&1 || true
  ok "Prerequisites ready."
}

# ---------------------------------------------------------------- DNS / domain

public_ip() { curl -fsS --max-time 10 https://api.ipify.org || curl -fsS --max-time 10 https://ifconfig.me; }

check_dns() { # check_dns <name> <expected-ip>
  local name="$1" want="$2" got
  got="$(getent ahostsv4 "$name" 2>/dev/null | awk '{print $1; exit}')"
  if [ -z "$got" ]; then
    warn "DNS: $name does not resolve yet."
    return 1
  elif [ "$got" != "$want" ]; then
    warn "DNS: $name resolves to $got but this server's public IP is $want."
    return 1
  fi
  ok "DNS: $name → $got"
}

prompt_domain() {
  local ip; ip="$(public_ip)" || die "Could not determine this server's public IP."
  log "This server's public IP: $ip"
  while true; do
    ask "Domain name for the site (e.g. edgebourne.com)"
    DOMAIN="$REPLY"
    [ -n "$DOMAIN" ] || { warn "A domain is required for SSL."; continue; }
    SERVER_NAMES="$DOMAIN"
    CERT_ARGS=(-d "$DOMAIN")
    if confirm "Also serve www.$DOMAIN?"; then
      SERVER_NAMES="$DOMAIN www.$DOMAIN"
      CERT_ARGS+=(-d "www.$DOMAIN")
    fi
    local all_ok=0
    for name in $SERVER_NAMES; do check_dns "$name" "$ip" || all_ok=1; done
    if [ "$all_ok" -eq 0 ]; then break; fi
    if confirm "DNS is not pointing here (yet). Continue anyway? Certificate issuance will fail until DNS is correct"; then break; fi
  done
}

render_ssl_conf() { # render_ssl_conf <domain> <server-names>
  sed -e "s/__DOMAIN__/$1/g" -e "s/__SERVER_NAMES__/$2/g" \
    "$APP_DIR/nginx/nginx-ssl.conf.template" > "$APP_DIR/nginx/nginx-ssl.conf"
}

install_renew_hook() {
  mkdir -p "$(dirname "$RENEW_HOOK")"
  cat > "$RENEW_HOOK" <<'EOF'
#!/bin/sh
# Reload EdgeBourne's nginx after a successful certificate renewal.
docker exec edgebourne-nginx nginx -s reload || true
EOF
  chmod +x "$RENEW_HOOK"
  systemctl enable --now certbot.timer >/dev/null 2>&1 || true
}

open_firewall() {
  if command -v ufw >/dev/null 2>&1 && ufw status | grep -q "Status: active"; then
    log "Opening ports 80/443 in ufw…"
    ufw allow 80/tcp >/dev/null; ufw allow 443/tcp >/dev/null
  fi
}

wait_for_health() { # wait_for_health <url>
  local url="$1" i
  for i in $(seq 1 30); do
    if curl -fsk --max-time 3 "$url" >/dev/null 2>&1; then ok "Healthy: $url"; return 0; fi
    sleep 2
  done
  die "App did not become healthy at $url — check: cd $APP_DIR && docker compose logs"
}

# ---------------------------------------------------------------- backup

backup_db() { # backup_db [target-file]
  local target="${1:-$BACKUP_DIR/edgebourne-$(date +%Y%m%d-%H%M%S).sql.gz}"
  mkdir -p "$(dirname "$target")"
  if docker ps --format '{{.Names}}' | grep -q '^edgebourne-postgres$'; then
    log "Backing up PostgreSQL → $target"
    docker exec edgebourne-postgres pg_dump -U edgebourne edgebourne | gzip > "$target"
    ok "Backup complete ($(du -h "$target" | cut -f1))."
  else
    warn "Postgres container not running — skipping backup."
  fi
}

prune_backups() {
  ls -1t "$BACKUP_DIR"/edgebourne-*.sql.gz 2>/dev/null | tail -n +$((KEEP_BACKUPS + 1)) | xargs -r rm -f
}

# ---------------------------------------------------------------- install

cmd_install() {
  need_root
  [ -d "$APP_DIR/.git" ] && die "Already installed at $APP_DIR — use the Update option instead."

  install_prereqs
  log "Cloning $REPO_URL → $APP_DIR"
  git clone -q "$REPO_URL" "$APP_DIR"

  prompt_domain
  ask "Let's Encrypt notification email (blank for none)"
  LE_EMAIL="$REPLY"
  ask "Admin panel password" "$(openssl rand -hex 8)"
  ADMIN_PW="$REPLY"

  log "Writing $APP_DIR/.env"
  cat > "$APP_DIR/.env" <<EOF
SECRET_KEY=$(openssl rand -hex 32)
POSTGRES_PASSWORD=$(openssl rand -hex 16)
ADMIN_INITIAL_PASSWORD=$ADMIN_PW
APP_PORT=80
DOMAIN=$DOMAIN
SERVER_NAMES=$SERVER_NAMES
EOF
  chmod 600 "$APP_DIR/.env"

  mkdir -p "$WEBROOT"
  open_firewall

  log "Starting the stack (HTTP) to answer the certificate challenge…"
  compose -f docker-compose.yml -f docker-compose.certbot.yml up -d --build
  wait_for_health "http://localhost/healthz"

  log "Requesting Let's Encrypt certificate for: $SERVER_NAMES"
  local email_args=(--register-unsafely-without-email)
  [ -n "$LE_EMAIL" ] && email_args=(-m "$LE_EMAIL")
  certbot certonly --webroot -w "$WEBROOT" "${CERT_ARGS[@]}" \
    --non-interactive --agree-tos "${email_args[@]}" \
    || die "Certificate issuance failed — verify DNS points at this server, then re-run Install."

  log "Switching to HTTPS…"
  render_ssl_conf "$DOMAIN" "$SERVER_NAMES"
  echo "COMPOSE_FILE=docker-compose.yml:docker-compose.prod.yml" >> "$APP_DIR/.env"
  compose up -d --remove-orphans
  install_renew_hook
  wait_for_health "https://$DOMAIN/healthz"

  echo
  ok  "EdgeBourne is live."
  echo -e "   Site:   ${C_GRN}https://$DOMAIN${C_OFF}"
  echo -e "   Admin:  ${C_GRN}https://$DOMAIN/admin${C_OFF}  (user: admin  password: $ADMIN_PW)"
  echo -e "   SSL:    auto-renews via certbot.timer (deploy hook reloads nginx)"
  echo -e "   Update: re-run this script and choose Update"
}

# ---------------------------------------------------------------- update

cmd_update() {
  need_root
  [ -d "$APP_DIR/.git" ] || die "No installation found at $APP_DIR — run Install first."

  backup_db
  prune_backups

  log "Pulling latest code from GitHub…"
  git -C "$APP_DIR" fetch -q origin main
  git -C "$APP_DIR" reset -q --hard origin/main

  local domain server_names
  domain="$(env_get DOMAIN)"; server_names="$(env_get SERVER_NAMES)"
  if [ -n "$domain" ] && [ -f "$APP_DIR/nginx/nginx-ssl.conf.template" ]; then
    render_ssl_conf "$domain" "${server_names:-$domain}"
  fi

  log "Rebuilding and restarting (DB migrations run automatically at startup)…"
  compose up -d --build --remove-orphans

  log "Cleaning up unused Docker images…"
  docker image prune -f >/dev/null

  wait_for_health "http://localhost/healthz"
  [ -n "$domain" ] && wait_for_health "https://$domain/healthz"
  ok "Update complete. Backup saved in $BACKUP_DIR (last $KEEP_BACKUPS kept)."
}

# ---------------------------------------------------------------- renew

cmd_renew() {
  need_root
  command -v certbot >/dev/null 2>&1 || die "certbot is not installed — run Install first."
  log "Running certificate renewal (renews when within 30 days of expiry)…"
  certbot renew
  docker exec edgebourne-nginx nginx -s reload >/dev/null 2>&1 || true
  echo
  certbot certificates
  ok "Renewal check complete. Automatic renewal stays active via certbot.timer."
}

# ---------------------------------------------------------------- remove

cmd_remove() {
  need_root
  [ -d "$APP_DIR" ] || die "Nothing to remove — $APP_DIR does not exist."

  warn "This removes the app, its containers AND all data volumes (database, uploads)."
  ask 'Type REMOVE to confirm'
  [ "$REPLY" = "REMOVE" ] || die "Aborted."

  if confirm "Save a final database backup to /root first?"; then
    backup_db "/root/edgebourne-final-$(date +%Y%m%d-%H%M%S).sql.gz"
  fi

  log "Stopping and deleting containers + volumes…"
  compose down -v --remove-orphans || true
  rm -rf "$APP_DIR"
  rm -f "$RENEW_HOOK"

  local domain
  domain="$(certbot certificates 2>/dev/null | awk '/Certificate Name/ {print $3}' | head -1 || true)"
  if [ -n "$domain" ] && confirm "Also delete the Let's Encrypt certificate ($domain)?"; then
    certbot delete --cert-name "$domain" --non-interactive || true
  fi
  ok "EdgeBourne removed. (Docker itself and $BACKUP_DIR were left in place.)"
}

# ---------------------------------------------------------------- menu

echo
echo -e "${C_TEAL}  ══════════════════════════════════${C_OFF}"
echo -e "${C_TEAL}   EdgeBourne — server installer${C_OFF}"
echo -e "${C_TEAL}  ══════════════════════════════════${C_OFF}"
echo "   1) Install (clean Ubuntu 24 server)"
echo "   2) Update from GitHub (keeps all data)"
echo "   3) Renew SSL certificate now"
echo "   4) Remove installation"
echo "   5) Exit"
echo
ask "Choose an option" "1"
case "$REPLY" in
  1) cmd_install ;;
  2) cmd_update ;;
  3) cmd_renew ;;
  4) cmd_remove ;;
  *) echo "Bye." ;;
esac
