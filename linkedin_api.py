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
from typing import Optional

import boto3
import requests
import traceback



class LinkedInPoster:
    def __init__(self):
        # Legacy /v2 calls ignore this; the versioned /rest calls require a *supported* version,
        # and LinkedIn sunsets old ones (202508 went out on 2026-08-17). Keep it current.
        self.api_version = os.environ.get("LINKEDIN_VERSION", "202608")
        self.legacy_api_version = "202404"
        # The versioned Content APIs (/rest/posts, /rest/images) replace /v2/ugcPosts and
        # /v2/assets. Our existing member token already works against them — an initializeUpload
        # probe on 2026-08-18 returned 200 with an image URN — so this needs no new credential.
        # Set LINKEDIN_USE_VERSIONED=0 to fall straight back to the legacy path.
        self.use_versioned = os.environ.get(
            "LINKEDIN_USE_VERSIONED", "1").strip().lower() not in {"0", "false", "no"}
        self.api_base_url = "https://api.linkedin.com"
        self.token_path = os.path.expanduser('~/.mingdaoai/linkedin_token.json')
        self.token_data = self._load_token_data()

    def _load_token_data(self) -> Optional[dict]:
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

    def _get_video_id(self, video_url: str) -> Optional[str]:
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

    def _get_thumbnail_url(self, video_id: Optional[str]) -> Optional[str]:
        """Get YouTube thumbnail URL for a video ID"""
        if not video_id:
            return None
        thumbnail_url = f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"
        return thumbnail_url

    def _register_upload_asset(self, file_size: int, media_type: str = "image/jpeg") -> dict:
        """Register an asset upload with LinkedIn Assets API.
        
        Args:
            file_size: Size of the file in bytes
            media_type: MIME type of the media
            
        Returns:
            dict containing upload_url and asset_urn
        """
        if not self.token_data:
            raise ValueError("No valid token found")
        
        if self.use_versioned:
            return self._initialize_image_upload()

        url = f"{self.api_base_url}/v2/assets?action=registerUpload"
        headers = {
            "Authorization": f"Bearer {self.token_data['access_token']}",
            "Accept": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
            "LinkedIn-Version": self.api_version,
            "Content-Type": "application/json"
        }
        
        payload = {
            "registerUploadRequest": {
                "recipes": [
                    "urn:li:digitalmediaRecipe:feedshare-image"
                ],
                "owner": self.token_data['person_urn'],
                "serviceRelationships": [
                    {
                        "relationshipType": "OWNER",
                        "identifier": "urn:li:userGeneratedContent"
                    }
                ],
                "supportedUploadMechanism": ["SYNCHRONOUS_UPLOAD"]
            }
        }
        
        try:
            response = requests.post(url, headers=headers, json=payload)
            if response.status_code != 200:
                print(f"Response status: {response.status_code}")
                print(f"Response body: {response.text}")
            response.raise_for_status()
            result = response.json()
            
            # Extract upload URL and asset URN
            value = result.get('value', {})
            upload_mechanism = value.get('uploadMechanism', {})
            upload_http_request = upload_mechanism.get('com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest', {})
            upload_url = upload_http_request.get('uploadUrl')
            asset_urn = value.get('asset')
            
            if not upload_url or not asset_urn:
                raise Exception("Failed to extract upload URL or asset URN from response")
            
            return {
                'upload_url': upload_url,
                'asset_urn': asset_urn,
                'headers': upload_http_request.get('headers', {})
            }
        except Exception as e:
            print(f"Error registering upload: {str(e)}")
            raise

    def _versioned_headers(self) -> dict:
        """Headers every versioned Content API call requires."""
        return {
            "Authorization": f"Bearer {self.token_data['access_token']}",
            "Accept": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
            "LinkedIn-Version": self.api_version,
            "Content-Type": "application/json",
        }

    def _initialize_image_upload(self) -> dict:
        """Register an image with the Images API, which replaces the Assets API.

        Returns the same shape as the legacy registerUpload path — upload_url, asset_urn, headers
        — so the caller does not care which API produced it. The URN differs in kind
        (urn:li:image:... rather than urn:li:digitalmediaAsset:...) and must be paired with the
        matching post API, which is why the two switch together on self.use_versioned.
        """
        if not self.token_data:
            raise ValueError("No valid token found")
        url = f"{self.api_base_url}/rest/images?action=initializeUpload"
        payload = {"initializeUploadRequest": {"owner": self.token_data["person_urn"]}}
        response = requests.post(url, headers=self._versioned_headers(), json=payload, timeout=60)
        if response.status_code != 200:
            print(f"initializeUpload failed {response.status_code}: {response.text[:300]}")
        response.raise_for_status()
        value = response.json().get("value", {})
        upload_url, image_urn = value.get("uploadUrl"), value.get("image")
        if not upload_url or not image_urn:
            raise Exception("Images API returned no uploadUrl/image URN")
        return {"upload_url": upload_url, "asset_urn": image_urn, "headers": {}}

    def _create_post_versioned(self, text: str, visibility: str, image_urn: Optional[str]) -> dict:
        """Create a member post through the Posts API, which replaces ugcPosts.

        The response carries the new post's URN in the x-restli-id header rather than a body, so
        the return is shaped like the legacy one — {"id": urn} — for callers and receipts.
        """
        payload = {
            "author": self.token_data["person_urn"],
            "commentary": text,
            "visibility": visibility,
            "distribution": {
                "feedDistribution": "MAIN_FEED",
                "targetEntities": [],
                "thirdPartyDistributionChannels": [],
            },
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False,
        }
        if image_urn:
            payload["content"] = {"media": {"id": image_urn}}
        response = requests.post(f"{self.api_base_url}/rest/posts",
                                 headers=self._versioned_headers(), json=payload, timeout=120)
        if response.status_code not in (200, 201):
            print(f"/rest/posts failed {response.status_code}: {response.text[:400]}")
        response.raise_for_status()
        urn = response.headers.get("x-restli-id", "")
        print(f"Post created via the versioned Posts API: {urn}")
        return {"id": urn}

    def _upload_image_binary(self, upload_url: str, image_path: str, headers: Optional[dict] = None) -> bool:
        """Upload image binary data to LinkedIn.
        
        Args:
            upload_url: URL returned from register_upload_asset
            image_path: Path to image file
            headers: Optional headers for upload
            
        Returns:
            bool indicating success
        """
        if not self.token_data:
            raise ValueError("No valid token found")
        
        try:
            with open(image_path, 'rb') as f:
                image_data = f.read()
            
            upload_headers = {
                "Authorization": f"Bearer {self.token_data['access_token']}",
                "Content-Type": "image/jpeg"
            }
            if headers:
                upload_headers.update(headers)
            
            response = requests.put(upload_url, headers=upload_headers, data=image_data)
            
            if response.status_code not in [200, 201]:
                print(f"Upload failed with status {response.status_code}: {response.text}")
                return False
            
            print(f"Image uploaded successfully: {image_path}")
            return True
        except Exception as e:
            print(f"Error uploading image: {str(e)}")
            return False

    def create_post(self, text: str, visibility: str = "PUBLIC", media_url: Optional[str] = None, thumbnail_url: Optional[str] = None, video_title: Optional[str] = None, image_urn: Optional[str] = None) -> dict:
        """
        Create a post on LinkedIn
        Args:
            text: The text content of the post
            visibility: Post visibility (PUBLIC or CONNECTIONS)
            media_url: Optional URL of the media to include in the post (for ARTICLE posts)
            thumbnail_url: Optional URL of the thumbnail image for the media
            video_title: Optional title of the video
            image_urn: Optional URN of an uploaded image asset (for IMAGE posts)
        Returns:
            dict: Response from LinkedIn API
        """
        if not self.token_data:
            raise ValueError("No valid token found. Please ensure a valid token file exists at ~/.mingdaoai/linkedin_token.json")

        # Article posts still go the legacy route: their versioned equivalent is a different
        # content shape (content.article with an uploaded thumbnail), and nothing in this channel
        # posts articles — every post carries a diagram image.
        if self.use_versioned and not media_url:
            return self._create_post_versioned(text, visibility, image_urn)

        url = f"{self.api_base_url}/v2/ugcPosts"
        headers = {
            "Authorization": f"Bearer {self.token_data['access_token']}",
            "Accept": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
            "LinkedIn-Version": self.api_version,
            "Content-Type": "application/json"
        }
        
        # Determine shareMediaCategory based on inputs
        if image_urn:
            share_media_category = "IMAGE"
        elif media_url:
            share_media_category = "ARTICLE"
        else:
            share_media_category = "NONE"
        
        payload = {
            "author": self.token_data['person_urn'],
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {
                        "text": text
                    },
                    "shareMediaCategory": share_media_category
                }
            },
            "visibility": {
                "com.linkedin.ugc.MemberNetworkVisibility": visibility
            }
        }

        if image_urn:
            # IMAGE post with asset URN
            media_object = {
                "status": "READY",
                "media": image_urn
            }
            payload["specificContent"]["com.linkedin.ugc.ShareContent"]["media"] = [media_object]
        elif media_url:
            # ARTICLE post with external URL
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






