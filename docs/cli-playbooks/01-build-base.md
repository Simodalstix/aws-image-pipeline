# Playbook 01 – Build and Publish Base AMI

Builds the hardened base AMI from `packer/base.pkr.hcl` and writes its ID to
SSM Parameter Store. Run this before building the app AMI.

## Prerequisites

- `ImagePipelineStack` deployed (`cdk deploy`)
- `aws-ops-networking` and `aws-ops-observability` stacks deployed
- Packer installed and `packer init` run at least once
- AWS credentials with EC2, SSM, and IAM PassRole permissions

## Steps

### 1. Validate the template

```bash
packer validate -var-file=packer/variables.pkrvars.hcl packer/base.pkr.hcl
```

### 2. Build the AMI

```bash
packer build -var-file=packer/variables.pkrvars.hcl packer/base.pkr.hcl
```

Packer will:
- Launch a `t3.small` builder in the public subnet from SSM
- Run `install_cw_agent.sh`, `harden.sh`, `verify_build.sh`
- Create the AMI and terminate the builder (~10–15 min)
- Print the AMI ID on the final line, e.g. `AMI: ami-0abc1234def56789`

### 3. Publish to Parameter Store

Copy the AMI ID from the Packer output:

```bash
python scripts/publish_ami.py --ami-id ami-<id-from-packer-output> --type base
```

This writes:
- `/ops-lab/images/base-ami-id` → AMI ID
- `/ops-lab/images/base-ami-version` → build timestamp (YYYYMMDD-hhmm)

### 4. Verify

```bash
python scripts/verify_ami.py --type base
```

All checks should pass. If any fail, do not proceed to the app build.

### 5. Confirm in SSM (optional)

```bash
aws ssm get-parameter --name /ops-lab/images/base-ami-id --region ap-southeast-2
aws ssm get-parameter --name /ops-lab/images/base-ami-version --region ap-southeast-2
```

## Troubleshooting

**SSH timeout during build** — the builder subnet must have a route to the
internet and `associate_public_ip_address = true` must resolve. Check that
`/ops-lab/networking/subnet/public-0` points to a public subnet.

**`packer-builder` instance profile not found** — the CDK stack has not been
deployed, or the profile name differs. Run `cdk deploy` and confirm
`iam_instance_profile = "packer-builder"` in `variables.pkrvars.hcl`.

**AMI not found after build** — Packer may have failed mid-way and cleaned up.
Check the Packer log for errors before `publish_ami.py`.
