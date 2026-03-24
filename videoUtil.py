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
linkedin_posts_list_key = 'linkedin-posts/list.txt'

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

def read_linkedin_post_list():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    cache_dir = os.path.join(script_dir, '.cache')
    os.makedirs(cache_dir, exist_ok=True)
    local_post_file = os.path.join(cache_dir, 'linkedin_post_list_downloaded.txt')
    post_list = []

    try:
        response = s3_client.get_object(Bucket=bucket_name, Key=linkedin_posts_list_key)
        post_list = response['Body'].read().decode('utf-8').splitlines()
        
        with open(local_post_file, 'w', encoding='utf-8') as file:
            file.write("\n".join(post_list))
    except s3_client.exceptions.NoSuchKey:
        if os.path.exists(local_post_file):
            with open(local_post_file, 'r', encoding='utf-8') as file:
                post_list = [line.strip() for line in file.readlines()]
        else:
            print(f"LinkedIn post list not found in S3: {linkedin_posts_list_key}")
            return []
    except Exception as e:
        print(f"Error reading LinkedIn post list from S3: {str(e)}")
        traceback.print_exc()
        return []

    return post_list

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

def get_valid_linkedin_post(history_key, days=5):
    print("Reading history from:", history_key)
    history = read_history(history_key)
    print("History read successfully:", history)

    print("Reading LinkedIn post list...")
    post_lines = read_linkedin_post_list()
    print(f"Found {len(post_lines)} LinkedIn posts in list")

    all_posts = []
    for line in post_lines:
        if line.strip():
            parts = line.strip().split('|')
            if len(parts) == 4:
                creation_date, video_id, title, s3_path = parts
                if s3_path.endswith('/post.txt'):
                    s3_base = s3_path[:-9]
                else:
                    s3_base = s3_path
                post = {
                    'creation_date': creation_date,
                    'video_id': video_id,
                    'title': title,
                    's3_base': s3_base,
                    'post_url': s3_path,
                    'type': 'linkedin-image'
                }
                all_posts.append(post)

    if not all_posts:
        print("No LinkedIn posts found.")
        return None

    recent_posts = []
    for p in all_posts:
        creation_date = datetime.datetime.strptime(p['creation_date'], '%Y-%m-%d')
        is_recent = (datetime.datetime.now() - creation_date).days <= 14
        if is_recent and not is_video_recent(p['post_url'], history, days):
            recent_posts.append(p)
            print(f"Found recent LinkedIn post: {p['title']}")

    if recent_posts:
        selected_post = random.choice(recent_posts)
        print(f"Selected recent LinkedIn post: {selected_post['title']}")
        return selected_post

    selected_post = random.choice(all_posts)
    print(f"Selected LinkedIn post from all posts: {selected_post['title']}")
    return selected_post


def get_valid_post(history_key, days=5):
    """Get a valid post (video or LinkedIn image post) based on freshness and recency.
    
    Combines videos and LinkedIn posts, applies same freshness (≤14 days) and 
    recency (not posted in last `days`) filters, selects randomly from recent 
    candidates, falls back to all candidates.
    
    Returns:
        dict with keys: type ('video' or 'linkedin-image'), title, url/post_url,
        creation_date, and other type-specific fields.
    """
    history = read_history(history_key)
    
    video_list = read_video_list()
    all_items = []
    for line in video_list:
        if line.strip():
            parts = line.strip().split('|')
            if len(parts) == 4:
                item = {
                    'creation_date': parts[0],
                    'type': parts[1],
                    'title': parts[2],
                    'url': parts[3],
                    'post_type': 'video'
                }
                all_items.append(item)
    
    post_lines = read_linkedin_post_list()
    for line in post_lines:
        if line.strip():
            parts = line.strip().split('|')
            if len(parts) == 4:
                creation_date, video_id, title, s3_path = parts
                if s3_path.endswith('/post.txt'):
                    s3_base = s3_path[:-9]
                else:
                    s3_base = s3_path
                item = {
                    'creation_date': creation_date,
                    'type': 'linkedin-image',
                    'title': title,
                    'video_id': video_id,
                    's3_base': s3_base,
                    'post_url': s3_path,
                    'post_type': 'linkedin-image'
                }
                all_items.append(item)
    
    if not all_items:
        print("No posts (videos or LinkedIn posts) found.")
        return None
    
    recent_items = []
    for item in all_items:
        creation_date = datetime.datetime.strptime(item['creation_date'], '%Y-%m-%d')
        is_recent = (datetime.datetime.now() - creation_date).days <= 14
        item_url = item.get('url') or item.get('post_url')
        if is_recent and not is_video_recent(item_url, history, days):
            recent_items.append(item)
            print(f"Found recent {item['post_type']}: {item['title']}")
    
    if recent_items:
        selected = random.choice(recent_items)
        print(f"Selected recent {selected['post_type']}: {selected['title']}")
        return selected
    
    selected = random.choice(all_items)
    print(f"Selected {selected['post_type']} from all posts: {selected['title']}")
    return selected

def download_linkedin_post_assets(post, cache_dir=None):
    """Download LinkedIn post assets (text and image) from S3 to local cache.
    
    Args:
        post: dict from get_valid_linkedin_post with keys 's3_base', 'video_id', 'title'
        cache_dir: optional cache directory (default: script's .cache folder)
    
    Returns:
        dict with keys 'post_text', 'image_path', 'metadata_path' (local paths)
    """
    if cache_dir is None:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        cache_dir = os.path.join(script_dir, '.cache')
    os.makedirs(cache_dir, exist_ok=True)
    
    s3_base = post['s3_base']
    video_id = post['video_id']
    
    # Define local filenames
    local_post = os.path.join(cache_dir, f"{video_id}_post.txt")
    local_image = os.path.join(cache_dir, f"{video_id}_architecture.png")
    local_metadata = os.path.join(cache_dir, f"{video_id}_metadata.json")
    
    # Download files from S3
    try:
        # post.txt
        s3_key = f"{s3_base}/post.txt"
        response = s3_client.get_object(Bucket=bucket_name, Key=s3_key)
        with open(local_post, 'w', encoding='utf-8') as f:
            f.write(response['Body'].read().decode('utf-8'))
        
        # architecture.png
        s3_key = f"{s3_base}/architecture.png"
        response = s3_client.get_object(Bucket=bucket_name, Key=s3_key)
        with open(local_image, 'wb') as f:
            f.write(response['Body'].read())
        
        # metadata.json (optional)
        s3_key = f"{s3_base}/metadata.json"
        try:
            response = s3_client.get_object(Bucket=bucket_name, Key=s3_key)
            with open(local_metadata, 'w', encoding='utf-8') as f:
                f.write(response['Body'].read().decode('utf-8'))
        except s3_client.exceptions.NoSuchKey:
            local_metadata = None
        
        print(f"Downloaded LinkedIn post assets for {video_id}")
        return {
            'post_text': local_post,
            'image_path': local_image,
            'metadata_path': local_metadata
        }
    except Exception as e:
        print(f"Error downloading LinkedIn post assets: {e}")
        raise


def update_history(video, history_key):
    history = read_history(history_key)
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    # Handle both video (has 'url') and linkedin post (has 'post_url')
    post_url = video.get('url') or video.get('post_url')
    if not post_url:
        raise ValueError("Video/post dict must have 'url' or 'post_url' key")
    new_entry = f"{timestamp}|{video['type']}|{video['title']}|{post_url}"
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