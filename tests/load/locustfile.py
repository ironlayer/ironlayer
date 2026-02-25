"""IronLayer load testing with Locust.

Simulates realistic traffic patterns: concurrent signups, logins, plan
generation, model queries, and heavy read workloads.

Usage:
    # Quick smoke test (10 users, 1 minute)
    locust -f tests/load/locustfile.py --headless -u 10 -r 2 -t 60s \
        --host http://localhost:8000/api/v1

    # Full load test (50 users, 200 req/s target, 10 minutes)
    locust -f tests/load/locustfile.py --headless -u 50 -r 5 -t 600s \
        --host http://localhost:8000/api/v1

    # With web UI
    locust -f tests/load/locustfile.py --host http://localhost:8000/api/v1
"""

from __future__ import annotations

import json
import os
import random
import string
import uuid
from typing import Any

from locust import HttpUser, between, events, tag, task

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Pre-created admin credentials for authenticated workloads.
# Set via env vars or fall back to defaults for local dev.
ADMIN_EMAIL = os.environ.get("LOAD_TEST_ADMIN_EMAIL", "loadtest@ironlayer.test")
ADMIN_PASSWORD = os.environ.get("LOAD_TEST_ADMIN_PASSWORD", "loadtest123!")
API_PREFIX = "/api/v1"


def _random_email() -> str:
    """Generate a unique random email for signup tests."""
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=10))
    return f"loadtest-{suffix}@ironlayer.test"


# ---------------------------------------------------------------------------
# User behaviours
# ---------------------------------------------------------------------------


class AuthenticatedUser(HttpUser):
    """Simulates an authenticated user performing typical platform operations.

    On start, logs in (or signs up) and stores the access token.
    Tasks simulate browsing the dashboard, viewing models, generating plans,
    and checking run status.
    """

    wait_time = between(0.5, 2.0)
    weight = 8  # 80% of users are authenticated

    _token: str = ""
    _user_id: str = ""
    _tenant_id: str = ""

    def on_start(self) -> None:
        """Log in and store the access token."""
        resp = self.client.post(
            f"{API_PREFIX}/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            name="/auth/login",
        )
        if resp.status_code == 200:
            data = resp.json()
            self._token = data["access_token"]
            self._user_id = data["user"]["id"]
            self._tenant_id = data["tenant_id"]
        elif resp.status_code in (401, 404):
            # Admin doesn't exist yet — sign up.
            resp = self.client.post(
                f"{API_PREFIX}/auth/signup",
                json={
                    "email": ADMIN_EMAIL,
                    "password": ADMIN_PASSWORD,
                    "display_name": "Load Test Admin",
                },
                name="/auth/signup",
            )
            if resp.status_code in (200, 201):
                data = resp.json()
                self._token = data["access_token"]
                self._user_id = data["user"]["id"]
                self._tenant_id = data["tenant_id"]

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

    @task(10)
    @tag("read")
    def list_plans(self) -> None:
        """GET /plans — most common dashboard operation."""
        self.client.get(
            f"{API_PREFIX}/plans?limit=20&offset=0",
            headers=self._headers(),
            name="/plans",
        )

    @task(8)
    @tag("read")
    def list_models(self) -> None:
        """GET /models — model catalog browsing."""
        self.client.get(
            f"{API_PREFIX}/models",
            headers=self._headers(),
            name="/models",
        )

    @task(5)
    @tag("read")
    def list_runs(self) -> None:
        """GET /runs — run history view."""
        self.client.get(
            f"{API_PREFIX}/runs?limit=20",
            headers=self._headers(),
            name="/runs",
        )

    @task(3)
    @tag("read")
    def get_usage(self) -> None:
        """GET /usage/summary — usage dashboard."""
        self.client.get(
            f"{API_PREFIX}/usage/summary?days=30",
            headers=self._headers(),
            name="/usage/summary",
        )

    @task(3)
    @tag("read")
    def get_subscription(self) -> None:
        """GET /billing/subscription — billing check."""
        self.client.get(
            f"{API_PREFIX}/billing/subscription",
            headers=self._headers(),
            name="/billing/subscription",
        )

    @task(2)
    @tag("read")
    def get_environments(self) -> None:
        """GET /environments — environment list."""
        self.client.get(
            f"{API_PREFIX}/environments",
            headers=self._headers(),
            name="/environments",
        )

    @task(2)
    @tag("read")
    def get_me(self) -> None:
        """GET /auth/me — profile fetch."""
        self.client.get(
            f"{API_PREFIX}/auth/me",
            headers=self._headers(),
            name="/auth/me",
        )

    @task(1)
    @tag("write")
    def refresh_token(self) -> None:
        """POST /auth/refresh — token rotation."""
        # This is a simplified version; real refresh uses the refresh_token.
        self.client.post(
            f"{API_PREFIX}/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            headers={"Content-Type": "application/json"},
            name="/auth/login (refresh)",
        )


class SignupUser(HttpUser):
    """Simulates new user signups — bursts of concurrent registrations."""

    wait_time = between(2.0, 5.0)
    weight = 2  # 20% of load is signup traffic

    @task
    @tag("write", "signup")
    def signup(self) -> None:
        """POST /auth/signup — new user registration."""
        email = _random_email()
        resp = self.client.post(
            f"{API_PREFIX}/auth/signup",
            json={
                "email": email,
                "password": "loadtest123!",
                "display_name": f"Load User {email[:8]}",
            },
            name="/auth/signup",
        )
        if resp.status_code in (200, 201):
            data = resp.json()
            # Immediately hit /auth/me to simulate post-signup flow.
            self.client.get(
                f"{API_PREFIX}/auth/me",
                headers={
                    "Authorization": f"Bearer {data['access_token']}",
                    "Content-Type": "application/json",
                },
                name="/auth/me (post-signup)",
            )


# ---------------------------------------------------------------------------
# Event hooks
# ---------------------------------------------------------------------------


@events.test_start.add_listener
def on_test_start(environment: Any, **kwargs: Any) -> None:
    """Log test parameters at startup."""
    print(
        f"\n{'='*60}\n"
        f"IronLayer Load Test Starting\n"
        f"  Host: {environment.host}\n"
        f"  Admin email: {ADMIN_EMAIL}\n"
        f"{'='*60}\n"
    )


@events.test_stop.add_listener
def on_test_stop(environment: Any, **kwargs: Any) -> None:
    """Print summary after test completes."""
    stats = environment.runner.stats
    print(
        f"\n{'='*60}\n"
        f"IronLayer Load Test Complete\n"
        f"  Total requests: {stats.total.num_requests}\n"
        f"  Failures: {stats.total.num_failures}\n"
        f"  Avg response time: {stats.total.avg_response_time:.0f}ms\n"
        f"  95th percentile: {stats.total.get_response_time_percentile(0.95):.0f}ms\n"
        f"  Requests/s: {stats.total.current_rps:.1f}\n"
        f"{'='*60}\n"
    )
