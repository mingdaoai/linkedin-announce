#!/usr/bin/env uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "groq>=0.4.0",
#     "requests>=2.25.0",
#     "youtube-transcript-api>=0.6.0",
#     "google-api-python-client>=2.0.0",
#     "google-auth-httplib2>=0.1.0",
#     "google-auth-oauthlib>=1.0.0",
#     "boto3>=1.26.0",
#     "yt-dlp>=2023.0.0",
#     "pyautogui>=0.9.0",
#     "pyperclip>=1.8.0",
#     "pandas>=1.3.0",
#     "pytz>=2022.0",
#     "markdown>=3.4.0",
#     "moviepy>=1.0.0",
#     "opencv-python>=4.5.0",
#     "selenium>=4.0.0",
#     "playwright>=1.40.0",
#     "beautifulsoup4>=4.11.0",
# ]
# ///

# list the videos in youtube channels
# get the video details
# if the video was uploaded in the last 30 days, and is not in one of the video list files,
# add it to the video list file
# Use AI to decide which video list to update
# Use AI to decide the line content to add to the video list file
# prompt the user to confirm which video list to update
# prompt the user to confirm the line to add to the video list file

import os
import glob
import json
import datetime
from pathlib import Path
from typing import List, Dict, Optional
import traceback
import time
from pprint import pprint
import requests

import groq
from youtubeManage.youtubeManageUtil import authenticate_youtube_mingdaoai, get_cached_video_details
from announceMock.makeWebhook.pushMakeUtil import confirm_video_link
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound
from youtube_transcript_api.formatters import TextFormatter
from ads.youtube_analyze.youtubeMetaUtil import download_transcript


def load_groq_key():
    """Load Groq API key from ~/.mingdaoai/groq.key"""
    key_path = Path.home() / '.mingdaoai' / 'groq.key'
    try:
        with open(key_path, 'r') as f:
            return f.read().strip()
    except FileNotFoundError:
        print(f"Error: Groq API key not found at {key_path}")
        raise

def create_groq_client():
    """Create and return a Groq client"""
    api_key = load_groq_key()
    return groq.Client(api_key=api_key)

def get_video_id_from_url(url: str) -> str:
    # Extract video ID from URL
    video_id = None
    if 'mingdaoschool.com/youtube' in url:
        from urllib.parse import parse_qs, urlparse
        video_id = parse_qs(urlparse(url).query)['v'][0]
    elif 'youtu.be/' in url:
        video_id = url.split('youtu.be/')[-1].split('?')[0]
    elif 'youtube.com/watch' in url:
        from urllib.parse import parse_qs, urlparse
        video_id = parse_qs(urlparse(url).query)['v'][0]
    elif 'youtube.com/shorts/' in url:
        video_id = url.split('youtube.com/shorts/')[-1].split('?')[0]
    else:
        assert False, f"Invalid video URL: {url}"
        
    assert len(video_id) < 20, f"Video ID {video_id} is too long. URL: {url}"
    return video_id

def get_youtube_url(video_id: str) -> str:
    return f'https://www.youtube.com/watch?v={video_id}'


def _transcript_via_youtube_api(video_id: str) -> Optional[str]:
    """Try to get transcript via YouTubeTranscriptApi (fetch any available). Returns text or None."""
    try:
        api = YouTubeTranscriptApi()
        fetched = api.fetch(video_id)
        if fetched:
            return TextFormatter().format_transcript(fetched)
    except (NoTranscriptFound, TranscriptsDisabled):
        pass
    except Exception as e:
        print(f"YouTubeTranscriptApi.fetch failed for {video_id}: {e}")
    return None


def _transcript_via_youtube_api_alternative(video_id: str) -> Optional[str]:
    """Alternative: list transcripts then find en / manually created / generated / first available."""
    try:
        api = YouTubeTranscriptApi()
        transcript_list = api.list(video_id)
        transcript = None
        try:
            transcript = transcript_list.find_transcript(['en'])
        except NoTranscriptFound:
            pass
        if not transcript:
            try:
                transcript = transcript_list.find_manually_created_transcript(['en'])
            except NoTranscriptFound:
                pass
        if not transcript:
            try:
                transcript = transcript_list.find_generated_transcript(['en'])
            except NoTranscriptFound:
                pass
        if not transcript:
            available = list(transcript_list)
            if available:
                transcript = available[0]
        if transcript:
            data = transcript.fetch()
            return TextFormatter().format_transcript(data)
    except (NoTranscriptFound, TranscriptsDisabled):
        pass
    except Exception as e:
        print(f"YouTubeTranscriptApi alternative failed for {video_id}: {e}")
    return None


