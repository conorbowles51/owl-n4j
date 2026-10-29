"""Which models can read page images: the one check every image-sending path uses before it sends.

A model that takes text only does not always refuse an image: DeepSeek V4 Pro (``deepseek-v4-pro``) accepts a
request carrying image parts, ignores them and answers anyway (measured 2026-10-28 on Loupe's key: a synthetic
image printing "1,234.56 / 789.01" was answered "1 and 0"). So a statement page image may only go to a model
the provider itself lists as taking images; anything else fails closed (the statement stays held with the
reason ``CANNOT_READ_IMAGES``; a WARNING goes to the journal) and nothing is sent.

* DeepSeek: the provider's own model list (``GET https://api.deepseek.com/models``, each model's
  ``input_modalities``), fetched with Loupe's stored key, kept for a day (``REFRESH_SECONDS``). When it cannot
  be fetched, the last list fetched within ``STALE_SECONDS`` is used, else the model is refused.
* OpenAI: ``OPENAI_IMAGE_MODELS``, a maintained allowlist of OpenAI models that take image input. A model not
  on it is refused until it is added here (with a measurement) - a new model is never assumed to read images.
* Every other provider: refused (no page-image path is approved for it).
"""
from __future__ import annotations

import logging
import threading
import time

log = logging.getLogger(__name__)

CANNOT_READ_IMAGES = 'this model cannot read page images'

# OpenAI models measured reading statement page images in Loupe: gpt-5.6-terra (the financial_vision default,
# proving held BNB2 statements in document mode, 2026-10-24) and gpt-4o (the same measurement). Another model is
# added here only with a measurement of it reading page images.
OPENAI_IMAGE_MODELS = frozenset({'gpt-5.6-terra', 'gpt-4o'})

DEEPSEEK_MODELS_URL = 'https://api.deepseek.com/models'
REFRESH_SECONDS = 24 * 3600
STALE_SECONDS = 48 * 3600

_lock = threading.Lock()
_cache = {}  # provider -> {'fetched': epoch seconds, 'models': {model id: set of input modalities}}


class ModelCannotReadImages(ValueError):
    """Raised instead of sending page images to a model that does not take them."""


def _fetch_deepseek(api_key, timeout=15):
    import requests
    response = requests.get(DEEPSEEK_MODELS_URL, headers={'Authorization': f'Bearer {api_key}'}, timeout=timeout)
    response.raise_for_status()
    models = {}
    for entry in response.json().get('data') or []:
        modalities = entry.get('input_modalities')
        if isinstance(modalities, list):
            models[str(entry.get('id'))] = {str(m).lower() for m in modalities}
        else:
            models[str(entry.get('id'))] = set()  # no modalities listed: not known to take images
    return models


def provider_models(provider, *, api_key=None, fetch=None, now=None):
    """{model id: input modalities} as the provider lists them (cached), or None when no fresh-enough list."""
    now = time.time() if now is None else now
    with _lock:
        cached = _cache.get(provider)
    if cached and now - cached['fetched'] < REFRESH_SECONDS:
        return cached['models']
    if provider != 'deepseek' or not (api_key or fetch):
        return cached['models'] if cached and now - cached['fetched'] < STALE_SECONDS else None
    try:
        models = (fetch or _fetch_deepseek)(api_key)
    except Exception as error:  # noqa: BLE001 - an unreachable list is never read as permission
        log.warning('The %s model list could not be fetched (%s: %s)', provider, type(error).__name__, str(error)[:200])
        return cached['models'] if cached and now - cached['fetched'] < STALE_SECONDS else None
    with _lock:
        _cache[provider] = dict(fetched=now, models=models)
    return models


def accepts_images(provider, model_id, *, api_key=None, fetch=None, now=None):
    """(True, '') when ``model_id`` of ``provider`` takes images, else (False, why)."""
    provider = str(provider or '').strip().lower()
    model_id = str(model_id or '').strip()
    if provider == 'openai':
        if model_id in OPENAI_IMAGE_MODELS:
            return True, ''
        return False, f'{model_id} is not on the list of OpenAI models known to read images'
    if provider == 'deepseek':
        models = provider_models('deepseek', api_key=api_key, fetch=fetch, now=now)
        if models is None:
            return False, "DeepSeek's model list could not be fetched to confirm the model reads images"
        if model_id not in models:
            return False, f'DeepSeek does not list a model {model_id}'
        if 'image' not in models[model_id]:
            return False, f'DeepSeek lists {model_id} as taking {", ".join(sorted(models[model_id])) or "no"} input, not images'
        return True, ''
    return False, f'page images are not sent to {provider or "an unnamed provider"}'


def require_images(provider, model_id, *, api_key=None, fetch=None, context=''):
    """Raise ModelCannotReadImages (and warn in the journal) unless the model takes images."""
    ok, why = accepts_images(provider, model_id, api_key=api_key, fetch=fetch)
    if not ok:
        log.warning('Page images not sent%s: %s (%s %s: %s)', f' ({context})' if context else '', CANNOT_READ_IMAGES,
                    provider, model_id, why)
        raise ModelCannotReadImages(f'{CANNOT_READ_IMAGES} ({why})')


def clear_cache():
    with _lock:
        _cache.clear()
