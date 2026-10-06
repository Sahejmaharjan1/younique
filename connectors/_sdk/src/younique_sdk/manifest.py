from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class PermissionBundle(BaseModel):
    key: str
    display_name: str
    description: str
    scopes: list[str] = Field(default_factory=list)
    tools: list[str]
    risk: Literal["low", "medium", "high"]
    produces_untrusted_content: bool


class ToolSpec(BaseModel):
    key: str
    title: str
    description: str
    risk: Literal["low", "medium", "high"]
    bundle: str
    input_schema: dict[str, Any] = Field(default_factory=dict)


class ConnectorManifest(BaseModel):
    key: str
    display_name: str
    description: str
    auth: Literal["oauth", "smtp", "none", "webhook"]
    limitations: list[str]
    bundles: list[PermissionBundle]
    approval_status: str = "not_applicable"
