from functools import lru_cache

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class EmailSenderIdentity(BaseModel):
    """One "From" identity an email can be sent as. id is the stable key the
    frontend selects by (never the email address itself, so swapping which
    Gmail account backs an identity later doesn't break saved selections).
    """

    id: str
    display_name: str
    email: str
    app_password: str


class Settings(BaseSettings):
    """Runtime config, loaded from environment / .env.

    Kept as one flat settings object so every module reads config the same
    way instead of each agent parsing its own env vars.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    gemini_api_key: str = ""
    gemini_generation_model: str = "gemini-2.5-flash"

    content_library_db_path: str = "data/content_library.db"
    asset_bank_path: str = "data/assets"
    topic_data_path: str = "data/topics"
    brochure_files_path: str = "data/brochures"
    api_public_base_url: str = "http://127.0.0.1:8123"
    usage_db_path: str = "data/usage.db"
    leads_db_path: str = "data/leads.db"

    # A solo trainer's own identity -- surfaced in the brochure footer and
    # checked for by ComplianceAgent's brand-consistency check. One global
    # value (not per-topic) since this app is scoped to a single trainer.
    trainer_name: str = ""
    trainer_contact: str = ""

    # Multiple "send as" identities, e.g. both the trainer's own inbox and a
    # personal one -- the user picks which to send a given email as. Set via
    # a single JSON-array env var, e.g.:
    #   EMAIL_SENDERS=[{"id":"sakshi","display_name":"Sakshi Dua","email":"sakshidua.imagecoach@gmail.com","app_password":"..."}]
    # Each app_password is a Gmail *App Password* (Google Account -> Security
    # -> App Passwords), never the account's real login password.
    email_senders: list[EmailSenderIdentity] = []

    # Legacy single-sender config -- still read as a fallback (via
    # resolved_email_senders()) so a deployment that only ever set these two
    # keeps working unchanged after this multi-sender feature shipped.
    gmail_address: str = ""
    gmail_app_password: str = ""
    gmail_sender_name: str = ""

    # Hard ceiling on paid AI hero-image generations per day, enforced by
    # UsageTrackingImageClient -- protects against runaway spend regardless
    # of how many times "Generate with AI" gets clicked.
    max_daily_ai_images: int = 10

    def resolved_email_senders(self) -> list[EmailSenderIdentity]:
        if self.email_senders:
            return self.email_senders
        if self.gmail_address and self.gmail_app_password:
            return [
                EmailSenderIdentity(
                    id="default",
                    display_name=self.gmail_sender_name or self.trainer_name or self.gmail_address,
                    email=self.gmail_address,
                    app_password=self.gmail_app_password,
                )
            ]
        return []


@lru_cache
def get_settings() -> Settings:
    return Settings()
