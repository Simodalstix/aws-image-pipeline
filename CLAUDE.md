# CLAUDE.md — aws-image-pipeline

## Behavioral Guidelines

These apply to every task in this repo. They bias toward caution over speed.
For trivial tasks, use judgment.

### 1. Think Before Coding

Don't assume. Don't hide confusion. Surface tradeoffs.

Before implementing:
- State assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them — don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

For infrastructure decisions specifically:
- Name the tradeoff (cost vs automation depth, simplicity vs pipeline completeness)
- If a Packer or CDK construct choice has implications, surface them
- Don't silently pick an instance type for the Packer builder — state it and why

### 2. Simplicity First

Minimum code that solves the problem. Nothing speculative.

- No features beyond what was asked
- No abstractions for single-use constructs
- No configurability that wasn't requested
- If you write 200 lines and it could be 50, rewrite it

Ask: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

### 3. Surgical Changes

Touch only what you must. Clean up only your own mess.

When editing existing code:
- Don't improve adjacent code, comments, or formatting
- Don't refactor things that aren't broken
- Match existing style, even if you'd do it differently
- If you notice unrelated issues, mention them — don't fix them silently

When your changes create orphans:
- Remove imports/variables/constructs that YOUR changes made unused
- Don't remove pre-existing dead code unless asked

Every changed line should trace directly to the request.

### 4. Goal-Driven Execution

Define success criteria. Loop until verified.

For infrastructure tasks, replace "tests pass" with CLI or script verification:
- "Add Packer template" → verify: `packer validate` passes, AMI appears in EC2 console
- "Update Parameter Store" → verify: new AMI ID readable at `/ops-lab/images/app-ami-id`
- "Wire 3tier launch template" → verify: new ASG instance launches from updated AMI

For multi-step tasks, state a brief plan first:
```
1. [Step] → verify: [CLI check]
2. [Step] → verify: [CLI check]
3. [Step] → verify: [CLI check]
```

---

## Platform Context

I am building a modular AWS ops platform as a series of independent but
interconnected GitHub projects. This repo is the image baking pipeline —
it produces golden AMIs consumed by other platform projects, and writes
AMI IDs to SSM Parameter Store so downstream stacks always launch from
the latest baked image without touching CDK.

**Developer:** simoda
**Machine:** Beelink (Linux, Ubuntu)
**Region:** ap-southeast-2
**Account:** 820242933814
**Primary tool:** Claude Code (CLI), working directly inside this repo

---

## Existing Projects

- `aws-ops-networking` ✅ — deployed. Foundation VPC stack. Exports to
  `/ops-lab/networking/*` in SSM Parameter Store.
- `aws-ops-observability` ✅ — deployed. Shared SNS topic, CloudWatch IAM
  policy, agent config template. Exports to `/ops-lab/shared/*`.
- `aws-3tier-platform` ✅ — deployed. ALB, ASG, RDS PostgreSQL, ElastiCache.
  Primary consumer of AMIs produced by this pipeline.

## Planned Projects (not yet started)

- `aws-config-mgmt-lab` — AWS Config rules, SSM State Manager, Puppet,
  drift detection, auto-remediation.
- `aws-fargate-golden-path` — container workload platform, ECS Fargate.
- `aws-event-driven-pipeline` — SQS/Kinesis, Lambda, S3, Glue, Athena.

---

## Platform Rules (apply to every project)

- **IaC:** CDK Python with Poetry for pipeline infrastructure
- **Image baking:** HashiCorp Packer (HCL2 syntax, not legacy JSON)
- **No hardcoded ARNs or IDs anywhere** — all cross-project values go through
  SSM Parameter Store
- **SSM Parameter Store is the config bus** — this pipeline writes new AMI IDs
  to Parameter Store on every successful build; downstream stacks read from there
- **NAT:** `NONE` by default — Packer builder runs in public subnet
- **EC2 access:** SSM only — no bastions, no key pairs, Packer uses
  `communicator = "ssh"` via temporary key only during build, destroyed after
- **All projects include:**
  - CLI playbooks under `docs/cli-playbooks/`
  - Boto3 operational scripts under `scripts/`
  - This `CLAUDE.md` at repo root

---

## This Project: aws-image-pipeline

**Purpose:** Bake hardened, pre-configured golden AMIs using Packer. Publish
AMI IDs to SSM Parameter Store so downstream stacks (3-tier ASG, Fargate task
definitions, config-mgmt targets) always launch from a known-good image.

This is the connective tissue between the platform foundation and application
stacks — nothing downstream hardcodes an AMI ID.

### Image Layers

