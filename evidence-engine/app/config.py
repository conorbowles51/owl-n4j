from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # PostgreSQL
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/ingestion"

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
    openai_model: str = "gpt-4o-mini"
    openai_quality_model: str = "gpt-4o"
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

    # Video processing
    video_frame_interval: int = 30  # seconds between extracted frames
    video_max_frames: int = 50

    # Google Maps Geocoding
    google_maps_api_key: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
