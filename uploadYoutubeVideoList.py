#!/usr/bin/env uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "boto3>=1.26.0",
#     "google-api-python-client>=2.100.0",
# ]
# ///

import boto3
import os
import glob
import argparse
import datetime
from datetime import timezone
import time

from announceMock.makeWebhook.pushMakeUtil import confirm_video_link
from youtubeManage.youtubeManageUtil import authenticate_youtube_mingdaoschool, get_cached_video_details
import traceback


def read_video_lists():
    videos = []
    # readding from ../videos directory
    video_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'videos')
    print(f"Reading video lists from {video_dir}")
    list_files = glob.glob(os.path.join(video_dir, '*-list.txt'))

    for list_file in list_files:
        video_type = os.path.basename(list_file).replace('-list.txt', '')

        with open(list_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    parts = line.split(';')
                    if len(parts) >= 3:  # Changed to >= to allow optional creation_date
                        video = {
                            'title': parts[1].strip(),
                            'subject': parts[0].strip(),
                            'url': parts[2].strip(),
                            'type': video_type
                        }
                        # Add creation_date if it exists (4th field)
                        if len(parts) >= 4:
                            video['creation_date'] = parts[3].strip()
                        videos.append(video)
    return videos


def get_video_id_from_url(url):
    # Extract video ID from URL
    if 'mingdaoschool.com/youtube' in url:
        from urllib.parse import parse_qs, urlparse
        return parse_qs(urlparse(url).query)['v'][0]
    elif 'youtu.be/' in url:
        return url.split('youtu.be/')[-1].split('?')[0]
    elif 'youtube.com/watch' in url:
        from urllib.parse import parse_qs, urlparse
        return parse_qs(urlparse(url).query)['v'][0]
    elif 'youtube.com/shorts/' in url:
        return url.split('youtube.com/shorts/')[-1].split('?')[0]
    assert False, f"Invalid video URL: {url}"

def get_youtube_url(video_id):
    return f'https://www.youtube.com/watch?v={video_id}'


def load_previous_results(bucket='dscub', key='videos/list.txt'):
    s3 = boto3.client('s3')
    try:
        response = s3.get_object(Bucket=bucket, Key=key)
        content = response['Body'].read().decode('utf-8')
        previous_videos = {}
        for line in content.splitlines():
            if line.strip():
                creation_date, video_type, title, url = line.strip().split('|')
                previous_videos[url] = {
                    'creation_date': creation_date,
                    'type': video_type,
                    'title': title,
                    'url': url
                }
        return previous_videos
    except Exception as e:
        print(f"Could not load previous results: {str(e)}")
        return {}

def enrich_videos_with_youtube_data(videos):
    youtube = None
    enriched_videos = []
    
    # Load previous results from S3
    previous_videos = load_previous_results()

    for video in videos:
        video_id = get_video_id_from_url(video['url'])
        youtube_url = get_youtube_url(video_id)
        
        # Check if video exists in previous results
        if youtube_url in previous_videos:
            print(f"Using cached data for video: {youtube_url}")
            previous_video = previous_videos[youtube_url]
            for key in video.keys():
                previous_video[key] = video[key]
            enriched_videos.append(previous_video)
            continue
        
        # Skip enrichment if video already has all required fields from input file
        if 'creation_date' in video:
            assert confirm_video_link(youtube_url), f"Invalid YouTube URL: {youtube_url}"
            enriched_videos.append({
                'creation_date': video['creation_date'],
                'type': video['type'],
                'subject': video['subject'],
                'url': youtube_url,
                'title': video['title']
            })
            continue

        print(f"Enriching video {video['url']} (subject: {video['subject']}) to get creation date")
        if video_id:
            try:
                if youtube is None:
                    youtube = authenticate_youtube_mingdaoschool()
                video_data = get_cached_video_details(youtube, video_id)
                if 'items' in video_data and video_data['items']:
                    snippet = video_data['items'][0]['snippet']
                    published_at = datetime.datetime.strptime(
                        snippet['publishedAt'],
                        '%Y-%m-%dT%H:%M:%SZ'
                    )

                    assert confirm_video_link(youtube_url), f"Invalid YouTube URL: {youtube_url}"
                    enriched_videos.append({
                        'creation_date': published_at.strftime('%Y-%m-%d'),
                        'type': video['type'],
                        'subject': video['subject'],
                        'url': youtube_url,
                        'title': video['title']
                    })
            except Exception as e:
                assert False, f"Error processing video {video['url']}: {str(e)}"
        else:
            assert False, f"Invalid video URL: {video['url']}"

    return enriched_videos

def save_to_s3(videos, bucket='dscub', key='videos/list.txt', dry_run=False):
    s3 = boto3.client('s3')

    # Format the videos list as text
    video_text = '\n'.join([
        f"{v['creation_date']}|{v['type']}|{v['title']}|{v['url']}"
        for v in sorted(videos, key=lambda x: x['creation_date'], reverse=True)
    ])

    print(f"Processing {len(videos)} videos")

    # Get the directory of the current script and create .cache directory if needed
    script_dir = os.path.dirname(os.path.abspath(__file__))
    cache_dir = os.path.join(script_dir, '.cache')
    os.makedirs(cache_dir, exist_ok=True)
    local_file_path = os.path.join(cache_dir, 'video_list.txt')

    if dry_run:
        print("[DRY RUN] Would save to local file:", local_file_path)
        print("[DRY RUN] Would upload to S3:", f"bucket={bucket}, key={key}")
        print("[DRY RUN] Content preview (first 200 chars):", video_text[:200] + "...")
        return

    # Save locally in the .cache directory
    print(f"Saving to local file: {local_file_path}")
    with open(local_file_path, 'w', encoding='utf-8') as f:
        f.write(video_text)

    try:
        # Upload to S3 using put_object with explicit content type
        print(f"Uploading to S3: bucket={bucket}, key={key}")
        s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=video_text.encode('utf-8'),
            ContentType='text/plain; charset=utf-8'
        )
        print("Upload to S3 completed successfully")
    except Exception as e:
        print(f"Error uploading to S3: {str(e)}")
        traceback.print_exc()
        # Continue execution even if S3 upload fails
        pass

