#!/usr/bin/env bash
set -euo pipefail

# CW_CONFIG_SSM_PATH and AWS_DEFAULT_REGION are injected by Packer.

dnf install -y amazon-cloudwatch-agent

# Fetch config from SSM and apply it. The config is stored locally on the AMI
# so the agent starts immediately on boot without needing to re-fetch.
/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
  -a fetch-config \
  -m ec2 \
  -s \
  -c "ssm:${CW_CONFIG_SSM_PATH}"

# Persist the SSM path so operators can re-fetch a newer config without
# needing to know the path (e.g. after a config update in Parameter Store).
echo "${CW_CONFIG_SSM_PATH}" > /opt/aws/amazon-cloudwatch-agent/etc/ssm-config-path

systemctl enable amazon-cloudwatch-agent
