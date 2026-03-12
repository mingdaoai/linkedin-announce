# LinkedIn Announce Automation

This repository consolidates scripts for automating LinkedIn posting and monitoring, previously located in `/Users/haha/mingdao/python/announceMock/makeWebhook`.

## Scripts

- `monitor_linkedin_cron.py` – Hourly cron job that checks S3 history for recent LinkedIn posts, logs status to `.cache/monitor_status.json`, and warns if no post within threshold (default 2 days).
- `linkedin_poster.py` – Main script to select a recent video from S3 list and post to LinkedIn via API (or dry‑run). Uses `linkedin_api.py` and `videoUtil.py`.
- `linkedin_api.py` – LinkedIn API posting utilities (direct API integration, no longer uses Make.com webhooks).
- `videoUtil.py` – Common functions to read S3 video list and history, select a valid video, and update history.
- `confirm_video_link.py` – Helper to validate video URLs.
- `updateYoutubeVideoList.py` – Updates the video list from YouTube (or other sources).
- `uploadYoutubeVideoList.py` – Uploads video list to S3.
- `uploadHistory.py` – Uploads history file to S3.
- `deploy.py` – Deployment script for EC2 instance.
- `create_s3_bucket.py` – Creates S3 bucket for video storage.

## Deprecated Make.com Functions

Legacy Make.com webhook functions have been moved to `bak/webhook_functions.py`. These are no longer used; posting is now done directly via the LinkedIn API.

## Dependencies

All scripts are written for Python ≥3.10 and use `uv` for dependency management. Each script declares its own dependencies via PEP 723 inline metadata. The main required packages are `boto3` and `requests`.

## Cron Setup

The hourly monitoring cron entry has been updated to point to this repository:

```
0 * * * * cd '/Users/haha/github/linkedin-announce' && /Users/haha/.local/bin/uv run monitor_linkedin_cron.py >> '/Users/haha/github/linkedin-announce/cron.log' 2>&1
```

To manually run the monitor:

```bash
uv run monitor_linkedin_cron.py [--dry-run] [--threshold DAYS]
```

To test the LinkedIn posting logic (dry‑run):

```bash
uv run linkedin_poster.py --dry-run
```

## EC2 Integration

The script that runs on EC2 to push new videos to LinkedIn (`linkedin_poster.py`) is now also in this repo. The deployment script (`deploy.py`) has been updated to deploy to `~/linkedin-announce` on the EC2 instance and set up a cron job at 9:30 AM daily.

To deploy updates to EC2:

```bash
uv run deploy.py --instance-id <instance-id>
```

## Environment

Ensure AWS credentials are configured (via `~/.aws/credentials` or environment variables) for S3 access. LinkedIn API token must be placed at `~/.mingdaoai/linkedin_token.json`.

## Logs

- `cron.log` – Output from the hourly monitor cron.
- `.cache/monitor_status.json` – JSON status file written by the monitor, useful for other scripts (e.g., todo_due).

## Integration with Todoist

The `todo_due` script (in the `~/github/todoist` directory) checks the `.cache/monitor_status.json` file and warns if the status is older than 48 hours or if there are posting issues. This provides visibility into LinkedIn posting health directly from your daily task review.

To manually check the status:

```bash
cd ~/github/todoist && ./todo_due
```

If you see warnings about outdated status, run the monitor manually:

```bash
cd ~/github/linkedin-announce && ./monitor_linkedin_cron.py
```