def get_s3_file_modification_time(bucket='dscub', key='videos/list.txt'):
    s3 = boto3.client('s3')
    try:
        response = s3.head_object(Bucket=bucket, Key=key)
        return response.get('LastModified')
    except Exception as e:
        print(f"Could not get S3 file modification time: {str(e)}")
        traceback.print_exc()
        return None

def read_push_history(bucket='dscub', key='videos/history.txt'):
    """Read push history from S3. Returns list of (timestamp_str, type, title, url) or [] on error."""
    s3 = boto3.client('s3')
    try:
        response = s3.get_object(Bucket=bucket, Key=key)
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


def report_last_pushes_and_warn(days_threshold=3, last_n=10):
    """Print last N pushes from S3 history and warn if no push for more than days_threshold."""
    entries = read_push_history()
    if not entries:
        print("\nPush history: (none or could not read)")
        return

    last_10 = entries[-last_n:]
    print(f"\n--- Last {len(last_10)} LinkedIn pushes (from s3://dscub/videos/history.txt) ---")
    for ts, typ, title, url in last_10:
        title_short = (title[:60] + '...') if len(title) > 60 else title
        print(f"  {ts}  [{typ}]  {title_short}")
        print(f"      {url}")
    print("---")

    # Check if last push is older than threshold
    try:
        last_ts_str = entries[-1][0]  # e.g. '2026-02-09 09:30:04'
        last_dt = datetime.datetime.strptime(last_ts_str, '%Y-%m-%d %H:%M:%S')
        last_dt = last_dt.replace(tzinfo=timezone.utc)
        now = datetime.datetime.now(timezone.utc)
        gap_days = (now - last_dt).total_seconds() / 86400
        if gap_days > days_threshold:
            print(f"\n*** WARNING: No push for {gap_days:.1f} days (last push: {last_ts_str}). Consider checking the daily cron on the EC2 instance. ***\n")
    except (ValueError, IndexError) as e:
        print(f"\nCould not parse last push timestamp: {e}")