```
base AMI (Amazon Linux 2023)
   └── base.pkr.hcl
         SSM agent (pre-installed on AL2023, verified)
         CloudWatch agent (installed + configured)
         AWS CLI v2
         OS hardening (sshd config, fail2ban, unnecessary services disabled)
         └── app.pkr.hcl (inherits base)
               Python 3.11 + pip
               FastAPI + uvicorn + dependencies
               /opt/app/ directory structure
               systemd service unit for FastAPI
```

### SSM Parameters This Project Reads

```
/ops-lab/networking/subnet/public-0    → Packer builder subnet
/ops-lab/networking/ssm-sg-id         → Packer builder security group
/ops-lab/shared/cw-agent-config-ssm-path → baked into AMI at build time
```

### SSM Parameters This Project Writes

```
/ops-lab/images/base-ami-id           → latest base AMI ID
/ops-lab/images/base-ami-version      → build timestamp / version tag
/ops-lab/images/app-ami-id            → latest app AMI ID
/ops-lab/images/app-ami-version       → build timestamp / version tag
```

### What This Project Deploys

**Packer templates (not CDK — these are Packer HCL files):**
- `packer/base.pkr.hcl` — base golden AMI
- `packer/app.pkr.hcl` — app AMI built on top of base
- `packer/variables.pkrvars.hcl` — shared variables (region, instance type, subnet)

**Provisioner scripts (called by Packer during build):**
- `scripts/install_cw_agent.sh` — install and configure CloudWatch agent
- `scripts/install_deps.sh` — Python runtime, app dependencies
- `scripts/harden.sh` — OS hardening steps
- `scripts/verify_build.sh` — smoke tests run inside the builder instance

**CDK stack (pipeline infrastructure):**
- `image_pipeline/pipeline_stack.py` — optional CodePipeline/CodeBuild wrapper
  to trigger Packer builds on git push. Start manual, add pipeline later.

**Boto3 scripts:**
- `scripts/publish_ami.py` — writes new AMI IDs to SSM Parameter Store
  post-build, tags AMI with build metadata
- `scripts/verify_ami.py` — describes AMI, confirms tags and Parameter Store
  values are consistent
- `scripts/deprecate_ami.py` — marks old AMIs as deprecated, deregisters
  images older than retention window

### Build Flow

```
Developer runs packer build
   → Packer launches t3.small builder in public subnet
   → Provisioners run (install, harden, verify)
   → Packer creates AMI, terminates builder
   → scripts/publish_ami.py writes AMI ID to Parameter Store
   → 3tier ASG launch template reads /ops-lab/images/app-ami-id on next deploy
```

### On-Prem Extension

Packer can target Proxmox via the `proxmox-iso` or `proxmox-clone` builder.
The same provisioner scripts that harden and configure AWS AMIs can build
Proxmox VM templates — unified image pipeline across cloud and on-prem.
This is the on-prem story for this repo.

---

## Repo Structure

```
aws-image-pipeline/
├── CLAUDE.md
├── README.md
├── pyproject.toml                    # Poetry — CDK + boto3 deps
├── cdk.json
├── app.py                            # CDK entrypoint (pipeline infra)
├── image_pipeline/
│   ├── __init__.py
│   └── pipeline_stack.py             # CodeBuild/CodePipeline (optional phase 2)
├── packer/
│   ├── base.pkr.hcl                  # Base golden AMI
│   ├── app.pkr.hcl                   # App AMI (builds on base)
│   └── variables.pkrvars.hcl         # Shared variables
├── provisioners/
│   ├── install_cw_agent.sh
│   ├── install_deps.sh
│   ├── harden.sh
│   └── verify_build.sh
├── scripts/
│   ├── publish_ami.py                # Post-build: write AMI ID to SSM
│   ├── verify_ami.py                 # Confirm AMI + Parameter Store consistent
│   └── deprecate_ami.py             # Clean up old AMIs
└── docs/
    └── cli-playbooks/
        ├── 01-build-base.md          # Build and publish base AMI
        ├── 02-build-app.md           # Build and publish app AMI
        ├── 03-ami-lifecycle.md       # Deprecation, retention, cleanup
        └── 04-proxmox-builder.md     # On-prem VM template builds
```

---

## Key Conventions

- Stack name (CDK): `ImagePipelineStack`
- All SSM parameter keys: `/ops-lab/images/{resource}`
- AMI naming: `ops-lab-{type}-{timestamp}` e.g. `ops-lab-app-20250501-1423`
- AMI tags: `Project: ops-lab`, `Type: base|app`, `BuildDate: YYYY-MM-DD`
- Packer instance type: `t3.small` for builds (cheap, sufficient)
- Packer communicator: `ssh` during build only — key destroyed post-build
- HCL2 syntax only — no legacy Packer JSON templates
- Comments explain *why*, not just *what*
- Build base first, app second — app template must reference base AMI ID
  from Parameter Store, not hardcode it

