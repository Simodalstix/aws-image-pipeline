#!/usr/bin/env python3
"""
Verify that the AMI in SSM Parameter Store exists, is available,
and has consistent tags.

Usage:
    python scripts/verify_ami.py --type base
    python scripts/verify_ami.py --type app --region ap-southeast-2
"""

import argparse
import sys

import boto3


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--type", required=True, choices=["base", "app"])
    parser.add_argument("--region", default="ap-southeast-2")
    args = parser.parse_args()

    ec2 = boto3.client("ec2", region_name=args.region)
    ssm = boto3.client("ssm", region_name=args.region)

    # Read current values from Parameter Store.
    ami_id = ssm.get_parameter(
        Name=f"/ops-lab/images/{args.type}-ami-id"
    )["Parameter"]["Value"]
    ami_version = ssm.get_parameter(
        Name=f"/ops-lab/images/{args.type}-ami-version"
    )["Parameter"]["Value"]

    print(f"SSM:  /ops-lab/images/{args.type}-ami-id     = {ami_id}")
    print(f"SSM:  /ops-lab/images/{args.type}-ami-version = {ami_version}")
    print()

    # Describe the AMI.
    response = ec2.describe_images(ImageIds=[ami_id])
    if not response["Images"]:
        print(f"FAIL  AMI {ami_id} not found in EC2", file=sys.stderr)
        sys.exit(1)

    ami = response["Images"][0]
    tags = {t["Key"]: t["Value"] for t in ami.get("Tags", [])}

    failures = []

    def check(label: str, condition: bool, detail: str = "") -> None:
        if condition:
            print(f"  PASS  {label}")
        else:
            print(f"  FAIL  {label}{': ' + detail if detail else ''}")
            failures.append(label)

    check("AMI state is available",    ami["State"] == "available",        ami["State"])
    check("Project tag = ops-lab",     tags.get("Project") == "ops-lab",   tags.get("Project", "(missing)"))
    check(f"Type tag = {args.type}",   tags.get("Type") == args.type,      tags.get("Type", "(missing)"))
    check("Name tag present",          "Name" in tags)
    check("PublishedAt tag present",   "PublishedAt" in tags)

    print()
    print(f"  Name:    {ami.get('Name', '(none)')}")
    print(f"  Created: {ami['CreationDate']}")

    if failures:
        print(f"\n{len(failures)} check(s) failed.", file=sys.stderr)
        sys.exit(1)

    print(f"\nAll checks passed — {ami_id} is consistent with Parameter Store.")


if __name__ == "__main__":
    main()
