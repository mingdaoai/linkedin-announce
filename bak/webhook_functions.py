#!/usr/bin/env python3
"""
DEPRECATED make.com webhook functions.
Previously used to trigger Make.com automations for LinkedIn, TikTok, and YouTube.
Now replaced by direct LinkedIn API integration.
"""

import json
import os
import traceback

import boto3
import requests

# URL to post the content (Make.com webhook)
url = "https://hook.us1.make.com/20nsx4oowyzju2sxmunjpd7x8sw4x9wq"


def confirm_video_link(video_url):
    """Validate that a video URL is accessible."""
    try:
        response = requests.head(video_url)
        return response.status_code == 200
    except requests.RequestException:
        return False


def pushMakeWebhook(content):
    """Post content to Make.com webhook."""
    actualContent = content.copy()
    actualContent["json"] = json.dumps(content, indent=2)
    # Post the content to the URL
    response = requests.post(url, json=actualContent)

    # Check the response status
    if response.status_code == 200:
        print("Content posted successfully")
    else:
        print(f"Failed to post content. Status code: {response.status_code}")


def pushLinkedInWebhook(textContent, includeKen=False, includeXiao=False, includeMingDao=False, includeAll=False):
    """Trigger LinkedIn post via Make.com webhook."""
    content = {
        "textContent": textContent,
        "isLinkedinKen": includeKen or includeAll,
        "isLinkedinXiao": includeXiao or includeAll,
        "isLinkedinMingdao": includeMingDao or includeAll,
    }
    pushMakeWebhook(content)


def pushTiktok(title, videoFile, videoTitle, isChinese=False, isEnglish=False):
    """Upload video to S3 and trigger TikTok posting via Make.com (incomplete)."""
    assert os.path.exists(videoFile), f"Video file not found at {videoFile}"
    # upload video to S3 first to bucket designmake under the folder tiktok
    s3 = boto3.client('s3')
    s3_key = f'tiktok/{videoTitle}.mp4'
    s3.upload_file(videoFile, 'designmake', s3_key)
    
    # Generate the public S3 URL
    video_url = f'https://designmake.s3.amazonaws.com/{s3_key}'

    # confirm the video link is valid
    assert confirm_video_link(video_url), f"Video link is not valid: {video_url}"
    
    content = {
        "title": title,
        "videoLink": video_url,
        "videoTitle": videoTitle,
        "isChinese": isChinese,
        "isEnglish": isEnglish,
    }
    # Note: function incomplete - no call to pushMakeWebhook


def pushYoutube(title, videoFile, videoTitle, isChinese=False, isEnglish=False):
    """Upload video to S3 and trigger YouTube posting via Make.com."""
    assert isChinese or isEnglish, "At least one language must be specified"
    assert isChinese != isEnglish, "Chinese and English cannot be both True"

    assert os.path.exists(videoFile), f"Video file not found at {videoFile}"
    # upload video to S3 first to bucket designmake under the folder tiktok
    s3 = boto3.client('s3')
    videoFileBaseName = os.path.basename(videoFile)
    s3_key = f'youtube/{videoFileBaseName}'
    s3.upload_file(videoFile, 'designmake', s3_key)
    
    # Generate the public S3 URL
    video_url = f'https://designmake.s3.amazonaws.com/{s3_key}'

    # confirm the video link is valid
    assert confirm_video_link(video_url), f"Video link is not valid: {video_url}"
    
    content = {
        "title": title,
        "videoTitle": videoTitle,
        "videoLink": video_url,
        "isYoutubeMingChinese": isChinese,
        "isYoutubeMingEnglish": isEnglish,
    }
    pushMakeWebhook(content)


def test():
    """Test function for Make.com webhook."""
    # Content to be posted
    content = {
        "title": "test title",
        "textContent": "text content",

        "videoLink": "video url",
        "videoTitle": "video title",
        "videoDescription": "video description",
        "videoImageUrl": "video image url",
        "videoThumbnailUrl": "video thumbnail url",

        "imageName": "image name",
        "imageUrl": "image url",
        "isYoutubeMingChinese": False,
        "isYoutubeMingEnglish": False,
        "isTiktokChinese": False,
        "isTiktokEnglish": False,
        "isText": False,
        "isImage": False,
        "isVideo": False,
        "isLinkedinKen": False,
        "isLinkedinMingdao": False,
        "isLinkedinXiao": False,
    }

    pushMakeWebhook(content)


if __name__ == "__main__":
    test()