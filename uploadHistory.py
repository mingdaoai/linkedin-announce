#!/usr/bin/env uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "boto3>=1.26.0",
# ]
# ///
import os
import boto3
import argparse

s3_client = boto3.client('s3')
bucket_name = 'dscub'
history_file_key = 'videos/history.txt'

def upload_history(dry_run=False):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    cache_dir = os.path.join(script_dir, '.cache')
    local_history_file = os.path.join(cache_dir, 'history.txt')
    
    # Create cache directory if it doesn't exist
    os.makedirs(cache_dir, exist_ok=True)
    
    if not os.path.exists(local_history_file):
        print(f"Local history file not found: {local_history_file}")
        return False
    
    try:
        with open(local_history_file, 'r', encoding='utf-8') as file:
            history_content = file.read()
        
        if dry_run:
            print(f"[DRY RUN] Would upload history file to S3: {bucket_name}/{history_file_key}")
            print(f"[DRY RUN] File content length: {len(history_content)} characters")
            return True
        
        # Upload to S3
        s3_client.put_object(
            Bucket=bucket_name,
            Key=history_file_key,
            Body=history_content.encode('utf-8'),
            ContentType='text/plain; charset=utf-8'
        )
        print(f"Successfully uploaded history to S3: {bucket_name}/{history_file_key}")
        return True
    except Exception as e:
        print(f"Error uploading history to S3: {str(e)}")
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Upload history.txt to S3')
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

    upload_history(dry_run=args.dry_run)