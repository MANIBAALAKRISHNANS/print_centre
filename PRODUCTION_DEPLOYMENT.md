# Production Deployment Guide — PrinterCentre

This document outlines the steps required to deploy the PrinterCentre print management system in a production hospital environment.

## 1. Security Initialization
Before starting the server, you **must** generate cryptographically secure secrets.

```bash
# Generate JWT_SECRET_KEY
openssl rand -hex 32

# Generate ADMIN_CLEANUP_TOKEN
openssl rand -hex 32
```

Create a `.env` file in the `backend/` directory by copying `.env.example` and filling in the values:
- Set `ENVIRONMENT=production`
- Set `JWT_SECRET_KEY` and `ADMIN_CLEANUP_TOKEN` to the values generated above.
- Set `ALLOWED_ORIGINS` to the exact URL(s) of your frontend (e.g., `https://printhub.hospital.internal`).

## 2. Admin User Setup
Initialize your first administrative account via the CLI:

```bash
cd backend
python setup_admin.py --user admin --password YOUR_STRONG_PASSWORD
```

## 3. Reverse Proxy Configuration (Nginx)
In production, use Nginx to terminate SSL and proxy requests to the FastAPI backend.

```nginx
server {
    listen 443 ssl http2;
    server_name printhub.hospital.internal;

    ssl_certificate /etc/letsencrypt/live/printhub.hospital.internal/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/printhub.hospital.internal/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Enable large uploads for A4 documents
        client_max_body_size 50M;
    }
}
```

## 4. Systemd Service File
Create a service file at `/etc/systemd/system/printhub.service`:

```ini
[Unit]
Description=PrinterCentre Backend
After=network.target

[Service]
User=printcenter
Group=printcenter
WorkingDirectory=/opt/printercentre/backend
EnvironmentFile=/opt/printercentre/backend/.env
ExecStart=/opt/printercentre/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000

[Install]
WantedBy=multi-user.target
```

## 5. Deployment Checklist
- [ ] Environment is set to `production`.
- [ ] `JWT_SECRET_KEY` is unique and at least 32 characters.
- [ ] `ALLOWED_ORIGINS` is strictly defined (no wildcards).
- [ ] Admin password has been changed from default.
- [ ] Audit logging is verified (check `GET /admin/audit-logs`).
- [ ] Database path is on a volume with daily backups.
- [ ] SSL certificates are valid and auto-renewing.
- [ ] Rate limiting is active (test 10+ login attempts).
- [ ] Agent registration flow tested with activation code.