def pushLinkedInImage(textContent, image_path, dry_run=False):
    """
    Post an image directly to LinkedIn using the API
    Args:
        textContent: The text content to post
        image_path: Path to image file
        dry_run: If True, simulate the post without actually posting
    """
    poster = LinkedInPoster()
    try:
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image file not found: {image_path}")
        
        file_size = os.path.getsize(image_path)
        
        if dry_run:
            print("[DRY RUN] Would post the following image content:")
            print("=" * 50)
            print(f"Text content: {textContent}")
            print(f"Image path: {image_path}")
            print(f"File size: {file_size} bytes")
            print("=" * 50)
            print("[DRY RUN] No actual post made to LinkedIn")
            return
        
        # Register upload asset
        upload_info = poster._register_upload_asset(file_size)
        upload_url = upload_info['upload_url']
        asset_urn = upload_info['asset_urn']
        headers = upload_info.get('headers', {})
        
        # Upload image binary
        success = poster._upload_image_binary(upload_url, image_path, headers)
        if not success:
            raise Exception("Failed to upload image to LinkedIn")
        
        # Create post with image URN
        result = poster.create_post(textContent, image_urn=asset_urn)
        print("Image post created successfully:", result)
    except Exception as e:
        print(f"Failed to create image post: {str(e)}")
        traceback.print_exc()
        raise


def confirm_video_link(video_url):
    try:
        response = requests.head(video_url)
        return response.status_code == 200
    except requests.RequestException:
        return False
