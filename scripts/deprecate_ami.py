#!/usr/bin/env python3
"""
Deprecate AMIs beyond the retention window and optionally deregister very old ones.

Retention policy:
  - The AMI currently in SSM is always protected regardless of age or rank.
  - The 3 most recent AMIs are kept active.
  - Older AMIs are deprecated (hidden from default searches, still launchable).
  - Pass --deregister-older-than-days N to permanently remove AMIs beyond that age.

Usage:
    python scripts/deprecate_ami.py --type base --dry-run
    python scripts/deprecate_ami.py --type app --deregister-older-than-days 90
"""

import argparse
import sys
from datetime import datetime, timezone, timedelta

import boto3


RETENTION_COUNT = 3


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--type", required=True, choices=["base", "app"])
    parser.add_argument("--region", default="ap-southeast-2")
    parser.add_argument(
        "--deregister-older-than-days",
        type=int,
        default=None,
        metavar="DAYS",
        help="Deregister AMIs older than DAYS (never deregisters the current SSM AMI)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print actions without executing them")
    args = parser.parse_args()

    ec2 = boto3.client("ec2", region_name=args.region)
    ssm = boto3.client("ssm", region_name=args.region)

    current_ami_id = ssm.get_parameter(
        Name=f"/ops-lab/images/{args.type}-ami-id"
    )["Parameter"]["Value"]

    response = ec2.describe_images(
        Owners=["self"],
        Filters=[
            {"Name": "tag:Project", "Values": ["ops-lab"]},
            {"Name": "tag:Type", "Values": [args.type]},
            {"Name": "state", "Values": ["available"]},
        ],
    )

    amis = sorted(response["Images"], key=lambda x: x["CreationDate"], reverse=True)

    if not amis:
        print("No AMIs found.")
        return

    now = datetime.now(timezone.utc)
    # DeprecateAt must be at least 1 minute in the future.
    deprecate_at = now + timedelta(minutes=2)
    suffix = " [dry-run]" if args.dry_run else ""

    for rank, ami in enumerate(amis):
        ami_id = ami["ImageId"]
        age_days = (now - datetime.fromisoformat(ami["CreationDate"])).days
        is_current = ami_id == current_ami_id
        within_retention = rank < RETENTION_COUNT

        status_parts = []
        if is_current:
            status_parts.append("current")
        if within_retention:
            status_parts.append(f"rank {rank + 1}")
        status = f"({', '.join(status_parts)}, {age_days}d)" if status_parts else f"({age_days}d)"

        if is_current or within_retention:
            print(f"  KEEP       {ami_id}  {status}")
            continue

        print(f"  DEPRECATE  {ami_id}  {status}{suffix}")
        if not args.dry_run:
            ec2.enable_image_deprecation(ImageId=ami_id, DeprecateAt=deprecate_at)

        if args.deregister_older_than_days and age_days >= args.deregister_older_than_days:
            print(f"  DEREGISTER {ami_id}  ({age_days}d >= {args.deregister_older_than_days}d threshold){suffix}")
            if not args.dry_run:
                ec2.deregister_image(ImageId=ami_id)

    print()
    total = len(amis)
    kept = min(RETENTION_COUNT, total)
    print(f"Processed {total} AMI(s): {kept} kept, {total - kept} deprecated{suffix}.")
    if args.deregister_older_than_days:
        print(f"Note: deregistered snapshots are not automatically deleted.")


if __name__ == "__main__":
    main()
