#!/usr/bin/env uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "boto3>=1.26.0",
#     "requests>=2.25.0",
# ]
# ///
import json
import os
from datetime import datetime

import boto3
import requests
import traceback



class LinkedInPoster:
    def __init__(self):
        self.api_version = "202404"
        self.api_base_url = "https://api.linkedin.com"
        self.token_path = os.path.expanduser('~/.mingdaoai/linkedin_token.json')
        self.token_data = self._load_token_data()

    def _load_token_data(self) -> dict:
        """Load token data from file if it exists and is not expired"""
        try:
            if os.path.exists(self.token_path):
                with open(self.token_path, 'r') as f:
                    token_data = json.load(f)
                    if token_data.get('expires_at', 0) > int(datetime.now().timestamp()):
                        return token_data
                    else:
                        print("Token has expired. Please update the token file.")
            else:
                print("No token found. Please place a valid token file at ~/.mingdaoai/linkedin_token.json")
        except Exception as e:
            print(f"Error loading token data: {str(e)}")
        return None

    def _get_video_id(self, video_url: str) -> str:
        """Extract video ID from YouTube URL in various formats"""
        try:
            if "mingdaoschool.com/youtube" in video_url:
                video_id = video_url.split("v=")[1]
            elif "youtube.com/watch?v=" in video_url:
                video_id = video_url.split("v=")[1].split("&")[0]
            elif "youtu.be/" in video_url:
                video_id = video_url.split("youtu.be/")[1].split("?")[0]
            elif "youtube.com/shorts/" in video_url:
                video_id = video_url.split("shorts/")[1].split("?")[0]
            else:
                return None
            return video_id
        except Exception as e:
            print(f"Error extracting video ID: {str(e)}")
            traceback.print_exc()
            return None

    def _get_thumbnail_url(self, video_id: str) -> str:
        """Get YouTube thumbnail URL for a video ID"""
        if not video_id:
            return None
        thumbnail_url = f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"
        return thumbnail_url
    def create_post(self, text: str, visibility: str = "PUBLIC", media_url: str = None, thumbnail_url: str = None, video_title: str = None) -> dict:
        """
        Create a post on LinkedIn
        Args:
            text: The text content of the post
            visibility: Post visibility (PUBLIC or CONNECTIONS)
            media_url: Optional URL of the media to include in the post
            thumbnail_url: Optional URL of the thumbnail image for the media
            video_title: Optional title of the video
        Returns:
            dict: Response from LinkedIn API
        """
        if not self.token_data:
            raise ValueError("No valid token found. Please ensure a valid token file exists at ~/.mingdaoai/linkedin_token.json")

        url = f"{self.api_base_url}/v2/ugcPosts"
        headers = {
            "Authorization": f"Bearer {self.token_data['access_token']}",
            "Accept": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
            "LinkedIn-Version": self.api_version,
            "Content-Type": "application/json"
        }
        
        payload = {
            "author": self.token_data['person_urn'],
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {
                        "text": text
                    },
                    "shareMediaCategory": "ARTICLE" if media_url else "NONE"
                }
            },
            "visibility": {
                "com.linkedin.ugc.MemberNetworkVisibility": visibility
            }
        }

        if media_url:
            media_object = {
                "status": "READY",
                "originalUrl": media_url,
                "title": {
                    "text": video_title or "Video"
                }
            }
            
            if thumbnail_url:
                media_object["thumbnails"] = [{
                    "url": thumbnail_url,
                    "resolvedUrl": thumbnail_url
                }]
            
            payload["specificContent"]["com.linkedin.ugc.ShareContent"]["media"] = [media_object]

        try:
            response = requests.post(url, headers=headers, json=payload)
            if response.status_code != 201:
                print(f"Response status: {response.status_code}")
                print(f"Response body: {response.text}")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error creating post: {str(e)}")
            raise


def pushLinkedInYoutube(textContent, video_url=None, video_title=None, dry_run=False):
    """
    Post directly to LinkedIn using the API
    Args:
        textContent: The text content to post
        video_url: Optional URL of the video to include in the post
        video_title: Optional title of the video
        dry_run: If True, simulate the post without actually posting
    """
    poster = LinkedInPoster()
    try:
        thumbnail_url = None
        if video_url:
            video_id = poster._get_video_id(video_url)
            if video_id:
                thumbnail_url = poster._get_thumbnail_url(video_id)
                if not thumbnail_url:
                    print("Warning: Could not find valid thumbnail for video")
        
        if dry_run:
            print("[DRY RUN] Would post the following content:")
            print("=" * 50)
            print(f"Text content: {textContent}")
            if video_url:
                print(f"Video URL: {video_url}")
                print(f"Video title: {video_title}")
                if thumbnail_url:
                    try:
                        response = requests.head(thumbnail_url)
                        if response.status_code == 200:
                            print(f"Thumbnail URL (verified): {thumbnail_url}")
                        else:
                            print(f"Warning: Thumbnail URL returned status {response.status_code}: {thumbnail_url}")
                    except Exception as e:
                        print(f"Warning: Could not verify thumbnail URL: {thumbnail_url}")
                        print(f"Error: {str(e)}")
                else:
                    print("No thumbnail URL available")
            print("=" * 50)
            print("[DRY RUN] No actual post made to LinkedIn")
            return
        result = poster.create_post(textContent, media_url=video_url, thumbnail_url=thumbnail_url, video_title=video_title)
        print("Post created successfully:", result)
    except Exception as e:
        print(f"Failed to create post: {str(e)}")
        traceback.print_exc()
        raise






def confirm_video_link(video_url):
    try:
        response = requests.head(video_url)
        return response.status_code == 200
    except requests.RequestException:
        return False
