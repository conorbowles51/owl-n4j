import { useEffect, useMemo, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { fetchAPI } from '@/lib/api-client'
import { useCase } from '@/features/cases/hooks/use-cases'
import { useCasePermissions } from '@/features/cases/hooks/use-case-permissions'
import { AudioTranscriptViewer, type AudioTranscriptViewerProps } from './AudioTranscriptViewer'
import { canonicalName } from '../utils/transcript-status'
import { resolveCanonicalSpeaker } from './audio-transcript.utils'
import { transcriptsAPI, type Transcript } from '../transcripts.api'
import { useGuardedProcess } from '../hooks/use-guarded-process'
import { ProcessHoldDialog } from './ProcessHoldDialog'
import { useEvidenceStore } from '../evidence.store'

export interface TranscriptCloseActions { dirty: boolean; save: () => Promise<void>; discard: () => void }

function SpeakerEntityPicker({ caseId, speaker, name, entityId, entityLabel, onChange }: {
  caseId: string; speaker: string; name: string; entityId?: string; entityLabel?: string; onChange: (id: string | null, label?: string) => void
}) {
  const [query, setQuery] = useState('')
  const [search, setSearch] = useState('')
  useEffect(() => { const timer = setTimeout(() => setSearch(query.trim()), 250); return () => clearTimeout(timer) }, [query])
  const results = useQuery({ queryKey: ['transcript-person-search', caseId, search], enabled: search.length > 0, staleTime: 0,
    queryFn: () => fetchAPI<{ nodes: { id: string; key: string; name: string; type: string; summary?: string; notes?: string }[] }>(
      `/api/graph/search?${new URLSearchParams({ case_id: caseId, q: search, limit: '100' })}`) })
  return <div className="min-w-0 rounded border p-2 text-xs">
    <p className="font-medium">{name}</p>
    {entityId && <p className="my-1 break-all" title={entityId}>Linked person: {entityLabel || name} <button className="underline" onClick={() => onChange(null)}>Unlink</button></p>}
    <Input className="mt-1 h-8 text-xs" aria-label={`Find case entity for ${name}`} placeholder="Find a person in this case (optional)"
      value={query} onChange={event => setQuery(event.target.value)} />
    {search && <div className="mt-1 max-h-32 overflow-y-auto" aria-label={`Case entities for ${speaker}`}>
      {results.isFetching ? 'Searching…' : results.error ? 'Could not load people. Try again.' :
        results.data?.nodes.filter(node => node.type === 'Person').map(node =>
          <button key={node.id || node.key} disabled={!node.id} className="block w-full rounded p-2 text-left hover:bg-muted disabled:opacity-50" onClick={() => { onChange(node.id, node.name); setQuery('') }}>
            {node.name} <span className="text-muted-foreground">{node.key}</span>
            {(node.summary || node.notes) && <span className="mt-1 block line-clamp-2 text-muted-foreground">{node.summary || node.notes}</span>}
          </button>)}
      {!results.isFetching && !results.data?.nodes.some(node => node.type === 'Person') && 'No matching people. Try a more specific name.'}
    </div>}
  </div>
}

export function TranscriptReviewPane({ evidenceId, caseId, registerCloseActions, ...viewerProps }: AudioTranscriptViewerProps & {
  evidenceId: string; caseId: string; registerCloseActions: (actions: TranscriptCloseActions) => void
}) {
  const client = useQueryClient()
  const capability = useQuery({ queryKey: ['audio-review-capabilities'], queryFn: transcriptsAPI.capabilities, retry: false, staleTime: 30000 })
  const reviewEnabled = capability.data?.enabled === true
  const query = useQuery({ queryKey: ['transcript', evidenceId], queryFn: () => transcriptsAPI.get(evidenceId), retry: false,
    refetchInterval: query => query.state.data?.evidence_status === 'processing' ? 3000 : false })
  const caseQuery = useCase(caseId)
  const { canEdit } = useCasePermissions(caseQuery.data)
  const [draft, setDraft] = useState<Transcript | null>(null)
  const [editing, setEditing] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showOriginal, setShowOriginal] = useState(false)
  const [showProcessed, setShowProcessed] = useState(false)
  const gate = useGuardedProcess(caseId)
  const current = draft ?? query.data
  const published = useQuery({ queryKey: ['transcript-published', evidenceId, current?.published_revision_id],
    queryFn: () => transcriptsAPI.revision(evidenceId, current!.published_revision_id!),
    enabled: showProcessed && !!current?.published_revision_id, retry: false })
  const shown = showProcessed && published.data ? { ...current!, transcription: published.data.rendered.text,
    segments: published.data.rendered.segments, speakers: published.data.payload.speakers as Record<string, string>,
    speaker_merges: published.data.payload.speaker_merges as Record<string, string> } : current
  const queue = useEvidenceStore(state => state.transcriptQueue)
  const groups = useMemo(() => current ? Array.from(new Set(current.segments.map(segment =>
    resolveCanonicalSpeaker(segment.speaker, current.speaker_merges)))) : [], [current])

  const refresh = async (saved: Transcript) => {
    client.setQueryData(['transcript', evidenceId], saved)
    setDraft(null)
    await Promise.all(['evidence', 'evidence-file', 'evidence-folder-contents', 'transcript-queue'].map(key => client.invalidateQueries({ queryKey: [key] })))
  }
  const save = async (): Promise<Transcript> => {
    if (!draft) return current!
    const saved = await transcriptsAPI.save(evidenceId, draft.revision_id, { ...draft.payload,
      speakers: draft.speakers, speaker_merges: draft.speaker_merges, speaker_entity_ids: draft.speaker_entity_ids })
    await refresh(saved)
    return saved
  }
  useEffect(() => {
    registerCloseActions({ dirty: !!draft, save: async () => { await save() }, discard: () => setDraft(null) })
  })
  useEffect(() => {
    if (!draft) return
    const handler = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = '' }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [draft])
  const action = async (operation: () => Promise<void>) => {
    if (busy) return
    setBusy(true); setError(null)
    try { await operation() } catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not save transcript') }
    finally { setBusy(false) }
  }
  const approve = async (process: boolean) => {
    const saved = await save()
    const reviewed = await transcriptsAPI.review(evidenceId, saved.revision_id, crypto.randomUUID())
    await refresh(reviewed)
    if (process) await gate.start({ fileIds: [evidenceId], reprocessCompleted: saved.evidence_status === 'processed' || !!saved.published_revision_id })
  }
  const update = (patch: Partial<Transcript>) => { if (current) setDraft({ ...current, ...patch }) }
  const index = queue.findIndex(item => item.id === evidenceId)
  const next = index >= 0 ? queue[index + 1] : undefined
  const previous = index > 0 ? queue[index - 1] : undefined

  if (!reviewEnabled && !current?.revision_id && !draft) return <AudioTranscriptViewer {...viewerProps}
    onSpeakerSettingsChange={capability.isFetched && canEdit ? viewerProps.onSpeakerSettingsChange : undefined} />

  return <div className="flex h-full min-h-0 flex-col">
    <ProcessHoldDialog gate={gate} />
    <div className="shrink-0 space-y-2 border-b bg-card px-4 py-2">
      <div className="flex flex-wrap items-center gap-2 text-xs" aria-live="polite">
        <strong>Transcript review{caseQuery.data?.title ? ` · ${caseQuery.data.title}` : ''}</strong>
        <span>{current ? canonicalName(current) : 'Transcribe this recording before reviewing.'}</span>
        {current && <span>{draft ? 'Unsaved changes' : 'Saved'}</span>}
        {query.isError && <span>Transcript review is unavailable. {query.error.message}</span>}
        {current && <Button size="sm" variant="ghost" onClick={() => setShowOriginal(v => !v)}>{showOriginal ? 'Hide original transcript' : 'View original transcript'}</Button>}
        {current?.changed_since_processing && current.published_revision_id && <Button size="sm" variant="ghost" onClick={() => setShowProcessed(v => !v)}>{showProcessed ? 'Return to working transcript' : 'View last processed transcript'}</Button>}
        {current?.changed_since_processing && !current.published_revision_id && <span>Earlier processing predates saved transcript revisions.</span>}
        {showProcessed && <span>{published.isFetching ? 'Loading processed revision…' : published.error ? 'Could not load processed revision. Return to the working transcript and try again.' : 'Viewing last processed revision'}</span>}
        {current?.evidence_status === 'processing' && <span>Processing the selected saved revision. Later edits apply to the next run.</span>}
        {!reviewEnabled && <span>Transcript review is unavailable. Saved revisions and your draft are retained.</span>}
        {canEdit && reviewEnabled && current && !showProcessed && <>
          <Button size="sm" variant="outline" onClick={() => setEditing(v => !v)}>{editing ? 'Finish editing' : 'Edit transcript'}</Button>
          <Button size="sm" variant="outline" disabled={busy || !draft} onClick={() => void action(async () => { await save() })}>Save draft</Button>
          <Button size="sm" variant="outline" disabled={busy || (current.reviewed && !draft)} onClick={() => void action(() => approve(false))}>Mark reviewed</Button>
          <Button size="sm" disabled={busy || current.evidence_status === 'processing'} onClick={() => void action(() => approve(true))}>
            {current.published_revision_id || current.evidence_status === 'processed' || current.changed_since_processing ? 'Update processed transcript' : current.reviewed ? 'Process reviewed transcript' : 'Mark reviewed and process'}
          </Button>
        </>}
        {previous && <Button size="sm" variant="ghost" disabled={busy} onClick={() => void action(async () => {
          await save(); useEvidenceStore.getState().openDetail(previous.id, { startSeconds: 0 })
        })}>Save and previous recording</Button>}
        {next && <Button size="sm" variant="ghost" disabled={busy} onClick={() => void action(async () => {
          await save(); useEvidenceStore.getState().openDetail(next.id, { startSeconds: 0 })
        })}>Save and next recording ({index + 1}/{queue.length})</Button>}
      </div>
      {error && <p role="alert" className="text-xs text-destructive">{error} Your unsaved edits are retained.</p>}
      {showOriginal && current && <div className="max-h-32 overflow-auto rounded border p-2 text-xs"><strong>Original machine transcript</strong><p className="whitespace-pre-wrap">{current.original_text}</p></div>}
      {editing && canEdit && reviewEnabled && current && !showProcessed && <div className="grid max-h-40 grid-cols-1 gap-2 overflow-auto sm:grid-cols-2 lg:grid-cols-3">
        {groups.map(speaker => <SpeakerEntityPicker key={speaker} caseId={caseId} speaker={speaker}
          name={current.speakers[speaker] || speaker} entityId={current.speaker_entity_ids[speaker]}
          entityLabel={(current.payload.entity_labels as Record<string, string> | undefined)?.[current.speaker_entity_ids[speaker]]}
          onChange={(id, label) => { const bindings = { ...current.speaker_entity_ids }; if (id) bindings[speaker] = id; else delete bindings[speaker];
            update({ speaker_entity_ids: bindings, ...(label && !current.speakers[speaker] ? { speakers: { ...current.speakers, [speaker]: label } } : {}) }) }} />)}
        <Button variant="ghost" size="sm" onClick={() => update({ segments: current.original_segments,
          transcription: current.original_text, payload: { ...current.payload, restore_original: true, text_overrides: {}, turn_speaker_overrides: {}, body_text: null } })}>Restore original words and turns</Button>
      </div>}
    </div>
    <div className="min-h-0 flex-1 overflow-y-auto md:overflow-hidden">
      <AudioTranscriptViewer {...viewerProps}
        transcription={shown?.transcription ?? viewerProps.transcription}
        segments={shown?.segments ?? viewerProps.segments} speakers={shown?.speakers ?? viewerProps.speakers}
        speakerMerges={shown?.speaker_merges ?? viewerProps.speakerMerges}
        onSpeakerSettingsChange={canEdit && reviewEnabled && current && !showProcessed ? async settings => {
          const bindings: Record<string, string> = {}
          for (const [rawSpeaker, entity] of Object.entries(current.speaker_entity_ids)) {
            const canonical = resolveCanonicalSpeaker(rawSpeaker, settings.merges)
            if (bindings[canonical] && bindings[canonical] !== entity) {
              const message = 'These speakers are linked to different case people. Unlink one before combining their labels.'
              setError(message); throw new Error(message)
            }
            bindings[canonical] = entity
          }
          update({ speakers: settings.speakers, speaker_merges: settings.merges, speaker_entity_ids: bindings }); return settings
        } : undefined}
        onTurnTextChange={editing && canEdit && reviewEnabled && current && !showProcessed ? (id, text) => update({
          segments: current.segments.map(turn => turn.id === id ? { ...turn, text } : turn),
          payload: { ...current.payload, text_overrides: { ...(current.payload.text_overrides as object), [id]: text } },
        }) : undefined}
        onTurnSpeakerChange={editing && canEdit && reviewEnabled && current && !showProcessed ? (id, speaker) => update({
          segments: current.segments.map(turn => turn.id === id ? { ...turn, speaker } : turn),
          payload: { ...current.payload, turn_speaker_overrides: { ...(current.payload.turn_speaker_overrides as object), [id]: speaker } },
        }) : undefined}
        onBodyTextChange={editing && canEdit && reviewEnabled && current && !showProcessed ? text => update({ transcription: text, payload: { ...current.payload, body_text: text } }) : undefined}
      />
    </div>
  </div>
}
