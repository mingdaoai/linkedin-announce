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
    
    status = {
        'checked_at': datetime.datetime.now(timezone.utc).isoformat(),
        'total_posts': total_posts,
        'threshold_days': args.threshold,
        'status': 'unknown'
    }
    
    if total_posts == 0:
        status['status'] = 'no_history'
        status['warning'] = 'No posting history found in S3'
        print("WARNING: No posting history found in S3")
    else:
        last_ts_str, last_dt, gap_days = get_last_push_info(entries)
        if last_ts_str:
            status['last_post'] = last_ts_str
            status['gap_days'] = gap_days
            status['last_post_datetime'] = last_dt.isoformat()
            
            # Show last 5 posts for context
            last_n = min(5, total_posts)
            recent = entries[-last_n:]
            status['recent_posts'] = []
            for ts, typ, title, url in recent:
                status['recent_posts'].append({
                    'timestamp': ts,
                    'type': typ,
                    'title_short': (title[:60] + '...') if len(title) > 60 else title,
                    'url': url
                })
            
            print(f"Total posts in history: {total_posts}")
            print(f"Last post: {last_ts_str} ({gap_days:.1f} days ago)")
            
            if gap_days > args.threshold:
                status['status'] = 'warning'
                status['warning'] = f'No LinkedIn post for {gap_days:.1f} days'
                print(f"*** WARNING: No post for {gap_days:.1f} days (threshold: {args.threshold} days)")
                print("   Consider checking the daily cron on the EC2 instance.")
            else:
                status['status'] = 'ok'
                print(f"OK: Last post within {args.threshold} days")
        else:
            status['status'] = 'error'
            status['error'] = 'Could not parse last post timestamp'
            print("ERROR: Could not parse last post timestamp")
    
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