"""Reserve worker capacity for statement reading independently of long AI jobs."""
from arq.constants import default_queue_name

PDF_REVIEW_QUEUE = 'arq:pdf-review'
PHONE_CAPTURE_QUEUE = 'arq:phone-capture'  # one phone at a time on its own worker (01 section 10.2)

AUDIO_REVIEW_QUEUE = 'arq:audio-review-v1'
AUDIO_REVIEW_HEARTBEAT = 'loupe:audio-review-v1:worker-ready'


def batch_queue(jobs):
    from pathlib import Path
    from services.audio_media import SUPPORTED_AUDIO_EXTENSIONS
    from services.transcript_review import feature_enabled
    if any(job.job_type == 'audio_review' or (getattr(job, 'pipeline_state', None) or {}).get('transcript_revision_id')
           or (feature_enabled() and Path(getattr(job, 'file_name', '')).suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS) for job in jobs):
        return AUDIO_REVIEW_QUEUE
    return PDF_REVIEW_QUEUE if jobs and all(job.job_type == 'pdf_review' for job in jobs) else default_queue_name


async def audio_worker_heartbeat(ctx):
    from services.transcript_review import feature_enabled
    if feature_enabled():
        await ctx['redis'].set(AUDIO_REVIEW_HEARTBEAT, '1', ex=90)
