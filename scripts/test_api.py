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

Note on app validators: the validation rules live in dependency-free modules that
  these tests import for real, so a passing run means the shipped code agrees
  with the documented contract:
    srcs/inventory-app/app/validation.py  (title required / non-blank, description)
    srcs/billing-app/app/validation.py    (user_id / items / amount coercion)
The Flask entrypoints that call them are exercised by the live HTTP tests.
"""

import json
import os
import re
import sys
import unittest
import urllib.request
import urllib.error

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The validators are deliberately dependency-free, so they can be imported on the
# host without Flask/SQLAlchemy/pika installed. Load them by path rather than by
# package name to avoid importing either service's __init__ (which opens a
# database connection).
def _load_module(name: str, relative_path: str):
    import importlib.util
    path = os.path.join(REPO_ROOT, relative_path)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


movie_validation = _load_module("inventory_movie_validation", os.path.join("srcs", "inventory-app", "app", "validation.py"))
order_validation = _load_module("billing_order_validation", os.path.join("srcs", "billing-app", "app", "validation.py"))
validate_movie_payload = movie_validation.validate_movie_payload
coerce_order_payload = order_validation.coerce_order_payload
InvalidOrderError = order_validation.InvalidOrderError

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
    """Unit tests importing the real validators the services actually call."""

    def test_movie_payload_validation(self):
        """Verify title validation rules for inventory movie creation."""
        title, description = validate_movie_payload(
            {"title": "A new movie", "description": "Very short description"}
        )
        self.assertEqual(title, "A new movie")
        self.assertEqual(description, "Very short description")

        # Title is trimmed rather than stored with surrounding whitespace.
        self.assertEqual(validate_movie_payload({"title": "  Padded  "})[0], "Padded")

        # Missing title
        with self.assertRaises(ValueError):
            validate_movie_payload({"description": "missing title"})

        # Blank / whitespace-only title
        with self.assertRaises(ValueError):
            validate_movie_payload({"title": "   "})

        # A missing description becomes an empty string, not "None".
        self.assertEqual(validate_movie_payload({"title": "T"})[1], "")

        # An explicit JSON null description must not be stringified to "None".
        self.assertEqual(validate_movie_payload({"title": "T", "description": None})[1], "")

        # Non-object bodies are rejected rather than raising TypeError/500.
        for bad_body in ("a string", 123, ["a", "title"], None):
            with self.assertRaises(ValueError):
                validate_movie_payload(bad_body)

    def test_movie_update_allows_partial_body(self):
        """PUT semantics: description may be updated without a title."""
        title, description = validate_movie_payload({"description": "only desc"}, require_title=False)
        self.assertEqual(description, "only desc")
        self.assertEqual(title, "")

        # But an explicitly blank title is still rejected.
        with self.assertRaises(ValueError):
            validate_movie_payload({"title": ""}, require_title=False)

    def test_billing_type_coercion(self):
        """Verify explicit coercion of string-formatted numbers from audit payloads."""
        user_id, number_of_items, total_amount = coerce_order_payload({
            "user_id": "20",
            "number_of_items": "99",
            "total_amount": "250"
        })

        self.assertEqual(user_id, "20")
        self.assertEqual(number_of_items, 99)
        self.assertEqual(total_amount, 250.0)
        self.assertIsInstance(number_of_items, int)
        self.assertIsInstance(total_amount, float)

    def test_billing_coercion_invalid_values(self):
        """Verify that malformed payloads raise InvalidOrderError, not crash the worker."""
        invalid_payloads = [
            {"user_id": "20", "number_of_items": "not-a-number", "total_amount": "invalid"},
            {"user_id": "20", "number_of_items": None, "total_amount": "250"},
            {"user_id": "20", "number_of_items": "99", "total_amount": "abc"},
            {"user_id": "   ", "number_of_items": "99", "total_amount": "250"},
            {"user_id": "", "number_of_items": "99", "total_amount": "250"},
            {"number_of_items": "99", "total_amount": "250"},
        ]
        for payload in invalid_payloads:
            with self.assertRaises(InvalidOrderError):
                coerce_order_payload(payload)

        # Non-object bodies (a list, a scalar) are rejected too.
        for bad_body in ("not json object", 42, ["a"]):
            with self.assertRaises(InvalidOrderError):
                coerce_order_payload(bad_body)


class TestOpenAPISpecification(unittest.TestCase):
    """Verify presence and required paths in openapi.yaml."""

    def test_openapi_file_exists_and_declares_paths(self):
        openapi_path = os.path.join(REPO_ROOT, "openapi.yaml")
        self.assertTrue(os.path.isfile(openapi_path), f"openapi.yaml not found at {openapi_path}")

        with open(openapi_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Check essential required paths and endpoints
        self.assertIn("/health:", content)
        self.assertIn("/api/movies:", content)
        self.assertIn("/api/movies/{id}:", content)
        self.assertIn("/api/billing:", content)
        self.assertIn("openapi: 3.0", content)

    def test_served_spec_matches_repo_copy(self):
        """The gateway serves srcs/api-gateway-app/openapi.yaml; keep copies identical.

        The Dockerfile copies the srcs/ copy into the image while this suite reads
        the repository-root copy. If they drift, the suite would validate a
        specification that no evaluator ever sees.
        """
        root_spec = os.path.join(REPO_ROOT, "openapi.yaml")
        served_spec = os.path.join(REPO_ROOT, "srcs", "api-gateway-app", "openapi.yaml")
        self.assertTrue(os.path.isfile(served_spec), f"gateway spec not found at {served_spec}")

        with open(root_spec, "r", encoding="utf-8") as f:
            root_content = f.read()
        with open(served_spec, "r", encoding="utf-8") as f:
            served_content = f.read()

        self.assertEqual(
            root_content,
            served_content,
            "openapi.yaml and srcs/api-gateway-app/openapi.yaml have drifted apart",
        )


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
