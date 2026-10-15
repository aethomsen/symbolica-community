"""Pytest configuration and fixtures."""

import os
import asyncio

import pytest

# Initialize the kernel before test collection imports Symbolica, and let
# subprocess tests inherit the same license as the parent interpreter.
if os.environ.get("SYMBOLICA_LICENSE_KEY"):
    os.environ.setdefault("SYMBOLICA_LICENSE", os.environ["SYMBOLICA_LICENSE_KEY"])


def pytest_configure(config):
    """Make the license available before collection and in child processes."""
    license_key = os.environ.get("SYMBOLICA_LICENSE") or os.environ.get(
        "SYMBOLICA_LICENSE_KEY"
    )
    if license_key:
        # Symbolica reads SYMBOLICA_LICENSE automatically. Keep the old test
        # variable working, including in subprocesses that do not run pytest.
        os.environ["SYMBOLICA_LICENSE"] = license_key


@pytest.fixture(scope="session")
def higgs_jet_data(tmp_path_factory):
    """Explicitly prepare authenticated inputs before tests use the Higgs API."""
    from symbolica.community.hep.integration import load_higgs_jet_data

    directory = tmp_path_factory.mktemp("higgs-jet-data")
    asyncio.run(load_higgs_jet_data(form_factors=True, cache_dir=directory))
    return directory
