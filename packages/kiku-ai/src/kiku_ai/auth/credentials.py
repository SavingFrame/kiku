from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field


class ApiKeyCredential(BaseModel):
    type: Literal["api_key"] = "api_key"
    key: str


class OAuthCredential(BaseModel):
    type: Literal["oauth"] = "oauth"
    access: str
    refresh: str
    expires: float
    extra: dict[str, Any] = Field(default_factory=dict)


Credential = Annotated[
    ApiKeyCredential | OAuthCredential,
    Field(discriminator="type"),
]
