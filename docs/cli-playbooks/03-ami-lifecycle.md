# Playbook 03 – AMI Lifecycle Management

Covers deprecating old AMIs beyond the retention window and permanently
deregistering images past a maximum age. The current SSM AMI is always
protected regardless of age or rank.

## Retention policy

- The AMI currently in `/ops-lab/images/{type}-ami-id` is **always kept**
- The **3 most recent** AMIs per type are kept active
- Older AMIs are **deprecated** (hidden from default searches, still launchable)
- AMIs older than a configurable threshold can be **deregistered** (permanent)

## Steps

### 1. Preview what would change (dry run)

Always run dry-run first.

```bash
python scripts/deprecate_ami.py --type base --dry-run
python scripts/deprecate_ami.py --type app --dry-run
```

Output shows each AMI as `KEEP`, `DEPRECATE`, or `DEREGISTER` with age and rank.

### 2. Deprecate old AMIs

```bash
python scripts/deprecate_ami.py --type base
python scripts/deprecate_ami.py --type app
```

Deprecated AMIs are hidden from default `describe-images` results but can still
be launched. Useful for keeping a longer tail without cluttering AMI lists.

### 3. Deregister AMIs beyond maximum age

```bash
# Permanently remove AMIs older than 90 days (after dry-run confirms intent)
python scripts/deprecate_ami.py --type base --deregister-older-than-days 90
python scripts/deprecate_ami.py --type app  --deregister-older-than-days 90
```

> **Note:** Deregistering an AMI does not delete its backing EBS snapshots.
> Clean up snapshots separately if storage cost is a concern:
>
> ```bash
> aws ec2 describe-snapshots --owner-ids self --region ap-southeast-2 \
>   --filters Name=tag:Project,Values=ops-lab \
>   --query 'Snapshots[*].[SnapshotId,StartTime,Description]' \
>   --output table
> ```

### 4. Verify current state

```bash
python scripts/verify_ami.py --type base
python scripts/verify_ami.py --type app
```

Both should pass — confirms SSM still points to an available AMI after cleanup.

## Recommended cadence

| Action | When |
|--------|------|
| Deprecate | After every 4th–5th build |
| Deregister (90d) | Monthly, or as part of a scheduled cleanup |
| verify_ami | After any deprecation or deregister run |
