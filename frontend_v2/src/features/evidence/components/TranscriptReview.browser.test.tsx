import '@/styles/globals.css'
import { useState } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { page } from 'vitest/browser'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { DocumentViewer } from '@/components/ui/document-viewer'
import { AudioTranscriptViewer } from './AudioTranscriptViewer'
import type { Transcript } from '../transcripts.api'

const permissions = vi.hoisted(() => ({ edit: true }))
vi.mock('@/features/cases/hooks/use-cases', () => ({ useCase: () => ({ data: { title: 'Synthetic review case' } }) }))
vi.mock('@/features/cases/hooks/use-case-permissions', () => ({ useCasePermissions: () => ({ canEdit: permissions.edit }) }))
vi.mock('@/lib/protected-file', () => ({ useProtectedObjectUrl: () => ({ objectUrl: null, loading: false, error: null }), openProtectedFile: vi.fn() }))

let saved: Transcript
let processed = 0
beforeEach(() => {
  permissions.edit = true; processed = 0
  const segments = [{ id: 'turn-1', speaker: 'A', start: 0, end: 1, text: 'I spoke to Erc.' },
    { id: 'turn-2', speaker: 'B', start: 1, end: 2, text: 'Yes.' }]
  saved = { evidence_status: 'unprocessed', evidence_id: 'audio', case_id: 'case', revision_id: 'revision-1',
    original_text: 'I spoke to Erc. Yes.', original_segments: segments, transcription: 'I spoke to Erc. Yes.', segments,
    speakers: {}, speaker_merges: {}, speaker_entity_ids: {}, review_state: 'awaiting_review', reviewed: false, review_required: true,
    payload: { text_overrides: {}, turn_speaker_overrides: {}, speakers: {}, speaker_merges: {}, speaker_entity_ids: {} } }
  const originalFetch = globalThis.fetch
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, options) => {
    const url = String(input)
    if (!url.startsWith('/api/')) return originalFetch(input, options)
    const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
    if (url.includes('capabilities')) return json({ enabled: true })
    if (url.includes('/graph/search')) return json({ nodes: [{ id: 'person-john', key: 'john', name: 'John', type: 'Person' }] })
    if (url.endsWith('/transcript/reviews')) {
      expect(JSON.parse(options!.body as string).revision_id).toBe(saved.revision_id)
      saved = { ...saved, reviewed: true, review_state: 'ready' }; return json(saved, 201)
    }
    if (url.endsWith('/transcript')) {
      if (options?.method === 'PATCH') {
        const update = JSON.parse(options.body as string)
        expect(update.expected_revision_id).toBe(saved.revision_id)
        saved = { ...saved, revision_id: 'revision-2', reviewed: false, review_state: 'awaiting_review', payload: update,
          speakers: update.speakers, speaker_merges: update.speaker_merges, speaker_entity_ids: update.speaker_entity_ids,
          segments: saved.original_segments.map(turn => ({ ...turn, text: update.text_overrides[turn.id] ?? turn.text,
            speaker: update.turn_speaker_overrides[turn.id] ?? turn.speaker })) }
      }
      return json(saved)
    }
    if (url.includes('route-check')) return json({ files: [{ file_id: 'audio', outcome: 'not_native', blocks_document_processing: false }], summary: {} })
    if (url.endsWith('/processing-plans')) return json({ id: 'frozen-plan', unreviewed_audio_count: 0 })
    if (url.endsWith('/executions')) { processed++; return json({ state: 'completed', job_ids: ['job-audio'] }, 202) }
    throw new Error(`Unexpected transcript request: ${url}`)
  })
})
afterEach(() => { cleanup(); vi.restoreAllMocks() })

function Harness() {
  const [open, setOpen] = useState(true)
  return <><button onClick={() => setOpen(true)}>Reopen recording</button><DocumentViewer caseId="case" evidenceId="audio"
    documentName="Synthetic call.wav" documentUrl="/api/evidence/audio/file" open={open} onOpenChange={setOpen} /></>
}
function openViewer() {
  return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}>
    <MemoryRouter><Harness /></MemoryRouter></QueryClientProvider>)
}

