"""Reserve worker capacity for statement reading independently of long AI jobs."""
from arq.constants import default_queue_name

PDF_REVIEW_QUEUE = 'arq:pdf-review'


def batch_queue(jobs):
    return PDF_REVIEW_QUEUE if jobs and all(job.job_type == 'pdf_review' for job in jobs) else default_queue_name
