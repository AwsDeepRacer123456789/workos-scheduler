"""
Small PostgreSQL helpers for the KernelQ control plane.

We use psycopg (version 3) to talk to Postgres. The connection string matches
the default credentials from local Docker Compose unless you override it with
the DATABASE_URL environment variable.
"""

from __future__ import annotations

import os

import psycopg

# Matches docker-compose.yml: user kernelq, password kernelq_dev_password,
# database kernelq, port 5432 on your machine.
DEFAULT_DATABASE_URL = (
    "postgresql://kernelq:kernelq_dev_password@localhost:5432/kernelq"
)


def get_database_url() -> str:
    """
    Return the Postgres connection URL.

    If DATABASE_URL is set in the environment (common in production), use it.
    Otherwise use DEFAULT_DATABASE_URL for local development.
    """
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)


def connect():
    """
    Open a new connection to PostgreSQL.

    Callers should close the connection when done, or use a context manager:

        with connect() as conn:
            ...
    """
    return psycopg.connect(get_database_url())
