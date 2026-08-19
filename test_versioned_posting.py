#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["requests>=2.25.0", "boto3>=1.26.0"]
# ///
"""Tests for the migration from /v2/ugcPosts to the versioned Content APIs.

LinkedIn's docs mark ugcPosts as replaced by the Posts API and the Assets API as replaced by the
Images API. Nothing gives /v2 a shutdown date, so this is maintenance rather than an emergency —
but the payloads differ in shape, and getting one wrong publishes nothing or publishes wrong.
These tests capture the requests the client would send, without touching the network.

Run: ./test_versioned_posting.py
"""

from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("linkedin_api", HERE / "linkedin_api.py")
linkedin_api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(linkedin_api)

TOKEN = {"access_token": "test-token", "person_urn": "urn:li:person:abc123",
         "expires_at": 4102444800}


def poster(versioned: bool = True):
    os.environ["LINKEDIN_USE_VERSIONED"] = "1" if versioned else "0"
    with mock.patch.object(linkedin_api.LinkedInPoster, "_load_token_data", return_value=TOKEN):
        return linkedin_api.LinkedInPoster()


class Captured:
    """Stands in for requests.post/put and records what would have been sent."""

    def __init__(self, status=201, body=None, headers=None):
        self.calls = []
        self.status, self.body, self.headers = status, body or {}, headers or {}

    def __call__(self, url, headers=None, json=None, data=None, timeout=None):
        self.calls.append({"url": url, "headers": headers or {}, "json": json})
        outer = self

        class Response:
            status_code = outer.status
            text = ""

            def json(self_inner):
                return outer.body

            def raise_for_status(self_inner):
                if outer.status >= 400:
                    raise RuntimeError(f"HTTP {outer.status}")

        Response.headers = outer.headers
        return Response()


class VersionedPostTests(unittest.TestCase):
    def test_an_image_post_uses_the_posts_api_with_the_documented_shape(self) -> None:
        capture = Captured(headers={"x-restli-id": "urn:li:share:999"})
        with mock.patch.object(linkedin_api.requests, "post", capture):
            result = poster().create_post("hello world", image_urn="urn:li:image:XYZ")
        self.assertEqual(result, {"id": "urn:li:share:999"},
                         "the post URN comes from x-restli-id, not the body")
        sent = capture.calls[0]
        self.assertTrue(sent["url"].endswith("/rest/posts"), sent["url"])
        body = sent["json"]
        self.assertEqual(body["author"], TOKEN["person_urn"])
        self.assertEqual(body["commentary"], "hello world")
        self.assertEqual(body["content"], {"media": {"id": "urn:li:image:XYZ"}})
        self.assertEqual(body["lifecycleState"], "PUBLISHED")
        self.assertEqual(body["distribution"]["feedDistribution"], "MAIN_FEED")
        self.assertNotIn("specificContent", body, "that is the ugcPosts shape")

    def test_every_versioned_call_carries_the_required_headers(self) -> None:
        capture = Captured(headers={"x-restli-id": "urn:li:share:1"})
        with mock.patch.object(linkedin_api.requests, "post", capture):
            poster().create_post("text only")
        headers = capture.calls[0]["headers"]
        self.assertEqual(headers["X-Restli-Protocol-Version"], "2.0.0")
        self.assertIn("LinkedIn-Version", headers)
        self.assertNotEqual(headers["LinkedIn-Version"], "202508",
                            "202508 was sunset on 2026-08-17")

    def test_image_registration_uses_the_images_api_and_keeps_the_old_return_shape(self) -> None:
        capture = Captured(status=200, body={"value": {
            "uploadUrl": "https://upload.example/1", "image": "urn:li:image:ABC"}})
        with mock.patch.object(linkedin_api.requests, "post", capture):
            info = poster()._register_upload_asset(1234)
        self.assertTrue(capture.calls[0]["url"].endswith("/rest/images?action=initializeUpload"))
        self.assertEqual(capture.calls[0]["json"],
                         {"initializeUploadRequest": {"owner": TOKEN["person_urn"]}})
        # The caller (pushLinkedInImage) is untouched by the migration only if this shape holds.
        self.assertEqual(set(info), {"upload_url", "asset_urn", "headers"})
        self.assertEqual(info["asset_urn"], "urn:li:image:ABC")


class LegacyFallbackTests(unittest.TestCase):
    """LINKEDIN_USE_VERSIONED=0 must restore the previous behaviour exactly — it is the rollback."""

    def test_the_legacy_flag_restores_ugcposts(self) -> None:
        capture = Captured(status=201, body={"id": "urn:li:ugcPost:1"})
        with mock.patch.object(linkedin_api.requests, "post", capture):
            poster(versioned=False).create_post("hello", image_urn="urn:li:digitalmediaAsset:1")
        sent = capture.calls[0]
        self.assertTrue(sent["url"].endswith("/v2/ugcPosts"), sent["url"])
        self.assertIn("specificContent", sent["json"])

    def test_the_legacy_flag_restores_the_assets_api(self) -> None:
        capture = Captured(status=200, body={"value": {
            "asset": "urn:li:digitalmediaAsset:1",
            "uploadMechanism": {
                "com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest": {
                    "uploadUrl": "https://upload.example/legacy", "headers": {}}}}})
        with mock.patch.object(linkedin_api.requests, "post", capture):
            info = poster(versioned=False)._register_upload_asset(10)
        self.assertIn("/v2/assets", capture.calls[0]["url"])
        self.assertEqual(info["asset_urn"], "urn:li:digitalmediaAsset:1")


if __name__ == "__main__":
    unittest.main(verbosity=2)