def get_transcript_with_fallback(video_id: str) -> Optional[str]:
    """
    Get video transcript with fallbacks when primary source is unavailable.
    Order: (1) youtubeMetaUtil (yt-dlp), (2) YouTubeTranscriptApi.fetch, (3) YouTubeTranscriptApi list/find.
    """
    transcript = download_transcript(video_id)
    if transcript:
        return transcript
    print(f"Primary transcript source returned nothing for {video_id}, trying YouTubeTranscriptApi...")
    transcript = _transcript_via_youtube_api(video_id)
    if transcript:
        return transcript
    transcript = _transcript_via_youtube_api_alternative(video_id)
    return transcript


def isYouTubeVideoPrivate(youtube, video_id: str) -> bool:
    """
    Check if a YouTube video is private or not publicly accessible.
    
    Args:
        youtube: The authenticated YouTube API client
        video_id: The YouTube video ID to check
        
    Returns:
        bool: True if the video is private/unlisted/inaccessible, False if it's public
    """
    try:
        # First check using YouTube API
        video_response = youtube.videos().list(
            part='status,snippet',
            id=video_id
        ).execute()
        
        # If video not found, it's either deleted or private
        if not video_response.get('items'):
            return True
            
        video_details = video_response['items'][0]
        privacy_status = video_details['status'].get('privacyStatus', 'not set')
        
        # If API says it's private/unlisted, no need to check further
        if privacy_status in ['private', 'unlisted']:
            return True
            
        # Double check using anonymous access via oEmbed
        youtube_url = get_youtube_url(video_id)
        request_url = f'https://www.youtube.com/oembed?url={youtube_url}&format=json'
        anon_response = requests.get(request_url)
        
        # If we can't access it anonymously, it's not public
        return anon_response.status_code != 200
        
    except Exception as e:
        print(f"Error checking video privacy for {video_id}: {str(e)}")
        traceback.print_exc()
        # If we can't determine the status, assume it's private to be safe
        return True

def get_cache_dir() -> str:
    """Get the cache directory path."""
    cache_dir = os.path.join(os.path.dirname(__file__), '.cache')
    os.makedirs(cache_dir, exist_ok=True)
    return cache_dir

