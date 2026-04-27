#!/usr/bin/env bash
set -euo pipefail

dnf install -y fail2ban

# Drop-in config so the base sshd_config isn't modified directly.
cat > /etc/ssh/sshd_config.d/99-hardening.conf << 'EOF'
PermitRootLogin no
PasswordAuthentication no
X11Forwarding no
MaxAuthTries 3
LoginGraceTime 30
AllowTcpForwarding no
EOF

cat > /etc/fail2ban/jail.local << 'EOF'
[DEFAULT]
bantime  = 3600
findtime = 600
maxretry = 3

[sshd]
enabled = true
port    = ssh
filter  = sshd
logpath = /var/log/secure
EOF

# Disable services not needed on an app server.
# Suppress errors for services that may not be present on this AMI.
for svc in postfix rpcbind; do
  systemctl disable --now "${svc}" 2>/dev/null || true
done

systemctl enable fail2ban

# Kernel hardening
cat > /etc/sysctl.d/99-hardening.conf << 'EOF'
net.ipv4.conf.all.accept_redirects = 0
net.ipv4.conf.default.accept_redirects = 0
net.ipv4.conf.all.send_redirects = 0
net.ipv6.conf.all.accept_redirects = 0
net.ipv4.tcp_syncookies = 1
net.ipv4.conf.all.log_martians = 1
EOF

sysctl --system
