#!/usr/bin/env uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["boto3>=1.26.0"]
# ///
"""One-off: rewrite `videos/history.txt` linkedin-image URLs from the legacy
`linkedin-posts/image_{hash}_{ts}/post.txt` paths to the new stable
`linkedin-posts/image_{owner}_{repo}/post.txt` scheme.

Why: linkedin_poster.py dedupes by the s3_path stored in history. After
linkedin_s3_poster.py switched to repo-based post IDs, every new
`linkedin-posts/list.txt` URL no longer matches the old history URLs, so a
repo that was posted yesterday looks brand-new to the poster. Rewriting
history preserves the 5-day freshness window.

Safe to re-run: paths already in the new format are left alone. Any
linkedin-image entry whose title doesn't map to a known repo is left alone
with a warning (we don't invent mappings).
"""
import argparse
import re
import sys

import boto3

s3 = boto3.client("s3")
BUCKET = "dscub"
HISTORY_KEY = "videos/history.txt"

# (keyword_in_title_lowercase, new_post_id). More specific entries first.
TITLE_TO_NEW_ID = [
    ("everything claude code", "image_affaan-m_everything-claude-code"),
    ("learn-claude-code",     "image_shareai-lab_learn-claude-code"),
    ("learn claude code",     "image_shareai-lab_learn-claude-code"),
    ("paperclip",             "image_paperclipai_paperclip"),
    ("deerflow",              "image_bytedance_deer-flow"),
    ("deer-flow",             "image_bytedance_deer-flow"),
    ("deer flow",             "image_bytedance_deer-flow"),
    ("hermes",                "image_nousresearch_hermes-agent"),
    ("nemoclaw",              "image_nvidia_nemoclaw"),
    ("personaplex",           "image_nvidia_personaplex"),
    ("garry",                 "image_garrytan_gstack"),
    ("gstack",                "image_garrytan_gstack"),
    ("google ai edge",        "image_google-ai-edge_gallery"),
    ("ai edge gallery",       "image_google-ai-edge_gallery"),
    ("litert-lm",             "image_google-ai-edge_litert-lm"),
    ("litert",                "image_google-ai-edge_litert-lm"),
    ("generative-ai",         "image_googlecloudplatform_generative-ai"),
    ("google cloud",          "image_googlecloudplatform_generative-ai"),
    ("google workspace",      "image_googleworkspace_cli"),
    ("gws",                   "image_googleworkspace_cli"),
    ("last30days",            "image_mvanhorn_last30days-skill"),
    ("last 30 days",          "image_mvanhorn_last30days-skill"),
    ("lightpanda",            "image_lightpanda-io_browser"),
    ("multica",               "image_multica-ai_multica"),
    ("goose",                 "image_aaif-goose_goose"),
    ("superpowers",           "image_obra_superpowers"),
    ("oh-my-codex",           "image_yeachan-heo_oh-my-codex"),
    ("oh my codex",           "image_yeachan-heo_oh-my-codex"),
    ("agency-agents",         "image_msitarzewski_agency-agents"),
    ("agency agents",         "image_msitarzewski_agency-agents"),
    ("archon",                "image_coleam00_archon"),
    ("context-hub",           "image_andrewyng_context-hub"),
    ("context hub",           "image_andrewyng_context-hub"),
    ("camofox",               "image_jo-inc_camofox-browser"),
    ("markitdown",            "image_microsoft_markitdown"),
    ("deeptutor",             "image_hkuds_deeptutor"),
    ("seomachine",            "image_thecraighewitt_seomachine"),
]

OLD_PATH_RE = re.compile(r"^linkedin-posts/image_[0-9a-f]{16}_\d+/post\.txt$")


def classify(title: str):
    lower = title.lower()
    for keyword, new_id in TITLE_TO_NEW_ID:
        if keyword in lower:
            return new_id
    return None


def migrate(dry_run: bool):
    body = s3.get_object(Bucket=BUCKET, Key=HISTORY_KEY)["Body"].read().decode("utf-8")
    changed = 0
    skipped = 0
    untouched_new = 0
    new_lines = []

    for line in body.splitlines():
        parts = line.split("|")
        if len(parts) != 4 or parts[1] != "linkedin-image":
            new_lines.append(line)
            continue
        ts, kind, title, path = parts
        if not OLD_PATH_RE.match(path):
            untouched_new += 1
            new_lines.append(line)
            continue

        new_id = classify(title)
        if new_id is None:
            print(f"  [skip: no mapping] {title[:60]!r}  ({path})")
            skipped += 1
            new_lines.append(line)
            continue

        new_path = f"linkedin-posts/{new_id}/post.txt"
        print(f"  {ts}: {path}")
        print(f"           ->  {new_path}  ({title[:50]!r})")
        new_lines.append(f"{ts}|{kind}|{title}|{new_path}")
        changed += 1

    print()
    print(f"rewrote:     {changed}")
    print(f"already new: {untouched_new}")
    print(f"unmapped:    {skipped}")

    new_body = "\n".join(new_lines)

    if dry_run:
        print("\n[DRY RUN] Not uploading.")
        return 0

    # Keep a timestamped backup key alongside the history in S3.
    import datetime
    backup_key = f"videos/history.txt.bak.{datetime.datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}"
    s3.put_object(
        Bucket=BUCKET, Key=backup_key,
        Body=body.encode("utf-8"),
        ContentType="text/plain; charset=utf-8",
    )
    print(f"\nBackup saved to s3://{BUCKET}/{backup_key}")

    s3.put_object(
        Bucket=BUCKET, Key=HISTORY_KEY,
        Body=new_body.encode("utf-8"),
        ContentType="text/plain; charset=utf-8",
    )
    print(f"Uploaded updated history to s3://{BUCKET}/{HISTORY_KEY}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true",
                    help="Preview rewrites without uploading to S3.")
    args = ap.parse_args()
    sys.exit(migrate(args.dry_run))
