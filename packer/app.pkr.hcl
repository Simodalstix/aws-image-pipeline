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

variable "build_timestamp" {
  type    = string
  default = ""
}

data "amazon-parameterstore" "subnet_id" {
  name            = "/ops-lab/networking/subnet/public-0"
  region          = var.region
  with_decryption = false
}

# Reads the AMI ID written by scripts/publish_ami.py after the base build.
# Run base build + publish_ami.py before building app.
data "amazon-parameterstore" "base_ami_id" {
  name            = "/ops-lab/images/base-ami-id"
  region          = var.region
  with_decryption = false
}

locals {
  timestamp = var.build_timestamp != "" ? var.build_timestamp : formatdate("YYYYMMDD-hhmm", timestamp())
  ami_name  = "ops-lab-app-${local.timestamp}"
}

source "amazon-ebs" "app" {
  ami_name      = local.ami_name
  instance_type = var.instance_type
  region        = var.region
  subnet_id     = data.amazon-parameterstore.subnet_id.value
  source_ami    = data.amazon-parameterstore.base_ami_id.value

  associate_public_ip_address           = true
  temporary_security_group_source_cidrs = ["0.0.0.0/0"]

  communicator = "ssh"
  ssh_username  = "ec2-user"
  ssh_timeout   = "10m"

  iam_instance_profile = var.iam_instance_profile

  tags = {
    Name      = local.ami_name
    Project   = "ops-lab"
    Type      = "app"
    BuildDate = formatdate("YYYY-MM-DD", timestamp())
    BaseAMI   = data.amazon-parameterstore.base_ami_id.value
  }

  run_tags = {
    Name    = "packer-builder-app-${local.timestamp}"
    Project = "ops-lab"
  }
}

build {
  name    = "app"
  sources = ["source.amazon-ebs.app"]

  provisioner "shell" {
    script = "provisioners/install_deps.sh"
    environment_vars = [
      "AWS_DEFAULT_REGION=${var.region}",
    ]
  }

  provisioner "shell" {
    script = "provisioners/verify_build.sh"
    environment_vars = [
      "VERIFY_APP=true",
    ]
  }
}
