#!/usr/bin/env uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "boto3>=1.26.0",
# ]
# ///

"""
Monitor LinkedIn posting cron status by checking S3 history.
Logs status to local file for other scripts (like todo_due) to check.
Run hourly via crontab.
"""

import boto3
import os
import datetime
from datetime import timezone
import json
import argparse
from pathlib import Path

BUCKET_NAME = 'dscub'
HISTORY_KEY = 'videos/history.txt'
STATUS_FILE = '.cache/monitor_status.json'
WARNING_THRESHOLD_DAYS = 2  # Warn if no post in last 2 days

# On 2026-07-14 the GitHub research → LinkedIn image pipeline moved to AWS. That
# publisher records a durable receipt per post at receipts/<post_id>.json in the
# artifact bucket below and does NOT append to the legacy videos/history.txt.
# Without consulting this ledger the monitor is blind to every AWS post and
# reports a false "no post for N days" once the last legacy post ages out.
# (See mingdao-marketing/docs/aws-github-research-pipeline.md.)
AWS_LEDGER_BUCKET = 'github-research-prod-659161076841'
AWS_LEDGER_PREFIX = 'receipts/'
AWS_LEDGER_REGION = 'us-west-2'

def read_push_history():
    """Read push history from S3. Returns list of (timestamp_str, type, title, url) or [] on error."""
    s3 = boto3.client('s3')
    try:
        response = s3.get_object(Bucket=BUCKET_NAME, Key=HISTORY_KEY)
        lines = response['Body'].read().decode('utf-8').strip().splitlines()
        entries = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            parts = line.split('|', 3)  # timestamp|type|title|url (title may contain |)
            if len(parts) >= 4:
                entries.append((parts[0], parts[1], parts[2], parts[3]))
        return entries
    except Exception as e:
        print(f"Could not read push history from S3: {e}")
        return []

def read_aws_publish_ledger():
    """Return (latest_published_dt_utc, count, latest_receipt) from the AWS
    publication receipts ledger, or (None, 0, None) on any error.

    Each receipts/<post_id>.json holds a receipt like:
        {"post_id": ..., "published_at": "2026-07-22T16:31:13.757986Z",
         "status": "published", "linkedin_post_id": "urn:li:share:..."}
    Only status=="published" receipts count as a real post. Read fully (the
    ledger is ~1 object/day, tiny) so a partial "publishing" intent record does
    not masquerade as a completed post."""
    try:
        s3 = boto3.client('s3', region_name=AWS_LEDGER_REGION)
        paginator = s3.get_paginator('list_objects_v2')
        keys = []
        for page in paginator.paginate(Bucket=AWS_LEDGER_BUCKET, Prefix=AWS_LEDGER_PREFIX):
            for obj in page.get('Contents', []):
                if obj['Key'].endswith('.json'):
                    keys.append(obj['Key'])
        latest_dt = None
        latest_receipt = None
        published = 0
        for key in keys:
            try:
                body = s3.get_object(Bucket=AWS_LEDGER_BUCKET, Key=key)['Body'].read()
                receipt = json.loads(body)
            except Exception:
                continue
            if receipt.get('status') != 'published':
                continue
            ts = receipt.get('published_at')
            if not ts:
                continue
            try:
                dt = datetime.datetime.fromisoformat(ts.replace('Z', '+00:00'))
            except ValueError:
                continue
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            published += 1
            if latest_dt is None or dt > latest_dt:
                latest_dt = dt
                latest_receipt = receipt
        return latest_dt, published, latest_receipt
    except Exception as e:
        print(f"Could not read AWS publish ledger: {e}")
        return None, 0, None


def get_last_push_info(entries):
    """Extract last push timestamp and compute gap."""
    if not entries:
        return None, None, None
    
    last_ts_str = entries[-1][0]  # e.g. '2026-02-09 09:30:04'
    try:
        last_dt = datetime.datetime.strptime(last_ts_str, '%Y-%m-%d %H:%M:%S')
        last_dt = last_dt.replace(tzinfo=timezone.utc)
        now = datetime.datetime.now(timezone.utc)
        gap_days = (now - last_dt).total_seconds() / 86400
        return last_ts_str, last_dt, gap_days
    except ValueError as e:
        print(f"Could not parse last push timestamp {last_ts_str}: {e}")
        return None, None, None

