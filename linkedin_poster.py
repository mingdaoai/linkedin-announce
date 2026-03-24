#!/usr/bin/env uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "boto3>=1.26.0",
#     "requests>=2.25.0",
# ]
# ///
import argparse
import sys
import traceback

from linkedin_api import pushLinkedInYoutube, pushLinkedInImage, confirm_video_link
from videoUtil import get_valid_post, download_linkedin_post_assets, update_history, webhook_history_file_key

def validate_args(args):
    """Validate the parsed arguments."""
    # Currently only dry-run is supported, but this function can be extended
    # for future argument validation
    return True

def main():
    parser = argparse.ArgumentParser(
        description='Push video content to LinkedIn',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Simulate pushing without actually posting or updating history'
    )

    try:
        # First parse with default settings to get help text if needed
        args = parser.parse_args()
        
        # Then parse strictly to catch unknown arguments
        parser_strict = argparse.ArgumentParser(allow_abbrev=False)
        parser_strict.add_argument('--dry-run', action='store_true')
        _, unknown = parser_strict.parse_known_args()
        
        if unknown:
            print(f"Error: unrecognized arguments: {' '.join(unknown)}")
            parser.print_help()
            return 1
            
        if not validate_args(args):
            print("Error: Invalid argument values")
            parser.print_help()
            return 1
            
        post = get_valid_post(webhook_history_file_key)
        if not post:
            print("No valid post (video or LinkedIn image) to publish.")
            return 1
        
        post_type = post.get('post_type')
        if post_type == 'video':
            if not confirm_video_link(post['url']):
                print(f"Video link is invalid: {post['url']}")
                return 1
            
            text = f"""
{post['title']}

To book private 1-1 career coaching or interview coaching, please visit mingdaoschool.com or send me a private message.
            """.strip()
            
            print(f"Uploading video link post:\n{text}")
            pushLinkedInYoutube(text, video_url=post['url'], video_title=post['title'], dry_run=args.dry_run)
            if not args.dry_run:
                update_history(post, webhook_history_file_key)
        
        elif post_type == 'linkedin-image':
            assets = download_linkedin_post_assets(post)
            with open(assets['post_text'], 'r', encoding='utf-8') as f:
                post_text = f.read()
            
            print(f"Uploading LinkedIn image post:\n{post_text[:200]}...")
            pushLinkedInImage(post_text, assets['image_path'], dry_run=args.dry_run)
            if not args.dry_run:
                update_history(post, webhook_history_file_key)
        
        else:
            print(f"Unknown post type: {post_type}")
            return 1
            
        return 0
        
    except argparse.ArgumentError as e:
        print(f"Error: {str(e)}")
        parser.print_help()
        return 1
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
