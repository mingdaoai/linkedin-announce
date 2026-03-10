#!/usr/bin/env uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "boto3>=1.26.0",
#     "botocore>=1.29.0",
# ]
# ///

# creates a bucket designmake and make it accessible
# through public urls such as https://designmake.s3.amazonaws.com/mingdaoAIYoutubePortrait.mp4

import boto3
import sys
from botocore.exceptions import ClientError

def debug_print(message):
    print(f"DEBUG: {message}", file=sys.stderr)

def create_public_bucket(bucket_name='designmake'):
    """Create an S3 bucket that allows public read access"""
    
    # Create S3 client
    s3_client = boto3.client('s3')
    
    try:
        # Create bucket with public read access
        location = {'LocationConstraint': 'us-west-2'}
        s3_client.create_bucket(
            Bucket=bucket_name,
            CreateBucketConfiguration=location
        )
        
        debug_print(f"Created bucket: {bucket_name}")
        
        # Set bucket policy to allow public read access
        bucket_policy = {
            'Version': '2012-10-17',
            'Statement': [{
                'Sid': 'PublicReadGetObject',
                'Effect': 'Allow',
                'Principal': '*',
                'Action': ['s3:GetObject'],
                'Resource': [f'arn:aws:s3:::{bucket_name}/*']
            }]
        }
        
        # Convert policy to JSON string
        bucket_policy = str(bucket_policy).replace("'", '"')
        
        # Set the bucket policy
        s3_client.put_bucket_policy(
            Bucket=bucket_name,
            Policy=bucket_policy
        )
        
        debug_print("Set bucket policy for public read access")
        
        # Enable website hosting
        website_configuration = {
            'ErrorDocument': {'Key': 'error.html'},
            'IndexDocument': {'Key': 'index.html'}
        }
        
        s3_client.put_bucket_website(
            Bucket=bucket_name,
            WebsiteConfiguration=website_configuration
        )
        
        debug_print("Enabled website hosting")
        
        return True
        
    except ClientError as e:
        debug_print(f"Error: {e}")
        return False

if __name__ == "__main__":
    success = create_public_bucket()
    if success:
        print("Successfully created public S3 bucket")
    else:
        print("Failed to create S3 bucket")
        sys.exit(1)