def write_status_file(status_data):
    """Write status to JSON file."""
    script_dir = Path(__file__).parent.resolve()
    cache_dir = script_dir / '.cache'
    cache_dir.mkdir(exist_ok=True)
    status_path = cache_dir / 'monitor_status.json'
    
    with open(status_path, 'w', encoding='utf-8') as f:
        json.dump(status_data, f, indent=2, default=str)
    
    print(f"Status written to {status_path}")

def main():
    parser = argparse.ArgumentParser(description='Monitor LinkedIn posting cron status')
    parser.add_argument('--dry-run', action='store_true', help='Show status without writing file')
    parser.add_argument('--threshold', type=float, default=WARNING_THRESHOLD_DAYS,
                       help=f'Days threshold for warning (default: {WARNING_THRESHOLD_DAYS})')
    args = parser.parse_args()
    
    print(f"Checking LinkedIn posting history from S3...")
    entries = read_push_history()
    total_posts = len(entries)

    # Legacy history.txt covers content still posted the old way (e.g. YouTube).
    _, hist_dt, _ = get_last_push_info(entries)

    # AWS ledger covers GitHub-research image posts published since 2026-07-14.
    aws_dt, aws_published, aws_receipt = read_aws_publish_ledger()
    if aws_published and aws_dt is not None:
        print(f"AWS publish ledger: {aws_published} receipt(s), latest {aws_dt.isoformat()}")

    now = datetime.datetime.now(timezone.utc)

    status = {
        'checked_at': now.isoformat(),
        'total_posts': total_posts,
        'aws_published_count': aws_published,
        'threshold_days': args.threshold,
        'status': 'unknown'
    }

    # Effective last post = most recent across both channels.
    last_dt = None
    last_source = None
    if hist_dt is not None:
        last_dt, last_source = hist_dt, 'history'
    if aws_dt is not None and (last_dt is None or aws_dt > last_dt):
        last_dt, last_source = aws_dt, 'aws-ledger'

    if last_dt is None:
        status['status'] = 'no_history'
        status['warning'] = 'No posting history found in S3 (legacy or AWS ledger)'
        print("WARNING: No posting history found in S3 (legacy or AWS ledger)")
    else:
        gap_days = (now - last_dt).total_seconds() / 86400
        status['last_post'] = last_dt.strftime('%Y-%m-%d %H:%M:%S')
        status['last_post_datetime'] = last_dt.isoformat()
        status['last_post_source'] = last_source
        status['gap_days'] = gap_days
        if last_source == 'aws-ledger' and aws_receipt:
            status['last_post_post_id'] = aws_receipt.get('post_id')

        # Show last 5 legacy posts for context (AWS receipts summarized above).
        if entries:
            recent = entries[-min(5, total_posts):]
            status['recent_posts'] = [{
                'timestamp': ts,
                'type': typ,
                'title_short': (title[:60] + '...') if len(title) > 60 else title,
                'url': url
            } for ts, typ, title, url in recent]

        print(f"Legacy history posts: {total_posts}; AWS ledger posts: {aws_published}")
        print(f"Last post: {status['last_post']} via {last_source} ({gap_days:.1f} days ago)")

        if gap_days > args.threshold:
            status['status'] = 'warning'
            status['warning'] = f'No LinkedIn post for {gap_days:.1f} days'
            print(f"*** WARNING: No post for {gap_days:.1f} days (threshold: {args.threshold} days)")
            print("   Check the AWS publisher (github-research-prod-publisher) and the EC2 cron.")
        else:
            status['status'] = 'ok'
            print(f"OK: Last post within {args.threshold} days")
    
    # Print recent posts
    if 'recent_posts' in status:
        print("\nRecent posts:")
        for post in status['recent_posts']:
            print(f"  {post['timestamp']} [{post['type']}] {post['title_short']}")
    
    if not args.dry_run:
        write_status_file(status)
    else:
        print("\n[DRY RUN] Status would be:")
        print(json.dumps(status, indent=2, default=str))
    
    # Return non‑zero exit code if warning/error (for cron alerts)
    if status.get('status') in ('warning', 'error', 'no_history'):
        return 1
    return 0

if __name__ == '__main__':
    import sys
    sys.exit(main())