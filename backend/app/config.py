"""Application settings, read from environment variables.

No secret has a default value. In Azure, secrets are injected from Key Vault
through Container Apps secret references; locally they come from a .env file
that is git-ignored.
"""
from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="KA_", extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"
    database_url: str = "sqlite:///./local.db"

    # Identity of the only person allowed to approve actions.
    owner_email: str = Field(..., description="Owner's sign-in email (Entra ID)")
    # Local development only: lets the owner sign in without Entra ID.
    # Refused at startup when app_env == "production".
    dev_auth_bypass: bool = False

    # Cost controls (INR).
    monthly_budget_inr: float = 4000.0
    max_posts_per_day: int = 3

    # Text generation. "mock" needs nothing and costs nothing; "azure_openai" is the real model.
    text_provider: Literal["mock", "azure_openai"] = "mock"
    azure_openai_endpoint: str | None = None
    azure_openai_deployment: str | None = None
    text_max_output_tokens: int = 4000
    # INR per 1M tokens. Conservative defaults; set from the Azure pricing page for your model.
    text_price_in_inr_per_m: float = 100.0
    text_price_out_inr_per_m: float = 600.0

    # Secrets: never logged, never sent to the browser.
    # Only for local use; in Azure the app signs in with its managed identity instead.
    azure_openai_api_key: SecretStr | None = None
    # Instagram (Phase 6). App ID is public; secret and encryption key come from Key Vault.
    instagram_app_id: str | None = None
    instagram_app_secret: SecretStr | None = None
    token_encryption_key: SecretStr | None = None
    # Public base URL of this app, used for the OAuth redirect and signed image links.
    public_base_url: str | None = None

    @property
    def instagram_ready(self) -> bool:
        return bool(self.instagram_app_id and self.instagram_app_secret and self.token_encryption_key
                    and self.public_base_url)

    def validate_for_runtime(self) -> None:
        if self.app_env == "production" and self.dev_auth_bypass:
            raise RuntimeError("KA_DEV_AUTH_BYPASS must be false in production")
        if self.monthly_budget_inr <= 0:
            raise RuntimeError("KA_MONTHLY_BUDGET_INR must be positive")


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.validate_for_runtime()
    return s