def read_existing_videos() -> Dict[str, List[Dict]]:
    """Read all existing video lists and return them organized by type."""
    videos_by_type = {}
    video_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'videos')
    
    # When using Ming Dao AI channel, only look at English lists
    #list_pattern = 'english-*-list.txt' if 'authenticate_youtube_mingdaoai' in str(authenticate_youtube_mingdaoai) else '*-list.txt'
    list_pattern = 'english-*-list.txt'
    list_files = glob.glob(os.path.join(video_dir, list_pattern))

    for list_file in list_files:
        video_type = os.path.basename(list_file).replace('-list.txt', '')
        videos_by_type[video_type] = []

        with open(list_file, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if line and not line.startswith('#'):
                    parts = line.split(';')
                    if len(parts) >= 3:
                        url = parts[2].strip()
                        if ' ' in url:
                            error_msg = f"URL contains spaces in file {list_file} at line {line_num}: {line}"
                            assert False, error_msg
                        video = {
                            'title': parts[0].strip(),
                            'description': parts[1].strip(),
                            'url': url,
                            'type': video_type
                        }
                        videos_by_type[video_type].append(video)

    return videos_by_type

def get_cached_video_metadata(youtube, channel_id: str) -> Optional[List[Dict]]:
    """Get playlist items from cache or fetch from YouTube API if cache is missing or expired."""
    try:
        cache_file = os.path.join(get_cache_dir(), f'channel_{channel_id}_playlist_items.json')
        print(f"📁 Cache file: {cache_file}")
        
        # Try to get from cache first
        if os.path.exists(cache_file):
            # Check if cache is less than 5 minutes old
            cache_age = time.time() - os.path.getmtime(cache_file)
            print(f"⏰ Cache age: {cache_age:.1f} seconds")
            if cache_age <= 300:  # 5 minutes = 300 seconds
                print(f"✅ Using cached playlist items for channel {channel_id}")
                with open(cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                print(f"⏰ Cache is {cache_age:.1f} seconds old (>5 minutes), fetching fresh data")
        else:
            print("📁 No cache file found, fetching fresh data")
            
        # If we get here, we need to fetch from YouTube API
        print(f"🌐 Fetching playlist items for channel {channel_id} from YouTube API")
        
        # Get channel uploads playlist ID
        print("🔍 Getting channel uploads playlist ID...")
        channel_response = youtube.channels().list(
            part='contentDetails,snippet',
            id=channel_id
        ).execute()
        
        if not channel_response.get('items'):
            print(f"❌ No channel found for ID: {channel_id}")
            return None
            
        channel_title = channel_response['items'][0]['snippet']['title']
        print(f"✅ Found channel: {channel_title}")
            
        uploads_playlist_id = channel_response['items'][0]['contentDetails']['relatedPlaylists']['uploads']
        print(f"📋 Got uploads playlist ID: {uploads_playlist_id}")
        
        # Get all playlist items
        items = []
        next_page_token = None
        page_count = 0
        
        while True:
            page_count += 1
            print(f"📄 Fetching page {page_count} of videos...")
            
            playlist_response = youtube.playlistItems().list(
                part='snippet',
                playlistId=uploads_playlist_id,
                maxResults=50,
                pageToken=next_page_token
            ).execute()
            
            new_items = playlist_response.get('items', [])
            print(f"✅ Found {len(new_items)} videos on page {page_count}")
            
            items.extend(new_items)
            
            next_page_token = playlist_response.get('nextPageToken')
            if not next_page_token:
                print("📄 No more pages to fetch")
                break
        
        # Cache the fetched items
        print(f"💾 Caching {len(items)} playlist items")
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(items, f, indent=2)
            
        return items
        
    except Exception as e:
        print(f"Error getting playlist items for channel {channel_id}: {str(e)}")
        traceback.print_exc()
        return None

def get_channel_videos(youtube, channel_id: str, days_back: int = 30) -> List[Dict]:
    """Get videos from a channel uploaded in the last N days."""
    try:
        print(f"🔍 Getting channel details for ID: {channel_id}")
        
        # Get playlist items (from cache or API)
        print("📋 Fetching playlist items...")
        items = get_cached_video_metadata(youtube, channel_id)
        if not items:
            print("❌ No playlist items found")
            return []
        
        print(f"✅ Found {len(items)} playlist items")
        
        # Process all items
        videos = []
        for item in items:
            published_at = datetime.datetime.strptime(
                item['snippet']['publishedAt'],
                '%Y-%m-%dT%H:%M:%SZ'
            )
            
            # Check if video is within the specified time range
            if datetime.datetime.now() - published_at > datetime.timedelta(days=days_back):
                print(f"Reached videos older than {days_back} days, stopping")
                break
                
            video_id = item['snippet']['resourceId']['videoId']
            video_url = get_youtube_url(video_id)
            
            # Get video details to check if it's a live broadcast
            print(f"\nChecking if video https://youtube.com/watch?v={video_id} is a livestream...")
            video_response = youtube.videos().list(
                part='snippet',
                id=video_id
            ).execute()
            
            if video_response.get('items'):
                video_details = video_response['items'][0]
                
                if video_details['snippet'].get('liveBroadcastContent') == 'upcoming':
                    print(f"Skipping live broadcast: {video_details['snippet']['title']}")
                    continue
            else:
                print(f"No video details found for ID: {video_id}")
                print("Debug - Video Response:")
                pprint(video_response)
                continue
            
            if confirm_video_link(video_url):
                videos.append({
                    'title': item['snippet']['title'],
                    'url': video_url,
                    'creation_date': published_at.strftime('%Y-%m-%d'),
                    'description': item['snippet']['description']
                })
                print(f"Added video: {item['snippet']['title']} ({published_at.strftime('%Y-%m-%d')})")
                
        print(f"Total videos found: {len(videos)}")
        return videos
        
    except Exception as e:
        print(f"Error getting videos from channel {channel_id}: {str(e)}")
        traceback.print_exc()
        return []

def get_available_video_types() -> List[str]:
    """Get list of available video types from the videos directory."""
    video_dir = Path(__file__).parent.parent / 'videos'
    list_files = list(video_dir.glob('english-*-list.txt'))
    assert len(list_files) > 0, f"No video list files found in the videos directory {video_dir}"
    return [f.stem.replace('-list', '') for f in list_files]

def determine_video_type(video: Dict) -> Optional[str]:
    """Use Groq AI to determine which video list this video belongs to."""
    try:
        client = create_groq_client()
        
        # Get available video types
        video_types = get_available_video_types()
        
        # Create prompt for AI
        prompt = f"""Based on the following video information, determine which category it belongs to from the available types: {', '.join(video_types)}

Video Title: {video['title']}
Description: {video['description']}

Please analyze the content and return ONLY the most appropriate category name from the available types. If you cannot determine a clear category, return 'unknown'.
"""
        
        # Call Groq API
        chat_completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.1-8b-instant",
            temperature=0.3,
            max_tokens=100,
        )
        
        # Get the response and clean it
        response = chat_completion.choices[0].message.content.strip().lower()
        
        # Check if the response is a valid video type
        if response in video_types:
            return response
        else:
            print(f"AI suggested type '{response}' which is not in available types: {video_types}")
            return None
            
    except Exception as e:
        print(f"Error in AI-based video type determination: {str(e)}")
        traceback.print_exc()
        return None

def format_video_line(video: Dict, title: str, description: str) -> str:
    """Format the video information into a line for the video list file."""
    return f"{title};{description};{video['url']}"

def update_video_list(video_type: str, video_line: str) -> bool:
    """Add the video line to the appropriate video list file."""
    try:
        video_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'videos')
        list_file = os.path.join(video_dir, f'{video_type}-list.txt')
        
        # Check if file exists and if it ends with a newline
        file_exists = os.path.exists(list_file)
        needs_newline = True
        if file_exists:
            with open(list_file, 'r', encoding='utf-8') as f:
                content = f.read()
                if content and content[-1] == '\n':
                    needs_newline = False
        
        # Append the new line with appropriate newline handling
        with open(list_file, 'a', encoding='utf-8') as f:
            if needs_newline:
                f.write('\n')
            f.write(f"{video_line}\n")
        return True
    except Exception as e:
        print(f"Error updating video list: {str(e)}")
        traceback.print_exc()
        return False

