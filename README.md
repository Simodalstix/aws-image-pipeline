# aws-image-pipeline

Golden AMI baking pipeline for the ops-lab platform. Produces hardened,
pre-configured AMIs using Packer and publishes AMI IDs to SSM Parameter Store
so downstream stacks always launch from a known-good image without hardcoding
any AMI ID.

Part of a modular AWS ops platform alongside `aws-ops-networking`,
`aws-ops-observability`, and `aws-3tier-platform`.

---

## How it works

```
Developer runs packer build (or CodeBuild triggers automatically)
  → Packer launches t3.small builder in public subnet
  → Provisioners run: install CW agent, harden OS, install app runtime
  → Packer creates AMI, terminates builder
  → scripts/publish_ami.py writes AMI ID to /ops-lab/images/{type}-ami-id
  → Downstream ASG launch templates read from Parameter Store on next deploy
```

## Image layers

| Layer | Template | What it adds |
|-------|----------|-------------|
| Base  | `packer/base.pkr.hcl` | CloudWatch agent, OS hardening (fail2ban, SSH config, sysctl), AWS CLI v2 |
| App   | `packer/app.pkr.hcl`  | Python 3.11, FastAPI + uvicorn, `/opt/app/` structure, systemd service unit |

Build base first. App builds on top of the base AMI ID written to SSM.

## SSM parameters

| Parameter | Written by | Read by |
|-----------|-----------|---------|
| `/ops-lab/networking/subnet/public-0` | aws-ops-networking | Packer (builder subnet) |
| `/ops-lab/networking/ssm-sg-id` | aws-ops-networking | (available, not used by builder) |
| `/ops-lab/shared/cw-agent-config-ssm-path` | aws-ops-observability | `install_cw_agent.sh` |
| `/ops-lab/images/base-ami-id` | `publish_ami.py` | `app.pkr.hcl`, aws-3tier-platform |
| `/ops-lab/images/base-ami-version` | `publish_ami.py` | ops tooling |
| `/ops-lab/images/app-ami-id` | `publish_ami.py` | aws-3tier-platform ASG |
| `/ops-lab/images/app-ami-version` | `publish_ami.py` | ops tooling |

---

## Prerequisites

- AWS credentials configured (`aws configure` or instance role)
- Packer installed — see [HashiCorp install docs](https://developer.hashicorp.com/packer/install)
- Python 3.11+ with boto3 (`pip install boto3`)
- `ImagePipelineStack` deployed (creates the `packer-builder` IAM instance profile)
- `aws-ops-networking` and `aws-ops-observability` stacks deployed

## Deploy the CDK stack

The CDK stack creates the `packer-builder` IAM instance profile and two
CodeBuild projects. Run this once before your first Packer build.

```bash
poetry install
cdk bootstrap   # first time only
cdk deploy
```

---

## Manual build flow

### 1. Build the base AMI

```bash
packer init packer/
packer validate -var-file=packer/variables.pkrvars.hcl packer/base.pkr.hcl
packer build   -var-file=packer/variables.pkrvars.hcl packer/base.pkr.hcl
```

### 2. Publish base AMI to Parameter Store

```bash
python scripts/publish_ami.py --ami-id ami-<id-from-packer-output> --type base
python scripts/verify_ami.py --type base
```

### 3. Build the app AMI

```bash
packer build -var-file=packer/variables.pkrvars.hcl packer/app.pkr.hcl
python scripts/publish_ami.py --ami-id ami-<id-from-packer-output> --type app
python scripts/verify_ami.py --type app
```

### 4. AMI lifecycle

```bash
# Preview what would be deprecated (keeps 3 most recent + current SSM AMI)
python scripts/deprecate_ami.py --type base --dry-run
python scripts/deprecate_ami.py --type base

# Permanently remove AMIs older than 90 days
python scripts/deprecate_ami.py --type base --deregister-older-than-days 90
```

## Automated builds (CodeBuild)

The CDK stack deploys two CodeBuild projects that replicate the manual steps above.
Trigger a build from the console or CLI:

```bash
aws codebuild start-build --project-name ops-lab-build-base-ami
aws codebuild start-build --project-name ops-lab-build-app-ami
```

The source must be connected to this repository in the CodeBuild project settings.

---

## Repo structure

```
packer/
  base.pkr.hcl              Base AMI template (AL2023)
  app.pkr.hcl               App AMI template (builds on base)
  variables.pkrvars.hcl     Region, instance type, IAM profile

provisioners/
  install_cw_agent.sh       Install CloudWatch agent, fetch config from SSM
  harden.sh                 SSH hardening, fail2ban, kernel params
  install_deps.sh           Python 3.11, FastAPI, /opt/app/, systemd unit
  verify_build.sh           Smoke tests (runs inside builder instance)

scripts/
  publish_ami.py            Write AMI ID + version to SSM post-build
  verify_ami.py             Confirm AMI and Parameter Store are consistent
  deprecate_ami.py          Retention policy — deprecate and deregister old AMIs

image_pipeline/
  pipeline_stack.py         CDK: IAM instance profile + CodeBuild projects
```
