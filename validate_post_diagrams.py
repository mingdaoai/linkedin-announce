#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "boto3>=1.26.0",
#     "Pillow>=10.0.0",
# ]
# ///
"""
Validate LinkedIn post diagram images stored in S3.

For each post in linkedin-posts/list.txt, downloads the image (architecture.png),
checks aspect ratio between 4:3 and 3:4, width <= height, and height <= 800.
Outputs validation results in bullet list format.
"""

import sys
import argparse
import io
import logging
import math
from pathlib import Path

import boto3
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
try:
    import videoUtil
except ImportError as e:
    logging.error(f"Cannot import videoUtil: {e}")
    sys.exit(1)

def setup_logging(verbose=False):
    script_dir = Path(__file__).parent.resolve()
    log_file = script_dir / 'validate_post_diagrams.log'
    
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
        handlers=[
            logging.FileHandler(log_file, delay=False),
            logging.StreamHandler(sys.stdout)
        ]
    )

logger = logging.getLogger(__name__)

BUCKET_NAME = 'dscub'
LINKEDIN_POSTS_LIST_KEY = 'linkedin-posts/list.txt'

def read_linkedin_post_list():
    """Read LinkedIn post list from S3 using videoUtil."""
    try:
        post_lines = videoUtil.read_linkedin_post_list()
        logger.info(f"Read {len(post_lines)} post lines from S3")
        return post_lines
    except Exception as e:
        logger.error(f"Failed to read LinkedIn post list: {e}")
        return []

def parse_post_line(line):
    """Parse a line from the LinkedIn post list.
    
    Expected format: creation_date|video_id|title|s3_path
    where s3_path ends with '/post.txt'.
    
    Returns dict with keys: creation_date, video_id, title, s3_path, s3_base.
    """
    parts = line.strip().split('|')
    if len(parts) != 4:
        logger.warning(f"Skipping malformed line: {line}")
        return None
    
    creation_date, video_id, title, s3_path = parts
    # Normalize s3_base: strip trailing '/post.txt' if present
    if s3_path.endswith('/post.txt'):
        s3_base = s3_path[:-9]
    else:
        s3_base = s3_path
        logger.warning(f"s3_path does not end with /post.txt: {s3_path}")
    
    return {
        'creation_date': creation_date,
        'video_id': video_id,
        'title': title,
        's3_path': s3_path,
        's3_base': s3_base,
    }

def download_image_bytes(s3_client, s3_key):
    """Download image from S3 and return bytes."""
    try:
        response = s3_client.get_object(Bucket=BUCKET_NAME, Key=s3_key)
        image_bytes = response['Body'].read()
        logger.debug(f"Downloaded {len(image_bytes)} bytes from {s3_key}")
        return image_bytes
    except Exception as e:
        logger.error(f"Failed to download {s3_key}: {e}")
        raise

def get_image_dimensions(image_bytes):
    """Get (width, height) from image bytes using PIL."""
    try:
        image = Image.open(io.BytesIO(image_bytes))
        width, height = image.size
        logger.debug(f"Image dimensions: {width}x{height}")
        return width, height
    except Exception as e:
        logger.error(f"Failed to parse image: {e}")
        raise

def evaluate_image(width, height):
    """Evaluate image against criteria.
    
    Returns dict with booleans:
    - aspect_ratio_ok: aspect ratio between 4:3 and 3:4 inclusive
    - portrait_ok: width <= height
    - height_ok: height <= 800
    """
    if height == 0:
        return {'aspect_ratio_ok': False, 'portrait_ok': False, 'height_ok': False}
    
    aspect_ratio = width / height
    aspect_ratio_ok = 0.75 <= aspect_ratio <= 1.3333333333333333
    portrait_ok = width <= height
    height_ok = height <= 800
    
    return {
        'aspect_ratio_ok': aspect_ratio_ok,
        'portrait_ok': portrait_ok,
        'height_ok': height_ok,
    }

