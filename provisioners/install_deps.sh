#!/usr/bin/env bash
set -euo pipefail

# AWS_DEFAULT_REGION is injected by Packer.

dnf install -y python3.11 python3.11-pip

# Ensure python3 resolves to 3.11 on this image.
alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1
alternatives --set python3 /usr/bin/python3.11

python3.11 -m pip install --upgrade pip --quiet
python3.11 -m pip install fastapi "uvicorn[standard]" boto3 --quiet

# App directory layout. Code is deployed separately at runtime —
# the AMI only provides the runtime environment.
mkdir -p /opt/app/{src,config,logs}
chmod 755 /opt/app /opt/app/src /opt/app/config
chmod 775 /opt/app/logs

cat > /etc/systemd/system/app.service << 'EOF'
[Unit]
Description=FastAPI Application
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ec2-user
WorkingDirectory=/opt/app
ExecStart=/usr/bin/python3.11 -m uvicorn src.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
# Enable so it starts on boot once app code is present; does not start now.
systemctl enable app.service