it('saves corrected words and an exact case person, reopens, reviews, then processes separately', async () => {
  await page.viewport(1440, 900)
  openViewer()
  fireEvent.click(await screen.findByRole('button', { name: 'Edit transcript' }))
  fireEvent.change(screen.getByLabelText('Transcript turn 1'), { target: { value: 'I spoke to Eric.' } })
  fireEvent.change(screen.getByLabelText('Find case entity for A'), { target: { value: 'John' } })
  fireEvent.click(await screen.findByRole('button', { name: /John john/ }))
  fireEvent.click(screen.getByRole('button', { name: 'Save draft' }))
  await waitFor(() => expect(saved.speaker_entity_ids).toEqual({ A: 'person-john' }))
  await waitFor(() => expect(screen.queryByText('Unsaved changes')).toBeNull())
  expect(saved.reviewed).toBe(false); expect(processed).toBe(0)
  fireEvent.click(screen.getByRole('button', { name: 'Close document' }))
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  fireEvent.click(screen.getByRole('button', { name: 'Reopen recording' }))
  await screen.findByRole('button', { name: 'I spoke to Eric.' })
  fireEvent.click(screen.getByRole('button', { name: 'View original transcript' }))
  expect(screen.getByText('I spoke to Erc. Yes.')).toBeVisible()
  fireEvent.click(screen.getByRole('button', { name: /^Mark reviewed$/ }))
  await screen.findByText('Ready to process'); expect(processed).toBe(0)
  fireEvent.click(screen.getByRole('button', { name: 'Process reviewed transcript' }))
  await waitFor(() => expect(processed).toBe(1))
  expect(saved.original_segments[0].text).toBe('I spoke to Erc.')
})

it('keeps unsaved edits when staying and requires an explicit discard to close', async () => {
  await page.viewport(390, 844)
  openViewer()
  fireEvent.click(await screen.findByRole('button', { name: 'Edit transcript' }))
  fireEvent.change(screen.getByLabelText('Transcript turn 1'), { target: { value: 'Unsaved correction' } })
  fireEvent.click(screen.getByRole('button', { name: 'Close document' }))
  expect(await screen.findByRole('alertdialog', { name: 'Unsaved transcript changes' })).toBeVisible()
  fireEvent.click(screen.getByRole('button', { name: 'Stay' }))
  expect(screen.getByLabelText('Transcript turn 1')).toHaveValue('Unsaved correction')
  fireEvent.click(screen.getByRole('button', { name: 'Close document' }))
  fireEvent.click(screen.getByRole('button', { name: 'Discard unsaved edits' }))
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  expect(saved.segments[0].text).toBe('I spoke to Erc.')
})

it('permits read-only transcript access without edit, review or process controls', async () => {
  permissions.edit = false
  openViewer()
  await screen.findByRole('button', { name: 'I spoke to Erc.' })
  expect(screen.queryByRole('button', { name: 'Edit transcript' })).toBeNull()
  expect(screen.queryByRole('button', { name: 'Mark reviewed' })).toBeNull()
  expect(screen.queryByRole('button', { name: /Rename/ })).toBeNull()
})

it('keeps a long transcript bounded and navigates search to a distant editable turn', async () => {
  await page.viewport(1440, 900)
  const segments = Array.from({ length: 2000 }, (_, index) => ({ id: `turn-${index}`, speaker: index % 2 ? 'B' : 'A',
    start: index, end: index + 1, text: index === 1999 ? 'Distant searchable words' : `Synthetic turn ${index}` }))
  render(<div style={{ height: 800 }}><AudioTranscriptViewer segments={segments} onTurnTextChange={() => undefined} /></div>)
  await screen.findByLabelText('Transcript turn 1')
  expect(screen.getAllByRole('textbox', { name: /Transcript turn/ }).length).toBeLessThan(50)
  fireEvent.change(screen.getByLabelText('Search this transcript'), { target: { value: 'Distant searchable' } })
  fireEvent.click(screen.getByRole('button', { name: 'Next match' }))
  expect(await screen.findByLabelText('Transcript turn 2000')).toHaveValue('Distant searchable words')
  expect(screen.getAllByRole('textbox', { name: /Transcript turn/ }).length).toBeLessThan(50)
})