def get_example_videos(video_type: str, max_examples: int = 3) -> List[Dict]:
    """Get example videos from existing videos of the same type."""
    try:
        video_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'videos')
        list_file = os.path.join(video_dir, f'{video_type}-list.txt')
        
        examples = []
        with open(list_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    parts = line.split(';')
                    if len(parts) >= 3:
                        examples.append({
                            'title': parts[0].strip(),
                            'description': parts[1].strip()
                        })
                        if len(examples) >= max_examples:
                            break
        return examples
    except Exception as e:
        print(f"Error getting example videos: {str(e)}")
        traceback.print_exc()
        return []

def suggest_video_content(video: Dict, video_type: str) -> Optional[Dict[str, str]]:
    """Use Groq AI to suggest title and description for the video with retry logic."""
    max_retries = 3
    
    for attempt in range(max_retries):
        try:
            client = create_groq_client()
            
            # Get video transcript (with fallback when not available from primary source)
            video_id = get_video_id_from_url(video['url'])
            transcript = get_transcript_with_fallback(video_id)
            
            # Get example videos
            examples = get_example_videos(video_type)
            examples_json = json.dumps([{
                "title": example['title'],
                "description": example['description']
            } for example in examples], indent=2)
            
            # Create strict prompt for AI
            prompt = f"""Based on the following video information, generate a title and description.

Video Title: {video['title']}
Description: {video['description']}
Transcript: {transcript if transcript else 'No transcript available'}

Here are some examples of existing videos in the same category:

{examples_json}

CRITICAL: You must respond with ONLY a valid JSON object. No other text, explanations, or formatting.

Return exactly this JSON structure:
{{
    "title": "A concise, engaging title",
    "description": "A clear, informative description of the video content"
}}

Requirements:
* The title should be engaging and accurately represent the content
* The title should be very short, such as 6 words or fewer
* The description should be clear and concise. Start with a short question, then a short sentence explaining what viewers will learn
* The question should be related to real life benefits. It should not include the name of the technology.
* The answer should include the name of the technology if applicable.
* The description should be similar to the examples (not as long as the original)
* The description should use 1-2 very short and concise sentences, good for breathing when reading
* Follow the style and format of the examples

RESPOND WITH ONLY THE JSON OBJECT - NO OTHER TEXT."""
            
            # Call Groq API
            chat_completion = client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model="llama-3.1-8b-instant",
                temperature=0.7,
                max_tokens=1000,
            )
            
            # Get the response and clean it
            response = chat_completion.choices[0].message.content.strip()
            
            # Extract JSON from response more aggressively
            response = extract_json_from_response(response)
            
            if response:
                try:
                    result = json.loads(response)
                    # Validate the result has required fields
                    if 'title' in result and 'description' in result:
                        print(f"Successfully generated content on attempt {attempt + 1}")
                        return result
                    else:
                        print(f"Invalid JSON structure on attempt {attempt + 1}: missing required fields")
                        print(f"Response: {response}")
                except json.JSONDecodeError as e:
                    print(f"JSON decode error on attempt {attempt + 1}: {str(e)}")
                    print(f"Response: {response}")
            else:
                print(f"No JSON found in response on attempt {attempt + 1}")
                print(f"Raw response: {chat_completion.choices[0].message.content}")
            
            if attempt < max_retries - 1:
                print(f"Retrying... (attempt {attempt + 2}/{max_retries})")
                time.sleep(1)  # Brief delay before retry
                
        except Exception as e:
            print(f"Error in AI-based content generation (attempt {attempt + 1}): {str(e)}")
            if attempt < max_retries - 1:
                print(f"Retrying... (attempt {attempt + 2}/{max_retries})")
                time.sleep(1)
            else:
                traceback.print_exc()
    
    print(f"Failed to generate valid content after {max_retries} attempts")
    return None

