packer {
  required_plugins {
    amazon = {
      source  = "github.com/hashicorp/amazon"
      version = ">= 1.2.0"
    }
  }
}

variable "region" {
  type = string
}

variable "instance_type" {
  type    = string
  default = "t3.small"
}

variable "iam_instance_profile" {
  type = string
}

# Override at build time: packer build -var 'build_timestamp=20250501-1423'
# Defaults to current time if omitted.
variable "build_timestamp" {
  type    = string
  default = ""
}

data "amazon-parameterstore" "subnet_id" {
  name            = "/ops-lab/networking/subnet/public-0"
  region          = var.region
  with_decryption = false
}

data "amazon-parameterstore" "cw_config_ssm_path" {
  name            = "/ops-lab/shared/cw-agent-config-ssm-path"
  region          = var.region
  with_decryption = false
}

locals {
  timestamp = var.build_timestamp != "" ? var.build_timestamp : formatdate("YYYYMMDD-hhmm", timestamp())
  ami_name  = "ops-lab-base-${local.timestamp}"
}

source "amazon-ebs" "base" {
  ami_name      = local.ami_name
  instance_type = var.instance_type
  region        = var.region
  subnet_id     = data.amazon-parameterstore.subnet_id.value

  # Public IP required — builder is in a public subnet with no NAT gateway.
  associate_public_ip_address = true

  # Packer creates a temporary SG allowing SSH from anywhere for the duration
  # of the build, then destroys it. The builder is ephemeral so this is
  # acceptable; the networking ssm-sg-id is for production instances only.
  temporary_security_group_source_cidrs = ["0.0.0.0/0"]

  communicator = "ssh"
  ssh_username  = "ec2-user"
  ssh_timeout   = "10m"

  # Instance profile must have AmazonSSMManagedInstanceCore +
  # CloudWatchAgentServerPolicy so provisioners can read from SSM.
  iam_instance_profile = var.iam_instance_profile

  source_ami_filter {
    filters = {
      name                = "al2023-ami-2023.*-x86_64"
      root-device-type    = "ebs"
      virtualization-type = "hvm"
    }
    most_recent = true
    owners      = ["amazon"]
  }

  tags = {
    Name      = local.ami_name
    Project   = "ops-lab"
    Type      = "base"
    BuildDate = formatdate("YYYY-MM-DD", timestamp())
  }

  run_tags = {
    Name    = "packer-builder-base-${local.timestamp}"
    Project = "ops-lab"
  }
}

build {
  name    = "base"
  sources = ["source.amazon-ebs.base"]

  provisioner "shell" {
    script = "provisioners/install_cw_agent.sh"
    environment_vars = [
      "CW_CONFIG_SSM_PATH=${data.amazon-parameterstore.cw_config_ssm_path.value}",
      "AWS_DEFAULT_REGION=${var.region}",
    ]
  }

  provisioner "shell" {
    script = "provisioners/harden.sh"
  }

  provisioner "shell" {
    script = "provisioners/verify_build.sh"
    environment_vars = [
      "VERIFY_APP=false",
    ]
  }
}
