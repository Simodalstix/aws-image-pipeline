#!/usr/bin/env python3
"""
Write a newly baked AMI ID to SSM Parameter Store and tag the AMI.

Usage:
    python scripts/publish_ami.py --ami-id ami-0abc1234 --type base
    python scripts/publish_ami.py --ami-id ami-0abc1234 --type app --region ap-southeast-2
"""

import argparse
import sys
from datetime import datetime, timezone

import boto3


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ami-id", required=True)
    parser.add_argument("--type", required=True, choices=["base", "app"])
    parser.add_argument("--region", default="ap-southeast-2")
    args = parser.parse_args()

    ec2 = boto3.client("ec2", region_name=args.region)
    ssm = boto3.client("ssm", region_name=args.region)

    now = datetime.now(timezone.utc)
    build_version = now.strftime("%Y%m%d-%H%M")

    # Verify the AMI exists and is available before publishing.
    response = ec2.describe_images(ImageIds=[args.ami_id])
    if not response["Images"]:
        print(f"ERROR: AMI {args.ami_id} not found in {args.region}", file=sys.stderr)
        sys.exit(1)

    ami_state = response["Images"][0]["State"]
    if ami_state != "available":
        print(f"ERROR: AMI {args.ami_id} is in state '{ami_state}', expected 'available'", file=sys.stderr)
        sys.exit(1)

    # Tag the AMI to record when it was promoted to the active parameter.
    ec2.create_tags(
        Resources=[args.ami_id],
        Tags=[{"Key": "PublishedAt", "Value": now.isoformat()}],
    )

    # Write AMI ID and build version to Parameter Store.
    for name, value, description in [
        (
            f"/ops-lab/images/{args.type}-ami-id",
            args.ami_id,
            f"Latest {args.type} AMI ID",
        ),
        (
            f"/ops-lab/images/{args.type}-ami-version",
            build_version,
            f"Latest {args.type} AMI build version (YYYYMMDD-hhmm)",
        ),
    ]:
        ssm.put_parameter(
            Name=name,
            Value=value,
            Type="String",
            Overwrite=True,
            Description=description,
        )
        print(f"  {name} = {value}")

    print(f"\nPublished {args.ami_id} as {args.type} AMI ({build_version})")


if __name__ == "__main__":
    main()
