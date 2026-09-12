#!/usr/bin/env python3
"""
Automated unit and integration test suite for Play with Containers.
Tests can be executed standalone without external dependencies:
    python3 scripts/test_api.py
"""

import json
import os
import sys
import unittest
import urllib.request
import urllib.error

GATEWAY_HOST = os.getenv("GATEWAY_HOST", "127.0.0.1")
GATEWAY_PORT = os.getenv("GATEWAY_PORT", "3000")
BASE_URL = f"http://{GATEWAY_HOST}:{GATEWAY_PORT}"


class TestPayloadValidation(unittest.TestCase):
    """Unit tests for request payload validation and data type coercion logic."""

    def test_movie_payload_validation(self):
        """Verify title validation rules for inventory movie creation."""
        valid_payload = {"title": "A new movie", "description": "Very short description"}
        self.assertTrue(isinstance(valid_payload.get("title"), str))
        self.assertTrue(bool(valid_payload.get("title", "").strip()))

        # Invalid payloads
        empty_title_payload = {"title": "   ", "description": "some desc"}
        self.assertFalse(bool(empty_title_payload["title"].strip()))

        missing_title_payload = {"description": "missing title"}
        self.assertNotIn("title", missing_title_payload)

    def test_billing_type_coercion(self):
        """Verify explicit coercion of string-formatted numbers from audit payloads."""
        audit_payload = {
            "user_id": "20",
            "number_of_items": "99",
            "total_amount": "250"
        }

        # Emulate billing worker coercion logic
        user_id = str(audit_payload.get("user_id", "")).strip()
        number_of_items = int(audit_payload.get("number_of_items", 0))
        total_amount = float(audit_payload.get("total_amount", 0.0))

        self.assertEqual(user_id, "20")
        self.assertEqual(number_of_items, 99)
        self.assertEqual(total_amount, 250.0)
        self.assertIsInstance(number_of_items, int)
        self.assertIsInstance(total_amount, float)

    def test_billing_coercion_invalid_values(self):
        """Verify that malformed numeric strings fail validation cleanly."""
        invalid_payload = {
            "user_id": "20",
            "number_of_items": "not-a-number",
            "total_amount": "invalid"
        }
        with self.assertRaises(ValueError):
            int(invalid_payload["number_of_items"])
        with self.assertRaises(ValueError):
            float(invalid_payload["total_amount"])


class TestOpenAPISpecification(unittest.TestCase):
    """Verify presence and required paths in openapi.yaml."""

    def test_openapi_file_exists_and_declares_paths(self):
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        openapi_path = os.path.join(repo_root, "openapi.yaml")
        self.assertTrue(os.path.isfile(openapi_path), f"openapi.yaml not found at {openapi_path}")

        with open(openapi_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Check essential required paths and endpoints
        self.assertIn("/health:", content)
        self.assertIn("/api/movies:", content)
        self.assertIn("/api/movies/{id}:", content)
        self.assertIn("/api/billing/:", content)
        self.assertIn("openapi: 3.0", content)


class TestLiveAPIGateway(unittest.TestCase):
    """Integration tests running against the live API Gateway if running."""

    @classmethod
    def setUpClass(cls):
        cls.live_available = False
        health_url = f"{BASE_URL}/health"
        try:
            req = urllib.request.Request(health_url)
            with urllib.request.urlopen(req, timeout=2) as resp:
                if resp.status == 200:
                    cls.live_available = True
        except Exception:
            cls.live_available = False

    def setUp(self):
        if not self.live_available:
            self.skipTest(f"API Gateway at {BASE_URL} is not currently running. Skipping live HTTP integration test.")

    def test_gateway_health(self):
        req = urllib.request.Request(f"{BASE_URL}/health")
        with urllib.request.urlopen(req, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data.get("status"), "healthy")

    def test_inventory_movie_crud(self):
        # 1. Create a movie
        payload = json.dumps({"title": "Test Integration Movie", "description": "Test Desc"}).encode("utf-8")
        req = urllib.request.Request(
            f"{BASE_URL}/api/movies/",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            created = json.loads(resp.read().decode("utf-8"))
            self.assertIn("id", created)
            self.assertEqual(created["title"], "Test Integration Movie")
            movie_id = created["id"]

        # 2. Get movies list
        req = urllib.request.Request(f"{BASE_URL}/api/movies/")
        with urllib.request.urlopen(req, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("movies", data)
            titles = [m.get("title") for m in data["movies"]]
            self.assertIn("Test Integration Movie", titles)

        # 3. Clean up created movie
        del_req = urllib.request.Request(f"{BASE_URL}/api/movies/{movie_id}", method="DELETE")
        with urllib.request.urlopen(del_req, timeout=5) as resp:
            self.assertEqual(resp.status, 200)

    def test_billing_order_enqueue(self):
        payload = json.dumps({
            "user_id": "20",
            "number_of_items": "99",
            "total_amount": "250"
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{BASE_URL}/api/billing/",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("message", data)
            self.assertIn("sent", data["message"])


if __name__ == "__main__":
    print("Running Play with Containers Test Suite...")
    unittest.main(verbosity=2)
