#!/usr/bin/env bash
set -euo pipefail

# VERIFY_APP is injected by Packer: "true" for app layer, "false" for base.

FAILED=0

pass() { echo "[PASS] $1"; }
fail() { echo "[FAIL] $1"; FAILED=$((FAILED + 1)); }

check() {
  local desc="$1"
  if eval "$2" &>/dev/null; then pass "${desc}"; else fail "${desc}"; fi
}

# --- Base layer checks (always run) ---

check "SSM agent binary present"          "test -f /usr/bin/amazon-ssm-agent"
check "SSM agent service enabled"         "systemctl is-enabled amazon-ssm-agent"
check "CloudWatch agent binary present"   "test -f /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent"
check "CloudWatch agent service enabled"  "systemctl is-enabled amazon-cloudwatch-agent"
check "CloudWatch agent config present"   "test -f /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json"
check "AWS CLI v2 installed"              "aws --version 2>&1 | grep -q 'aws-cli/2'"
check "fail2ban installed"               "command -v fail2ban-server"
check "fail2ban service enabled"          "systemctl is-enabled fail2ban"
check "SSH root login disabled"           "grep -q 'PermitRootLogin no' /etc/ssh/sshd_config.d/99-hardening.conf"
check "SSH password auth disabled"        "grep -q 'PasswordAuthentication no' /etc/ssh/sshd_config.d/99-hardening.conf"

# --- App layer checks ---

if [[ "${VERIFY_APP:-false}" == "true" ]]; then
  check "Python 3.11 installed"           "python3.11 --version"
  check "FastAPI importable"              "python3.11 -c 'import fastapi'"
  check "Uvicorn importable"              "python3.11 -c 'import uvicorn'"
  check "Boto3 importable"               "python3.11 -c 'import boto3'"
  check "/opt/app directory present"      "test -d /opt/app"
  check "App service unit present"        "test -f /etc/systemd/system/app.service"
  check "App service enabled"             "systemctl is-enabled app"
fi

if [[ $FAILED -gt 0 ]]; then
  echo ""
  echo "Build verification failed: ${FAILED} check(s) failed."
  exit 1
fi

echo ""
echo "All checks passed."
