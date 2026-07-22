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
    service_api_key: str = ""

    # OpenAI
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    gemini_api_key: str = ""
    ai_credential_encryption_key: str = "loupe-development-ai-credentials-change-me"
    openai_model: str = "gpt-5.6-terra"
    openai_extraction_model: str = "gpt-5.6-terra"
    openai_resolution_model: str = "gpt-5.6-terra"
    openai_summary_model: str = "gpt-5.6-terra"
    openai_document_summary_model: str = "gpt-5.6-sol"
    openai_quality_model: str = "gpt-5.6-terra"
    openai_embedding_model: str = "text-embedding-3-small"
    openai_embedding_batch_size: int = 16
    openai_embedding_max_batch_chars: int = 80000
    extraction_max_concurrency: int = 6
    document_summary_max_concurrency: int = 3
    claim_verification_enabled: bool = True
    claim_verification_max_claims: int = 250
    claim_verification_batch_size: int = 20
    claim_verification_max_concurrency: int = 2

    # Quality thresholds
    entity_confidence_threshold: float = 0.4
    relationship_confidence_threshold: float = 0.3
    merge_confidence_threshold: float = 0.8

    # Storage
    storage_path: str = "/data/files"
    cellebrite_data_root: str = "evidence-data"
    max_upload_file_bytes: int = 1_073_741_824
    max_upload_batch_files: int = 50
    max_upload_batch_bytes: int = 5_368_709_120
    upload_read_chunk_bytes: int = 1_048_576
    batch_file_max_concurrency: int = 4
    max_extracted_characters: int = 50_000_000
    max_pdf_pages: int = 2_000
    max_image_pixels: int = 25_000_000
    max_image_file_bytes: int = 50_000_000
    max_text_input_bytes: int = 100_000_000
    max_office_uncompressed_bytes: int = 500_000_000
    max_office_archive_entries: int = 10_000

    # Image processing
    image_provider: str = "tesseract"  # "tesseract" or "openai"
    tesseract_lang: str = "eng"
    pdf_ocr_dpi: int = 300
    pdf_ocr_max_pixels: int = 25_000_000
    pdf_ocr_page_timeout_seconds: int = 300
    pdf_ocr_max_concurrency: int = 2
    openai_vision_model: str = "gpt-4o"
    openai_transcription_model: str = "gpt-4o-mini-transcribe"
    audio_transcription_segment_seconds: int = 240
    audio_transcription_max_single_seconds: int = 240

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