def extract_json_from_response(response: str) -> Optional[str]:
    """Extract JSON from AI response, handling various formats."""
    if not response:
        return None
    
    # Remove markdown code block markers
    response = response.replace('```json', '').replace('```', '').strip()
    
    # Look for JSON object boundaries
    start_idx = response.find('{')
    end_idx = response.rfind('}')
    
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        json_str = response[start_idx:end_idx + 1]
        return json_str.strip()
    
    # If no clear boundaries, try the whole response
    return response.strip()

def get_skipped_videos_cache() -> Dict[str, str]:
    """Get the cache of skipped videos."""
    try:
        cache_file = os.path.join(get_cache_dir(), 'skipped_videos.json')
        if os.path.exists(cache_file):
            with open(cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    except Exception as e:
        print(f"Error reading skipped videos cache: {str(e)}")
        traceback.print_exc()
        return {}

def cache_skipped_video(video_id: str, reason: str) -> None:
    """Cache a skipped video with the reason."""
    try:
        cache_file = os.path.join(get_cache_dir(), 'skipped_videos.json')
        skipped_videos = get_skipped_videos_cache()
        skipped_videos[video_id] = reason
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(skipped_videos, f, indent=2)
    except Exception as e:
        print(f"Error writing skipped videos cache: {str(e)}")
        traceback.print_exc()

def is_video_skipped(video_id: str) -> Optional[str]:
    """Check if a video was previously skipped and return the reason if it was."""
    skipped_videos = get_skipped_videos_cache()
    return skipped_videos.get(video_id)

def main():
    print("=" * 60)
    print("Starting YouTube Video List Update Script with Enhanced Debugging")
    print("=" * 60)
    
    print("Step 1: Starting YouTube authentication...")
    try:
        youtube = authenticate_youtube_mingdaoai()
        print("✅ YouTube authentication successful!")
    except Exception as e:
        print(f"❌ YouTube authentication failed: {str(e)}")
        print(f"Traceback: {traceback.format_exc()}")
        return
    
    updates_made = False  # Track if any updates were made
    
    try:
        # Get the authenticated user's channel ID
        print("Step 2: Getting authenticated user's channel...")
        try:
            channels_response = youtube.channels().list(
                part='id,snippet',
                mine=True
            ).execute()
            print("✅ Channel list request successful!")
        except Exception as e:
            print(f"❌ Channel list request failed: {str(e)}")
            print(f"Traceback: {traceback.format_exc()}")
            return
        
        if not channels_response.get('items'):
            print("❌ Error: No channel found for authenticated user")
            return
        
        # Print the list of channel names found
        print("\nChannels found:")
        for item in channels_response.get('items', []):
            channel_name = item.get('snippet', {}).get('title', 'Unknown')
            channel_id = item.get('id', 'Unknown ID')
            print(f"- {channel_name} (ID: {channel_id})")

        channel = channels_response['items'][0]
        channel_id = channel['id']
        channel_title = channel['snippet']['title']
        print(f"✅ Found channel: {channel_title} (ID: {channel_id})")
        assert channel_title == "Ming Dao AI", f"Channel name must be 'Ming Dao AI', but got '{channel_title}'"
        
        # Read existing videos
        existing_videos = read_existing_videos()
        print(f"Found existing videos in {len(existing_videos)} categories")
        
        # Check for private videos in existing lists
        print("\nChecking for private videos in existing lists...")
        for video_type, videos in existing_videos.items():
            for video in videos:
                try:
                    video_id = get_video_id_from_url(video['url'])
                    
                    if isYouTubeVideoPrivate(youtube, video_id):
                        print(f"\nWarning: Video is not publicly accessible:")
                        print(f"Type: {video_type}")
                        print(f"Title: {video['title']}")
                        print(f"URL: {video['url']}")
                        if input("Remove this video from the list? (y/n): ").lower() == 'y':
                            video_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'videos')
                            list_file = os.path.join(video_dir, f'{video_type}-list.txt')
                            
                            # Read all lines
                            with open(list_file, 'r', encoding='utf-8') as f:
                                lines = f.readlines()
                            
                            # Filter out the line containing this video's URL
                            new_lines = [line for line in lines if video['url'] not in line]
                            
                            # Write back the filtered lines
                            with open(list_file, 'w', encoding='utf-8') as f:
                                f.writelines(new_lines)
                            print("Video removed from list.")
                            updates_made = True  # Mark that an update was made
                            
                except Exception as e:
                    print(f"\nError checking video {video['url']}: {str(e)}")
                    traceback.print_exc()
                    continue
        
        # Get recent videos from the channel
        print(f"Step 3: Fetching videos from channel: {channel_title}")
        try:
            recent_videos = get_channel_videos(youtube, channel_id)
            print(f"✅ Successfully retrieved {len(recent_videos)} videos from channel {channel_title}")
        except Exception as e:
            print(f"❌ Error fetching videos from channel {channel_title}: {str(e)}")
            print(f"Traceback: {traceback.format_exc()}")
            return
        
        if not recent_videos:
            print(f"No videos found for channel {channel_title}")
            return
            
        print(f"\nFound {len(recent_videos)} recent videos:")
        for video in recent_videos:
            print(f"\nVideo: {video['title']}")
            print(f"Date: {video['creation_date']}")
            print(f"URL: {video['url']}")
            
            # Check if video exists in any list
            found_in = []
            current_video_id = get_video_id_from_url(video['url'])
            
            # Check if video was previously skipped
            skip_reason = is_video_skipped(current_video_id)
            if skip_reason:
                print(f"Video was previously skipped: {skip_reason}")
                continue
            
            for video_type, videos in existing_videos.items():
                for v in videos:
                    existing_video_id = get_video_id_from_url(v['url'])
                    if current_video_id == existing_video_id:
                        found_in.append(video_type)
                        break
            
            if found_in:
                print(f"Found in existing lists: {', '.join(found_in)}")
                print("Skipping to next video...")
                continue
            else:
                print("Not found in any existing list")
                
            # Check if video is too old (more than 30 days)
            video_date = datetime.datetime.strptime(video['creation_date'], '%Y-%m-%d')
            if datetime.datetime.now() - video_date > datetime.timedelta(days=30):
                print("Status: Too old to be added (more than 30 days)")
                continue  # Skip to next video if too old
            else:
                print("Status: Eligible for adding")
            
            print(f"Video privacy status: [public], proceeding with content generation...")
            
            # Determine video type
            video_type = determine_video_type(video)
            if not video_type:
                print("\nNew video found:")
                print(f"Title: {video['title']}")
                print(f"URL: {video['url']}")
                print(f"Creation date: {video['creation_date']}")
                
                # Get available video types
                available_types = get_available_video_types()
                print("\nAvailable video types:")
                for i, type_name in enumerate(available_types, 1):
                    print(f"{i}. {type_name}")
                print("s. Skip this video")
                
                while True:
                    selection = input("\nEnter video type number, name, or 's' to skip: ").strip().lower()
                    if selection == 's':
                        reason = input("Enter reason for skipping (e.g., 'wrong category', 'not relevant'): ").strip()
                        if reason:
                            cache_skipped_video(current_video_id, reason)
                            print(f"Video skipped and reason cached: {reason}")
                        video_type = ""
                        break
                    elif not selection:
                        video_type = ""
                        break
                        
                    # Try to match by number
                    try:
                        index = int(selection) - 1
                        if 0 <= index < len(available_types):
                            video_type = available_types[index]
                            break
                    except ValueError:
                        pass
                        
                    # Try to match by name
                    if selection in available_types:
                        video_type = selection
                        break
                        
                    print(f"Invalid selection. Please enter a number (1-{len(available_types)}), type name, or 's' to skip.")
            
            if video_type:
                # Get example subjects
                examples = get_example_videos(video_type)
                if examples:
                    print(f"\nExample videos from {video_type}:")
                    for example in examples:
                        print(f"Title: {example['title']}")
                        print(f"Description: {example['description']}")
                        print()
                    print()
                
                # Get AI-suggested content
                suggested_content = suggest_video_content(video, video_type)
                
                # Get video transcript for human review (with fallback when not available)
                video_id = get_video_id_from_url(video['url'])
                transcript = get_transcript_with_fallback(video_id)
                
                print("\nVideo Details:")
                print(f"Original Title: {video['title']}")
                if video['description']:
                    print(f"Original Description: {video['description']}")
                if transcript:
                    print("\nTranscript (excerpt, first 2000 chars):")
                    print(transcript[:2000] + ("..." if len(transcript) > 2000 else ""))
                else:
                    print("\nTranscript: Not available (cannot get video transcript)")
                
                if suggested_content:
                    print("\nAI-suggested content:")
                    print(f"Title: {suggested_content['title']}")
                    print(f"Description: {suggested_content['description']}")
                    
                    print(f"\nVideo URL: {video['url']}")
                    print(f"Video Type: {video_type}")
                    print("\nDo you want to:")
                    print("1. Use all AI suggestions")
                    print("2. Edit some fields")
                    print("3. Enter all fields manually")
                    print("4. Skip this video")
                    choice = input("Enter your choice (1-4): ").strip()
                    
                    if choice == "4":
                        reason = input("Enter reason for skipping (e.g., 'not relevant', 'poor quality'): ").strip()
                        cache_skipped_video(current_video_id, reason)
                        print(f"Video skipped and reason cached: {reason}")
                        continue
                    
                    if choice == "1":
                        content = suggested_content
                    elif choice == "2":
                        content = suggested_content.copy()
                        if input("Edit title? (y/n): ").lower() == 'y':
                            content['title'] = input("Enter title: ").strip()
                        if input("Edit description? (y/n): ").lower() == 'y':
                            content['description'] = input("Enter description: ").strip()
                    else:
                        content = {
                            'title': input("Enter title: ").strip(),
                            'description': input("Enter description: ").strip()
                        }
                else:
                    content = {
                        'title': input("Enter title: ").strip(),
                        'description': input("Enter description: ").strip()
                    }
                
                if content['title'] and content['description']:
                    video_line = format_video_line(video, content['title'], content['description'])
                    print(f"\nProposed line to add: {video_line}")
                    if input("Confirm adding this line? (y/n): ").lower() == 'y':
                        if update_video_list(video_type, video_line):
                            print("Video added successfully!")
                            updates_made = True  # Mark that an update was made
                        else:
                            print("Failed to add video.")
        
        # After all processing is complete, if any updates were made, run uploadYoutubeVideoList.py
        if updates_made:
            print("\nUpdates were made to video lists. Running uploadYoutubeVideoList.py to update S3...")
            try:
                import subprocess
                script_dir = os.path.dirname(os.path.abspath(__file__))
                upload_script = os.path.join(script_dir, 'uploadYoutubeVideoList.py')
                subprocess.run(['python3', upload_script], check=True)
                print("Successfully uploaded video list to S3")
            except subprocess.CalledProcessError as e:
                print(f"Error running uploadYoutubeVideoList.py: {str(e)}")
                traceback.print_exc()
        else:
            print("\nNo updates were made to video lists. Skipping S3 upload.")
            
    except Exception as e:
        print(f"Error getting authenticated user's channel: {str(e)}")
        traceback.print_exc()
        return

if __name__ == '__main__':
    main()
