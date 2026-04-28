# Playbook 02 – Build and Publish App AMI

Builds the app AMI from `packer/app.pkr.hcl` on top of the base AMI. The app
template reads the base AMI ID from SSM at build time — the base must be
published before running this.

## Prerequisites

- Base AMI published (Playbook 01 complete)
- `/ops-lab/images/base-ami-id` populated in SSM Parameter Store

## Steps

### 1. Confirm the base AMI is published

```bash
aws ssm get-parameter --name /ops-lab/images/base-ami-id --region ap-southeast-2
```

If this returns a valid `ami-*` value, proceed.

### 2. Validate the template

```bash
packer validate -var-file=packer/variables.pkrvars.hcl packer/app.pkr.hcl
```

### 3. Build the AMI

```bash
packer build -var-file=packer/variables.pkrvars.hcl packer/app.pkr.hcl
```

Packer will:
- Read the base AMI ID from `/ops-lab/images/base-ami-id`
- Launch a `t3.small` builder from that base image
- Run `install_deps.sh` (Python 3.11, FastAPI, systemd unit) and `verify_build.sh`
- Create the app AMI and terminate the builder (~10–15 min)

### 4. Publish to Parameter Store

```bash
python scripts/publish_ami.py --ami-id ami-<id-from-packer-output> --type app
```

This writes:
- `/ops-lab/images/app-ami-id` → AMI ID
- `/ops-lab/images/app-ami-version` → build timestamp

### 5. Verify

```bash
python scripts/verify_ami.py --type app
```

### 6. Confirm downstream pickup

The `aws-3tier-platform` ASG reads `/ops-lab/images/app-ami-id` on its next
deploy. No changes needed there — the new AMI is live from the next instance
refresh or stack deploy.

## Rebuilding app only

If only app dependencies changed (not OS hardening or agents), rebuild app
only — skip Playbook 01. The existing base AMI in SSM is reused automatically.

## Rebuilding both layers

If OS-level changes were made (harden.sh, install_cw_agent.sh, kernel params):

1. Run Playbook 01 — build and publish new base
2. Run this playbook — app picks up the new base from SSM automatically
