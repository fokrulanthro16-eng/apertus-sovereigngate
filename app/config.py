from functools import lru_cache
from typing import Dict, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration settings for Apertus SovereignGate."""

    # Sovereign Backend: CSCS Inference API (Primary)
    cscs_base_url: str = "https://api.inference.cscs.ch/v1"
    cscs_api_key: str = ""

    # Secondary Backend: Hugging Face Inference API (Fallback)
    hf_base_url: str = "https://router.huggingface.co/v1"
    hf_api_key: str = ""

    # Server settings
    port: int = 8000
    environment: str = "development"
    app_name: str = "Apertus SovereignGate"
    app_version: str = "1.0.0"

    # Default LLM configuration
    default_model: str = "apertus-8b"
    timeout_seconds: float = 60.0

    # Model Alias Mappings
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def resolve_cscs_model(self, requested_model: Optional[str] = None) -> str:
        """Resolve requested model name to actual CSCS endpoint model identifier."""
        req = (requested_model or self.default_model).lower().strip()
        mapping = {
            "apertus-8b": "swiss-ai/Apertus-v1.5-8B",
            "apertus-70b": "swiss-ai/Apertus-v1.5-70B",
            "swiss-ai/apertus-8b": "swiss-ai/Apertus-v1.5-8B",
            "swiss-ai/apertus-70b": "swiss-ai/Apertus-v1.5-70B",
            "apertus-8b-instruct": "swiss-ai/Apertus-v1.5-8B",
            "apertus-70b-instruct": "swiss-ai/Apertus-v1.5-70B",
            "cscs-70b": "swiss-ai/Apertus-v1.5-70B",
            "cscs-8b": "swiss-ai/Apertus-v1.5-8B",
        }
        return mapping.get(req, requested_model or "swiss-ai/Apertus-v1.5-8B")

    def resolve_hf_model(self, requested_model: Optional[str] = None) -> str:
        """Resolve requested model name to HF fallback model identifier."""
        req = (requested_model or self.default_model).lower().strip()
        mapping = {
            "apertus-8b": "swiss-ai/Apertus-8B-Instruct-2509",
            "apertus-70b": "swiss-ai/Apertus-8B-Instruct-2509",
            "hf-fallback": "swiss-ai/Apertus-8B-Instruct-2509",
            "hf-apertus-8b": "swiss-ai/Apertus-8B-Instruct-2509",
            "swiss-ai/apertus-8b": "swiss-ai/Apertus-8B-Instruct-2509",
            "swiss-ai/apertus-70b": "swiss-ai/Apertus-8B-Instruct-2509",
        }
        return mapping.get(req, "swiss-ai/Apertus-8B-Instruct-2509")


@lru_cache
def get_settings() -> Settings:
    """Return cached instance of application settings."""
    return Settings()
