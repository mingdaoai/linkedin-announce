#!/usr/bin/env python
import os
import random
import boto3
import datetime
import traceback

s3_client = boto3.client('s3')
bucket_name = 'dscub'
webhook_history_file_key = 'videos/history.txt'
wechat_history_file_key = 'videos/wechat_history.txt'
video_list_key = 'videos/list.txt'

def read_history(history_key=webhook_history_file_key):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    cache_dir = os.path.join(script_dir, '.cache')
    os.makedirs(cache_dir, exist_ok=True)
    local_history_file = os.path.join(cache_dir, os.path.basename(history_key))
    history = []

    try:
        # Always read from S3
        response = s3_client.get_object(Bucket=bucket_name, Key=history_key)
        history = response['Body'].read().decode('utf-8').splitlines()
        history = [line.strip().split('|') for line in history]
        
        # Save a local copy
        with open(local_history_file, 'w', encoding='utf-8') as file:
            file.write("\n".join(["|".join(entry) for entry in history]))
    except s3_client.exceptions.NoSuchKey:
        # Try to read from local file if S3 fails
        if os.path.exists(local_history_file):
            with open(local_history_file, 'r', encoding='utf-8') as file:
                history = [line.strip().split('|') for line in file.readlines()]
        else:
            return []

    return history

def read_video_list():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    cache_dir = os.path.join(script_dir, '.cache')
    os.makedirs(cache_dir, exist_ok=True)
    local_video_file = os.path.join(cache_dir, 'video_list_downloaded.txt')
    video_list = []

    try:
        # Always read from S3
        response = s3_client.get_object(Bucket=bucket_name, Key=video_list_key)
        video_list = response['Body'].read().decode('utf-8').splitlines()
        
        # Save a local copy
        with open(local_video_file, 'w', encoding='utf-8') as file:
            file.write("\n".join(video_list))
    except s3_client.exceptions.NoSuchKey:
        # Try to read from local file if S3 fails
        if os.path.exists(local_video_file):
            with open(local_video_file, 'r', encoding='utf-8') as file:
                video_list = [line.strip() for line in file.readlines()]
        else:
            print(f"Video list not found in S3: {video_list_key}")
            return []
    except Exception as e:
        print(f"Error reading video list from S3: {str(e)}")
        traceback.print_exc()
        return []

    return video_list

def is_video_recent(video_url, history, days=5):
    for entry in history:
        if len(entry) >= 4 and entry[3] == video_url:
            timestamp = datetime.datetime.strptime(entry[0], '%Y-%m-%d %H:%M:%S')
            if datetime.datetime.now() - timestamp < datetime.timedelta(days=days):
                return True
    return False

def get_valid_video(history_key, days=5):
    print("Reading history from:", history_key)  # Debug message
    history = read_history(history_key)
    print("History read successfully:", history)  # Debug message

    print("Reading video list...")  # Debug message
    video_list = read_video_list()
    print("Video list read successfully:", video_list)  # Debug message
    
    all_videos = []
    for line in video_list:
        if line.strip():
            # Format: creation_date|type|title|url
            parts = line.strip().split('|')
            if len(parts) == 4:
                video = {
                    'creation_date': parts[0],
                    'type': parts[1],
                    'title': parts[2],
                    'url': parts[3]
                }
                all_videos.append(video)
    
    if not all_videos:
        print("No videos found.")
        return None
    
    recent_videos = []
    for v in all_videos:
        # Parse creation date in YYYY-MM-DD format
        creation_date = datetime.datetime.strptime(v['creation_date'], '%Y-%m-%d')
        is_recent = (datetime.datetime.now() - creation_date).days <= 14
        if is_recent and not is_video_recent(v['url'], history, days):
            recent_videos.append(v)
            print(f"Found recent video: {v['title']}")  # Debug message

    if recent_videos:
        selected_video = random.choice(recent_videos)
        print(f"Selected recent video: {selected_video['title']}")  # Debug message
        return selected_video

    selected_video = random.choice(all_videos)
    print(f"Selected video from all videos: {selected_video['title']}")  # Debug message
    return selected_video

def update_history(video, history_key):
    history = read_history(history_key)
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    new_entry = f"{timestamp}|{video['type']}|{video['title']}|{video['url']}"
    history.append(new_entry.split('|'))
    
    # Update both local and S3
    script_dir = os.path.dirname(os.path.abspath(__file__))
    cache_dir = os.path.join(script_dir, '.cache')
    os.makedirs(cache_dir, exist_ok=True)
    local_history_file = os.path.join(cache_dir, os.path.basename(history_key))
    
    updated_history = "\n".join(["|".join(entry) for entry in history])
    
    # Save locally first
    with open(local_history_file, 'w', encoding='utf-8') as file:
        file.write(updated_history)
    
    # Then update S3
    s3_client.put_object(
        Bucket=bucket_name,
        Key=history_key,
        Body=updated_history.encode('utf-8'),
        ContentType='text/plain; charset=utf-8'
    ) 