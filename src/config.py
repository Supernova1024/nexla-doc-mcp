"""Centralized configuration with environment variable overrides."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    project_root: Path = field(default_factory=lambda: Path(__file__).resolve().parent.parent)

    chunk_size: int = 800
    chunk_overlap: int = 200

    collection_name: str = "nexla_documents"

    llm_provider: str = "openai"
    anthropic_model: str = "claude-sonnet-4-20250514"
    openai_model: str = "gpt-4o"
    temperature: float = 0.1

    anthropic_api_key: str = ""
    openai_api_key: str = ""

    @property
    def data_dir(self) -> Path:
        return self.project_root / "data"

    @property
    def chroma_dir(self) -> Path:
        return self.project_root / ".chroma_db"

    def __post_init__(self):
        env_map = {
            "PROJECT_ROOT": ("project_root", Path),
            "DATA_DIR": None,
            "CHROMA_DIR": None,
            "CHUNK_SIZE": ("chunk_size", int),
            "CHUNK_OVERLAP": ("chunk_overlap", int),
            "COLLECTION_NAME": ("collection_name", str),
            "LLM_PROVIDER": ("llm_provider", str),
            "ANTHROPIC_MODEL": ("anthropic_model", str),
            "OPENAI_MODEL": ("openai_model", str),
            "TEMPERATURE": ("temperature", float),
            "ANTHROPIC_API_KEY": ("anthropic_api_key", str),
            "OPENAI_API_KEY": ("openai_api_key", str),
        }

        for env_var, mapping in env_map.items():
            value = os.environ.get(env_var)
            if value is not None and mapping is not None:
                attr_name, cast_fn = mapping
                setattr(self, attr_name, cast_fn(value))

        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.chroma_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
