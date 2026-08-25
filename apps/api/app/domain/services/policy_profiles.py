from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from app.domain.exceptions.errors import PolicyValidationError

DEFAULT_POLICY_PROFILE = "INTERNET_NO_AI"


@dataclass(frozen=True, slots=True)
class PolicyProfileDefinition:
    id: str
    label: str
    description: str
    rules: dict[str, Any]


class PolicyProfileCatalog:
    """Domain catalog of policy choices offered to teachers."""

    def __init__(self, profiles: tuple[PolicyProfileDefinition, ...]):
        self._profiles = profiles
        self._by_id = {profile.id: profile for profile in profiles}

    def get(self, profile_id: str) -> PolicyProfileDefinition:
        normalized = profile_id.strip().upper()
        try:
            profile = self._by_id[normalized]
        except KeyError as exc:
            raise PolicyValidationError(
                f"unknown policy profile: {profile_id}"
            ) from exc
        return PolicyProfileDefinition(
            id=profile.id,
            label=profile.label,
            description=profile.description,
            rules=deepcopy(profile.rules),
        )

    def list_all(self) -> list[PolicyProfileDefinition]:
        return [self.get(profile.id) for profile in self._profiles]


BUILT_IN_POLICY_PROFILES = PolicyProfileCatalog(
    (
        PolicyProfileDefinition(
            id=DEFAULT_POLICY_PROFILE,
            label="Internet + No AI",
            description=(
                "Allow programming tools and general Internet access while blocking "
                "generative AI, social networks, remote-control software, and USB storage."
            ),
            rules={
                "applications": {
                    "allow": ["vscode.exe", "gcc.exe"],
                    "deny": ["chatgpt.exe", "anydesk.exe", "teamviewer.exe"],
                },
                "network": {"block": ["generative_ai", "social_network"]},
                "devices": {"usb": "deny"},
            },
        ),
        PolicyProfileDefinition(
            id="OFFLINE_PROGRAMMING",
            label="Offline Programming",
            description=(
                "Allow local programming tools while blocking Internet categories, "
                "remote-control software, and USB storage."
            ),
            rules={
                "applications": {
                    "allow": ["vscode.exe", "gcc.exe"],
                    "deny": [
                        "chrome.exe",
                        "msedge.exe",
                        "firefox.exe",
                        "anydesk.exe",
                        "teamviewer.exe",
                    ],
                },
                "network": {
                    "block": ["generative_ai", "social_network", "vpn_proxy"]
                },
                "devices": {"usb": "deny"},
            },
        ),
    )
)
