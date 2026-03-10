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

from linkedin_api import pushLinkedInYoutube, confirm_video_link
from videoUtil import get_valid_video, update_history, webhook_history_file_key

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
            
        video = get_valid_video(webhook_history_file_key)
        if video and confirm_video_link(video['url']):
            text = f"""
{video['title']}

To book private 1-1 career coaching or interview coaching, please visit mingdaoschool.com or send me a private message.
            """.strip()
            
            print(f"Uploading\n{text}")
            pushLinkedInYoutube(text, video_url=video['url'], video_title=video['title'], dry_run=args.dry_run)
            if not args.dry_run:
                update_history(video, webhook_history_file_key)
        else:
            print("No valid video to post or video link is invalid.")
            
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