def check_file_modification_times():
    video_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'videos')
    list_files = glob.glob(os.path.join(video_dir, '*-list.txt'))
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    cache_dir = os.path.join(script_dir, '.cache')
    local_cache_file = os.path.join(cache_dir, 'video_list.txt')
    
    local_mod_times = []
    for list_file in list_files:
        try:
            naive_time = datetime.datetime.fromtimestamp(os.path.getmtime(list_file))
            utc_time = naive_time.replace(tzinfo=timezone.utc)
            local_mod_times.append((list_file, utc_time))
        except Exception as e:
            print(f"Error getting modification time for {list_file}: {str(e)}")
            traceback.print_exc()
    
    # Check if local cache exists
    if not os.path.exists(local_cache_file):
        print(f"Local cache file {local_cache_file} does not exist. Forcing update.")
        return True, local_mod_times, None
    
    cache_time = datetime.datetime.fromtimestamp(os.path.getmtime(local_cache_file)).replace(tzinfo=timezone.utc)
    
    # If any list file is newer than the cache, force update
    for file_path, local_time in local_mod_times:
        if local_time > cache_time:
            print(f"Local file {file_path} is newer than cache file. Forcing update.")
            return True, local_mod_times, None
    
    # Now compare cache file to S3
    s3_mod_time = get_s3_file_modification_time()
    if not s3_mod_time:
        print("Could not get S3 file modification time. Forcing update.")
        return True, local_mod_times, None

    if cache_time > s3_mod_time:
        print("Local cache file is newer than S3 file. Will upload.")
        return True, local_mod_times, s3_mod_time
    else:
        print("No update needed. Local cache file is not newer than S3 file.")
        return False, local_mod_times, s3_mod_time

def main():
    parser = argparse.ArgumentParser(description='Upload video list to S3')
    parser.add_argument('--dry-run', action='store_true', help='Simulate the upload without actually performing it')
    
    try:
        args = parser.parse_args()
    except argparse.ArgumentError as e:
        print(f"Error: {str(e)}")
        parser.print_help()
        exit(1)
    
    # Check for any unknown args by reparsing with allow_abbrev=False
    parser_strict = argparse.ArgumentParser(allow_abbrev=False)
    parser_strict.add_argument('--dry-run', action='store_true')
    try:
        _, unknown = parser_strict.parse_known_args()
        if unknown:
            print(f"Error: unrecognized arguments: {' '.join(unknown)}")
            parser.print_help()
            exit(1)
    except Exception as e:
        print(f"Error parsing arguments: {str(e)}")
        parser.print_help()
        exit(1)

    # Check modification times
    needs_update, local_mod_times, s3_mod_time = check_file_modification_times()
    
    if not needs_update:
        print("\nNo update needed. File modification times:")
        if s3_mod_time:
            # Convert UTC to local time for display
            local_s3_time = s3_mod_time.astimezone()
            print(f"S3 file (dscub/videos/list.txt): {local_s3_time}")
            
            # Download and print the content of the last uploaded file from S3
            try:
                s3 = boto3.client('s3')
                response = s3.get_object(Bucket='dscub', Key='videos/list.txt')
                content = response['Body'].read().decode('utf-8')
                print("\nContent of the last uploaded file from S3:")
                print(content)
            except Exception as e:
                print(f"Error downloading or reading the last uploaded file from S3: {str(e)}")
                traceback.print_exc()
                
        print("\nLocal files (sorted by modification time, newest first):")
        # Sort local files by modification time in descending order
        sorted_local_times = sorted(local_mod_times, key=lambda x: x[1], reverse=True)
        for file_path, mod_time in sorted_local_times:
            # Convert UTC to local time for display
            local_time = mod_time.astimezone()
            print(f"{file_path}: {local_time}")
        report_last_pushes_and_warn()
        return
    # Read all video lists
    print("Reading video lists...")
    videos = read_video_lists()
    print(f"Found {len(videos)} videos in list files")

    # Enrich with YouTube data
    print("Enriching with YouTube data...")
    enriched_videos = enrich_videos_with_youtube_data(videos)
    print(f"Enriched {len(enriched_videos)} videos with YouTube data")

    # Save results locally and to S3
    save_to_s3(enriched_videos, dry_run=args.dry_run)

    report_last_pushes_and_warn()


if __name__ == '__main__':
    main()