def download_post_text(s3_client, s3_key):
    """Download post.txt and return its content."""
    try:
        response = s3_client.get_object(Bucket=BUCKET_NAME, Key=s3_key)
        text = response['Body'].read().decode('utf-8')
        return text.strip()
    except Exception as e:
        logger.error(f"Failed to download post text {s3_key}: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description='Validate LinkedIn post diagram images in S3')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable debug logging')
    parser.add_argument('--limit', type=int, default=0, help='Limit number of posts to process (0 for all)')
    parser.add_argument('--skip-text', action='store_true', help='Skip downloading post.txt')
    args = parser.parse_args()
    
    setup_logging(verbose=args.verbose)
    logger.info("Starting validation of LinkedIn post diagrams")
    s3_client = boto3.client('s3')
    
    post_lines = read_linkedin_post_list()
    if not post_lines:
        logger.error("No posts found. Exiting.")
        return
    
    if args.limit > 0:
        post_lines = post_lines[:args.limit]
        logger.info(f"Limited to {args.limit} posts")
    
    results = []
    for line in post_lines:
        if not line.strip():
            continue
        logger.info(f"Processing: {line.strip()}")
        post = parse_post_line(line)
        if not post:
            continue
        
        image_key = f"{post['s3_base']}/architecture.png"
        logger.info(f"  Image key: {image_key}")
        
        try:
            image_bytes = download_image_bytes(s3_client, image_key)
            width, height = get_image_dimensions(image_bytes)
            eval_result = evaluate_image(width, height)
        except Exception as e:
            logger.warning(f"  Skipping due to error: {e}")
            continue
        
        post_text = None
        if not args.skip_text:
            post_text = download_post_text(s3_client, post['s3_path'])
        else:
            logger.debug("  Skipping post text download")
        
        result = {
            'post': post,
            'width': width,
            'height': height,
            'aspect_ratio': width / height if width and height else None,
            'post_text': post_text,
            'image_key': image_key,
            **({'aspect_ratio_ok': eval_result['aspect_ratio_ok'],
                'portrait_ok': eval_result['portrait_ok'],
                'height_ok': eval_result['height_ok']} if eval_result else {})
        }
        results.append(result)
        
        if width and height and eval_result:
            logger.info(f"  {width}x{height}, aspect {width/height:.3f}, "
                        f"aspect_ok={eval_result['aspect_ratio_ok']}, "
                        f"portrait_ok={eval_result['portrait_ok']}, "
                        f"height_ok={eval_result['height_ok']}")
        elif width and height:
            logger.warning(f"  {width}x{height}, aspect {width/height:.3f}, missing eval_result")
        else:
            logger.warning("  No dimensions available")
    
    logger.info("\n=== VALIDATION RESULTS ===")
    for r in results:
        preview = (r['post_text'][:100].replace('\n', ' ') if r['post_text'] else '')
        width = r['width']
        height = r['height']
        aspect_ratio = r['aspect_ratio']
        aspect_ok = r.get('aspect_ratio_ok', False)
        portrait_ok = r.get('portrait_ok', False)
        height_ok = r.get('height_ok', False)
        
        print(f"* {r['post']['creation_date']} {r['post']['video_id']} - {r['post']['title']}")
        print(f"  • Image: {r['image_key']}")
        if width is not None and height is not None:
            print(f"  • Dimensions: {width}x{height} (aspect ratio: {aspect_ratio:.3f})")
        else:
            print(f"  • Dimensions: N/A")
        print(f"  • Validation:")
        print(f"    • Aspect ratio (4:3 to 3:4): {'✓ OK' if aspect_ok else '✗ FAIL'}")
        print(f"    • Portrait orientation (width <= height): {'✓ OK' if portrait_ok else '✗ FAIL'}")
        print(f"    • Height <= 800px: {'✓ OK' if height_ok else '✗ FAIL'}")
        if preview:
            print(f"  • Post preview: {preview}")
        print()
    
    logger.info(f"Processed {len(results)} posts")

if __name__ == "__main__":
    main()