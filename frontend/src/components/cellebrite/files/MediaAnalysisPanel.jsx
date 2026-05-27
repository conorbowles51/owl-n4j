import React, { useState, useEffect, useCallback } from 'react';
import { Mic, Eye, Loader2, RotateCw, Languages, AlertCircle } from 'lucide-react';
import { evidenceAPI } from '../../../services/api';

/**
 * image | transcription | null — what AI action applies to a file, from its
 * Cellebrite category (Image/Audio/Video) else its filename extension.
 */
export function mediaKindFor(category, filename) {
  const c = (category || '').toLowerCase();
  if (c === 'image') return 'image';
  if (c === 'audio' || c === 'video') return 'transcription';
  const ext = (filename || '').toLowerCase().split('.').pop();
  if (['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'heic', 'heif', 'tif', 'tiff'].includes(ext)) return 'image';
  if (['mp3', 'wav', 'm4a', 'aac', 'ogg', 'opus', 'amr', 'flac', '3gp', 'mp4', 'mov', 'm4v', 'mkv', 'webm'].includes(ext)) return 'transcription';
  return null;
}

/**
 * "Send to AI processing" panel for one media evidence file — transcription
 * (audio/voice/video, local Whisper) or image recognition (OpenAI vision).
 * Shared by the Files viewer (FileDetailPanel) and Cellebrite message
 * attachments (CommsAttachment), so the action behaves identically everywhere.
 *
 * Props:
 *   evidenceId    — the evidence row to analyse (attachments carry this).
 *   kind          — 'image' | 'transcription'. Omit to derive from category/filename.
 *   category, filename — used to derive `kind` when not passed.
 *   autoLoadCache — fetch any previously-computed result on mount. ON for the
 *                   single-file viewer; OFF for chat attachments (avoids one
 *                   GET per attachment in a thread of hundreds).
 *   compact       — denser styling for inline use under a chat attachment.
 */
export default function MediaAnalysisPanel({
  evidenceId,
  kind: kindProp,
  category,
  filename,
  autoLoadCache = false,
  compact = false,
}) {
  const kind = kindProp || mediaKindFor(category, filename);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [translate, setTranslate] = useState(false); // transcription → English

  const cacheKey = kind === 'image' ? 'image_analysis' : 'transcription';

  useEffect(() => {
    if (!evidenceId || !kind || !autoLoadCache) return undefined;
    let cancelled = false;
    setResult(null);
    setError(null);
    evidenceAPI.getAnalysis(evidenceId)
      .then((res) => { if (!cancelled) setResult(res?.media_analysis?.[cacheKey] || null); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [evidenceId, kind, cacheKey, autoLoadCache]);

  const run = useCallback(async (force = false) => {
    if (!evidenceId || !kind) return;
    setLoading(true);
    setError(null);
    try {
      const res = await evidenceAPI.analyzeMedia(evidenceId, {
        kind,
        force,
        task: kind === 'transcription' && translate ? 'translate' : 'transcribe',
      });
      setResult(res?.result || null);
    } catch (e) {
      setError(e?.message || 'Analysis failed');
    } finally {
      setLoading(false);
    }
  }, [evidenceId, kind, translate]);

  if (!evidenceId || !kind) return null;

  const isImage = kind === 'image';
  const Icon = isImage ? Eye : Mic;
  const label = isImage ? 'Recognize image' : 'Transcribe';
  const runningLabel = isImage ? 'Analyzing…' : 'Transcribing…';

  return (
    <div className={compact ? 'mt-1' : ''}>
      {!result && (
        <div className="flex items-center gap-1.5 flex-wrap">
          <button
            type="button"
            onClick={() => run(false)}
            disabled={loading}
            className={`inline-flex items-center gap-1 rounded border text-xs disabled:opacity-50 ${
              compact
                ? 'px-1.5 py-0.5 border-owl-blue-200 bg-owl-blue-50 text-owl-blue-700 hover:bg-owl-blue-100 text-[11px]'
                : 'px-2 py-1 border-light-300 hover:bg-light-50 text-light-700'
            }`}
            title={isImage ? 'Run AI image recognition on this image' : 'Transcribe this audio with AI'}
          >
            {loading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Icon className="w-3 h-3" />}
            {loading ? runningLabel : label}
          </button>
          {!isImage && !loading && (
            <button
              type="button"
              onClick={() => setTranslate((v) => !v)}
              className={`inline-flex items-center gap-1 text-[10px] ${translate ? 'text-emerald-700' : 'text-light-500'} hover:underline`}
              title="Translate the transcript to English instead of transcribing in the original language"
            >
              <Languages className="w-3 h-3" />
              {translate ? 'to English' : 'orig. language'}
            </button>
          )}
        </div>
      )}

      {error && (
        <div className="mt-1 flex items-start gap-1 text-[11px] text-red-600">
          <AlertCircle className="w-3 h-3 flex-shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      {result && (
        <div className={`mt-1 rounded border border-light-200 bg-light-50 ${compact ? 'p-1.5' : 'p-2'}`}>
          <div className="flex items-center gap-1.5 mb-1">
            <Icon className="w-3 h-3 text-owl-blue-600" />
            <span className="text-[10px] font-semibold uppercase tracking-wide text-light-600">
              {isImage ? 'Image recognition' : 'Transcript'}
            </span>
            <span className="text-[9px] text-light-400">
              {result.model || result.provider || ''}
              {result.task === 'translate' ? ' · EN' : (result.language ? ` · ${result.language}` : '')}
            </span>
            <button
              type="button"
              onClick={() => run(true)}
              disabled={loading}
              className="ml-auto inline-flex items-center gap-0.5 text-[10px] text-light-500 hover:text-owl-blue-700 disabled:opacity-50"
              title="Re-run analysis"
            >
              {loading ? <Loader2 className="w-3 h-3 animate-spin" /> : <RotateCw className="w-3 h-3" />}
              {loading ? '' : 'Re-run'}
            </button>
          </div>
          <div className={`whitespace-pre-wrap break-words text-light-800 ${compact ? 'text-[11px] max-h-40 overflow-y-auto' : 'text-xs max-h-64 overflow-y-auto'}`}>
            {result.text ? result.text : <span className="italic text-light-400">No text detected.</span>}
          </div>
        </div>
      )}
    </div>
  );
}
