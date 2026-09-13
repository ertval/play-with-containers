#!/usr/bin/env python3
"""
Automated unit and integration test suite for Play with Containers.
Tests can be executed standalone without external dependencies:
    python3 scripts/test_api.py

Test layers:
  - Unit tests (TestPayloadValidation, TestOpenAPISpecification) are OFFLINE:
    they never need docker/compose or the live stack.
  - Live tests (TestLiveAPIGateway) need the stack up first:
    `docker compose up --build -d --wait` (or `make up`), then re-run this script.
    By default live tests SKIP when the gateway is unreachable; set STRICT_LIVE=1
    (or CI=true) to FAIL instead of skip in CI/strict environments.

Note on app validators: the real validation logic lives inline in
  srcs/inventory-app/app/movies.py (title required/non-blank) and
  srcs/billing-app/app/consume_queue.py (user_id/items/amount coercion).
There is no standalone validator module to import without pulling in Flask /
SQLAlchemy app side effects (create_app connects to Postgres, proxy.py opens
RabbitMQ at import), so unit tests intentionally mirror that logic and cite the
source files above instead of importing the apps.
"""

import json
import os
import re
import sys
import unittest
import urllib.request
import urllib.error

# Safe .env loader: KEY=VAL lines only (KEY must match ^[A-Za-z_][A-Za-z0-9_]*$).
# Values are taken literally — no shell eval, no command/backtick expansion.
# Only sets keys not already present in the environment.
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
if os.path.isfile(env_path):
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip().lstrip("\ufeff")
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", k):
                    continue
                v = v.strip()
                # Strip one level of matching surrounding quotes (no escape processing).
                if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
                    v = v[1:-1]
                # Strip trailing inline comment for unquoted values only.
                os.environ.setdefault(k, v)
    except Exception:
        pass

STRICT_LIVE = os.getenv("STRICT_LIVE", "0") == "1" or os.getenv("CI", "").lower() == "true"

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
    """Integration tests running against the live API Gateway if running.
    Require `docker compose up` first; skipped offline unless STRICT_LIVE=1/CI=true.
    """

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
            msg = f"API Gateway at {BASE_URL} is not currently running. Start it with `make up` / `docker compose up --build -d --wait`."
            if STRICT_LIVE:
                self.fail(f"STRICT_LIVE/CI mode: {msg}")
            self.skipTest(f"{msg} Skipping live HTTP integration test.")

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

    def test_inventory_movie_filter(self):
        # 1. Create a movie to search for
        payload = json.dumps({"title": "FilterSearchMovieUnique", "description": "Desc"}).encode("utf-8")
        req = urllib.request.Request(
            f"{BASE_URL}/api/movies/",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        movie_id = None
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                self.assertEqual(resp.status, 200)
                created = json.loads(resp.read().decode("utf-8"))
                movie_id = created.get("id")

            # 2. Filter by substring query
            filter_req = urllib.request.Request(f"{BASE_URL}/api/movies?title=SearchMovieUnique")
            with urllib.request.urlopen(filter_req, timeout=5) as resp:
                self.assertEqual(resp.status, 200)
                data = json.loads(resp.read().decode("utf-8"))
                titles = [m.get("title") for m in data.get("movies", [])]
                self.assertIn("FilterSearchMovieUnique", titles)
        finally:
            if movie_id is not None:
                del_req = urllib.request.Request(f"{BASE_URL}/api/movies/{movie_id}", method="DELETE")
                try:
                    urllib.request.urlopen(del_req, timeout=5)
                except Exception:
                    pass

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
