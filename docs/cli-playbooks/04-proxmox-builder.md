# Playbook 04 – Proxmox VM Template Builds

Extends the pipeline to build Proxmox VM templates using the same provisioner
scripts that produce AWS AMIs. The result is a unified image pipeline across
cloud and on-prem — one set of hardening and configuration scripts, two targets.

## How it works

Packer's `proxmox-clone` builder clones an existing Proxmox VM template,
runs the same provisioners (`harden.sh`, `install_cw_agent.sh`,
`install_deps.sh`), and converts the result to a new template. The provisioners
are cloud-agnostic shell scripts — they work unchanged on either target.

```
packer/proxmox-base.pkr.hcl
  └── clones a clean AL2023-equivalent template in Proxmox
        runs provisioners/harden.sh
        runs provisioners/install_cw_agent.sh  (skips AWS SSM fetch on-prem)
        saves as new Proxmox template
```

## Prerequisites

- Proxmox VE node accessible from your build machine
- A base VM template in Proxmox to clone from (e.g. a plain Rocky Linux 9 or
  Debian 12 cloud-init image)
- Packer `proxmox` plugin installed:

```bash
packer plugins install github.com/hashicorp/proxmox
```

- API token or credentials for Proxmox with VM clone/template permissions

## Example template structure

Create `packer/proxmox-base.pkr.hcl`:

```hcl
packer {
  required_plugins {
    proxmox = {
      source  = "github.com/hashicorp/proxmox"
      version = ">= 1.1.0"
    }
  }
}

variable "proxmox_url"      { type = string }
variable "proxmox_username" { type = string }
variable "proxmox_token"    { type = string }
variable "proxmox_node"     { type = string }
variable "clone_vm_id"      { type = number }  # template to clone

source "proxmox-clone" "base" {
  proxmox_url              = var.proxmox_url
  username                 = var.proxmox_username
  token                    = var.proxmox_token
  node                     = var.proxmox_node
  clone_vm                 = var.clone_vm_id
  vm_name                  = "ops-lab-base-template"
  template_name            = "ops-lab-base-template"

  communicator             = "ssh"
  ssh_username             = "admin"
  ssh_private_key_file     = "~/.ssh/id_ed25519"
}

build {
  sources = ["source.proxmox-clone.base"]

  provisioner "shell" {
    script = "provisioners/harden.sh"
  }

  # install_cw_agent.sh requires adjustment on-prem:
  # CW agent can still ship logs to CloudWatch if the VM has outbound internet
  # and an IAM user with CloudWatchAgentServerPolicy. Skip if air-gapped.
  provisioner "shell" {
    script = "provisioners/install_cw_agent.sh"
    environment_vars = [
      "CW_CONFIG_SSM_PATH=/ops-lab/shared/cw-agent-config-ssm-path",
      "AWS_DEFAULT_REGION=ap-southeast-2",
    ]
  }

  provisioner "shell" {
    script = "provisioners/verify_build.sh"
    environment_vars = ["VERIFY_APP=false"]
  }
}
```

## Building

```bash
packer validate packer/proxmox-base.pkr.hcl
packer build \
  -var proxmox_url=https://proxmox.local:8006/api2/json \
  -var proxmox_username=root@pam \
  -var proxmox_token=<token> \
  -var proxmox_node=pve \
  -var clone_vm_id=9000 \
  packer/proxmox-base.pkr.hcl
```

Store sensitive variables in a local `.pkrvars.hcl` file (gitignored):

```hcl
# packer/proxmox.pkrvars.hcl  — do not commit
proxmox_url      = "https://proxmox.local:8006/api2/json"
proxmox_username = "root@pam"
proxmox_token    = "root@pam!packer=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
proxmox_node     = "pve"
clone_vm_id      = 9000
```

```bash
packer build -var-file=packer/proxmox.pkrvars.hcl packer/proxmox-base.pkr.hcl
```

## On-prem vs AWS differences

| Concern | AWS | Proxmox |
|---------|-----|---------|
| Source image | AL2023 via AMI filter | Existing VM template (clone_vm_id) |
| SSH access | Temporary key, public subnet | Direct SSH to Proxmox network |
| CloudWatch agent | Fetches config from SSM | Needs AWS creds or skip if air-gapped |
| Output | AMI registered in EC2 | VM template on Proxmox node |
| Publish step | `publish_ami.py` → SSM | Manual or write to local config store |

## Notes

- `install_cw_agent.sh` references SSM to fetch the agent config. On-prem, this
  works if the VM has outbound internet access and AWS credentials. For
  air-gapped environments, embed the config directly or skip the script.
- The `proxmox-iso` builder can be used instead of `proxmox-clone` to build
  from a fresh ISO, at the cost of a longer build time.
