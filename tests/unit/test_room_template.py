"""The Switch room template keys match TEMPLATES.md (H-PREP): a key Switch does not read is a silent no-op."""

from __future__ import annotations

from pathlib import Path

import yaml

from tests.conftest import REPO_ROOT

TEMPLATE = REPO_ROOT / "tripwire_agent" / "room_template.yaml"
ADDRESSING_VALUES = {"owner", "owner-agents", "anyone"}
AGENT_KEYS = {
    "name", "display_name", "icon_url", "description", "instructions", "provider", "machine", "location",
    "directory", "model", "advanced_config", "isolation", "auto_mode", "auto_approve", "can_manage_agents",
    "connections", "repo", "sources", "addressing", "join", "allow_existing",
}


def _template() -> dict:
    return yaml.safe_load(TEMPLATE.read_text(encoding="utf-8"))


def test_template_uses_version_key_not_template_version() -> None:
    """TEMPLATES.md names the key `version`. `template_version` is not read, so it is a silent no-op."""
    template = _template()

    assert "template_version" not in template
    assert template["version"] in (1, 2)


def test_template_agent_keys_are_known_to_switch() -> None:
    """Every agent field is one TEMPLATES.md documents."""
    unknown = set(_template()["agent"]) - AGENT_KEYS

    assert unknown == set()


def test_template_addressing_is_a_documented_value() -> None:
    """Addressing takes owner, owner-agents or anyone in the template."""
    assert _template()["agent"]["addressing"] in ADDRESSING_VALUES


def test_template_instructions_name_the_reply_approval() -> None:
    """The template carries the reply-based approval line, so Console imports the same rule the file states."""
    instructions = _template()["agent"]["instructions"]

    assert "reply `@tripwire approve`" in instructions
    assert "Allow once" not in instructions
