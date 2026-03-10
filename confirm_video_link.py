#!/usr/bin/env uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "boto3>=1.26.0",
#     "requests>=2.25.0",
#     "botocore>=1.29.0",
# ]
# ///

import boto3
import requests
import sys
from urllib.parse import urlparse
from botocore.exceptions import ClientError

def debug_print(message):
    print(f"DEBUG: {message}", file=sys.stderr)

def confirm_video_exists(video_url):
    """
    Confirms if a video exists and is accessible at the given S3 URL
    Returns True if video exists and is accessible, False otherwise
    """
    try:
        # Parse the URL to get bucket and key
        parsed_url = urlparse(video_url)
        path_parts = parsed_url.path.strip('/').split('/')
        
        if 's3.amazonaws.com' in parsed_url.netloc:
            bucket_name = parsed_url.netloc.split('.')[0]
            key = '/'.join(path_parts)
        else:
            bucket_name = path_parts[0]
            key = '/'.join(path_parts[1:])

        debug_print(f"Checking bucket: {bucket_name}, key: {key}")

        # Create S3 client
        s3_client = boto3.client('s3')
        
        # Try to get object metadata (head request)
        response = s3_client.head_object(
            Bucket=bucket_name,
            Key=key
        )
        
        # Check if content type is video
        content_type = response.get('ContentType', '')
        if not content_type.startswith('video/'):
            debug_print(f"Warning: Content-Type '{content_type}' does not appear to be a video")
        
        # Also try a direct HTTP request to verify public access
        response = requests.head(video_url)
        response.raise_for_status()
        
        debug_print("Video is accessible via direct URL")
        return True
        
    except ClientError as e:
        debug_print(f"AWS Error: {e}")
        return False
    except requests.exceptions.RequestException as e:
        debug_print(f"HTTP Error: {e}")
        return False
    except Exception as e:
        debug_print(f"Unexpected error: {e}")
        return False

def main():
    if len(sys.argv) != 2:
        print("Usage: python3 confirm_video_link.py <video_url>")
        print("Example: python3 confirm_video_link.py https://designmake.s3.amazonaws.com/example.mp4")
        sys.exit(1)
        
    video_url = sys.argv[1]
    success = confirm_video_exists(video_url)
    
    if success:
        print("✅ Video is accessible")
        sys.exit(0)
    else:
        print("❌ Video is not accessible")
        sys.exit(1)

if __name__ == "__main__":
    main() 