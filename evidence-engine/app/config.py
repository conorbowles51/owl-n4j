from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # PostgreSQL (shared with backend — owl_db)
    database_url: str = "postgresql+asyncpg://owl_us:owl_pw@localhost:5432/owl_db"

    # Neo4j
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "password"

    # ChromaDB
    chroma_host: str = "localhost"
    chroma_port: int = 8000

    # Redis
    redis_url: str = "redis://localhost:6379"

    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-5-mini"
    openai_extraction_model: str = "gpt-5-mini"
    openai_resolution_model: str = "gpt-5-mini"
    openai_summary_model: str = "gpt-5-mini"
    openai_document_summary_model: str = "gpt-5-mini"
    openai_quality_model: str = "gpt-5-mini"
    openai_embedding_model: str = "text-embedding-3-small"

    # Quality thresholds
    entity_confidence_threshold: float = 0.4
    relationship_confidence_threshold: float = 0.3

    # Storage
    storage_path: str = "/data/files"

    # Image processing
    image_provider: str = "tesseract"  # "tesseract" or "openai"
    tesseract_lang: str = "eng"
    openai_vision_model: str = "gpt-4o"
    openai_transcription_model: str = "gpt-4o-mini-transcribe"

    # Video processing
    video_frame_interval: int = 30  # seconds between extracted frames
    video_max_frames: int = 50

    # Geocoding
    geocoding_provider: str = "nominatim"
    geocoding_nominatim_url: str = "https://nominatim.openstreetmap.org/search"
    geocoding_user_agent: str = "InvestigationConsole/1.0"
    geocoding_timeout_seconds: float = 10.0

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()
