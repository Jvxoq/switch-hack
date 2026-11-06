from __future__ import annotations

from pathlib import Path

import pytest

from tests.fakes.clock import FakeClock
from tests.fakes.containment import FakeContainment
from tests.fakes.langfuse import FakeLangfuse
from tests.fakes.switch import FakeSwitch
from tripwire.contracts.config import TripwireConfig, load_config

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def cfg() -> TripwireConfig:
    return load_config(REPO_ROOT / "tripwire.yaml")


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def langfuse() -> FakeLangfuse:
    return FakeLangfuse()


@pytest.fixture
def switch() -> FakeSwitch:
    return FakeSwitch()


@pytest.fixture
def containment(clock: FakeClock, cfg: TripwireConfig) -> FakeContainment:
    return FakeContainment(clock, cfg)
