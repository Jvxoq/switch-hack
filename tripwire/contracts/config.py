"""Load and validate `tripwire.yaml`. Secrets are referenced by env-var name, never by value."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class ConfigError(Exception):
    """Raised with a human-readable message when the config is missing, unparsable or invalid."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoopRuleConfig(_Strict):
    max_repeats: int = Field(5, ge=1)
    max_observations: int = Field(25, ge=1)


class SilentErrorRuleConfig(_Strict):
    count: int = Field(3, ge=1)
    window_minutes: float = Field(5, gt=0)
    patterns: list[str] = Field(default_factory=lambda: ["error", "not found"])


class CostSpikeRuleConfig(_Strict):
    median_multiplier: float = Field(5, gt=0)
    per_trace_usd: float = Field(1.0, ge=0)


class RulesConfig(_Strict):
    loop: LoopRuleConfig = Field(default_factory=LoopRuleConfig)
    silent_error: SilentErrorRuleConfig = Field(default_factory=SilentErrorRuleConfig)
    cost_spike: CostSpikeRuleConfig = Field(default_factory=CostSpikeRuleConfig)


class RouteConfig(_Strict):
    loss_budget_usd: float = Field(50.0, ge=0)
    hourly_ceiling_usd: float = Field(50.0, ge=0)


class AutoPauseConfig(_Strict):
    minutes: float = Field(10, gt=0)
    budget_fraction: float = Field(0.5, gt=0, le=1)


class TripwireGuardConfig(_Strict):
    max_tool_calls: int = Field(20, ge=1)
    max_minutes: float = Field(3, gt=0)


class FixPrConfig(_Strict):
    """Where the fix-PR tool branches and which GitHub repo it opens pull requests against.

    An empty `repo_path`, `github_owner` or `github_repo` turns the tool off; the tool then refuses.
    """

    repo_path: str = ""
    github_owner: str = ""
    github_repo: str = ""
    base_branch: str = Field("main", min_length=1)


class SecretNames(_Strict):
    """Names of the env vars that hold each secret. The values never appear in the config."""

    langfuse_public_key: str = "LANGFUSE_PUBLIC_KEY"
    langfuse_secret_key: str = "LANGFUSE_SECRET_KEY"
    github_token: str = "GITHUB_TOKEN"


class TripwireConfig(_Strict):
    poll_seconds: float = Field(15, gt=0)
    window_minutes: float = Field(60, gt=0)
    containment_url: str = "http://127.0.0.1:8700"
    # Overridden by the LANGFUSE_HOST env var when that is set (the detector reads it, see detector/main.py).
    langfuse_host: str = Field("http://localhost:3000", min_length=1)
    # Pages read per Langfuse list endpoint (100 rows a page) on each poll. A busier window needs a higher cap.
    langfuse_max_pages: int = Field(100, ge=1)
    # Incident record log (JSONL). The detector's --records flag overrides it.
    records_path: str = Field("incident-records.jsonl", min_length=1)
    verify_minutes: float = Field(5, gt=0)
    rules: RulesConfig = Field(default_factory=RulesConfig)
    allow_list_tools: list[str] = Field(default_factory=lambda: ["list_orders_page"])
    routes: dict[str, RouteConfig] = Field(default_factory=lambda: {"order-lookup": RouteConfig()})
    auto_pause: AutoPauseConfig = Field(default_factory=AutoPauseConfig)
    tripwire_guard: TripwireGuardConfig = Field(default_factory=TripwireGuardConfig)
    fix_pr: FixPrConfig = Field(default_factory=FixPrConfig)
    owners: list[str] = Field(default_factory=lambda: ["jason"], min_length=1)
    secrets: SecretNames = Field(default_factory=SecretNames)


def _format_validation_error(err: ValidationError, source: str) -> str:
    lines = [f"invalid config {source}:"]
    for problem in err.errors():
        loc = ".".join(str(part) for part in problem["loc"]) or "(top level)"
        lines.append(f"  - {loc}: {problem['msg']}")
    return "\n".join(lines)


def load_config_dict(data: dict[str, Any] | None, source: str = "<dict>") -> TripwireConfig:
    try:
        return TripwireConfig.model_validate(data or {})
    except ValidationError as err:
        raise ConfigError(_format_validation_error(err, source)) from None


def load_config(path: str | Path) -> TripwireConfig:
    path = Path(path)
    if not path.is_file():
        raise ConfigError(f"config file not found: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as err:
        raise ConfigError(f"could not parse {path}: {err}") from None
    if data is not None and not isinstance(data, dict):
        raise ConfigError(f"invalid config {path}: top level must be a mapping")
    return load_config_dict(data, source=str(path))


def resolve_secret(cfg: TripwireConfig, secret: str, environ: dict[str, str] | None = None) -> str:
    """Return the value of a secret from the environment. `secret` is a field of `cfg.secrets`."""
    env_name = getattr(cfg.secrets, secret, None)
    if env_name is None:
        raise ConfigError(f"unknown secret {secret!r}; expected one of {sorted(SecretNames.model_fields)}")
    env = os.environ if environ is None else environ
    value = env.get(env_name)
    if not value:
        raise ConfigError(f"secret {secret!r} needs the environment variable {env_name} to be set")
    return value


LANGFUSE_HOST_ENV = "LANGFUSE_HOST"


def resolve_langfuse_host(cfg: TripwireConfig, environ: Mapping[str, str]) -> str:
    """The LANGFUSE_HOST env var wins; otherwise the config's `langfuse_host`."""
    return environ.get(LANGFUSE_HOST_ENV) or cfg.langfuse_host
