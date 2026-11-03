import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { transcriptsAPI, type AudioMode, type ProcessingPlan } from '../transcripts.api'

export function AudioProcessingChoice({ plan, busy, onChoose, onCancel }: {
  plan: ProcessingPlan | null; busy: boolean; onChoose: (mode: AudioMode) => void; onCancel: () => void
}) {
  const [showFiles, setShowFiles] = useState(false)
  const [cursor, setCursor] = useState(0)
  const page = useQuery({ queryKey: ['processing-plan-files', plan?.id, cursor],
    queryFn: () => transcriptsAPI.files(plan!.id, cursor), enabled: showFiles && !!plan && plan.file_count > 100, retry: false })
  const files = plan && plan.file_count > 100 ? page.data?.items ?? [] : plan?.files ?? []
  return <Dialog open={!!plan} onOpenChange={open => { if (!open && !busy) onCancel() }}>
    <DialogContent className="max-w-xl">
      <DialogHeader>
        <DialogTitle>Process {plan?.eligible_count ?? 0} files</DialogTitle>
        <DialogDescription>{plan?.document_count ?? 0} documents follow their normal processing route.
          {' '}{plan?.audio_count ?? 0} audio {plan?.audio_count === 1 ? 'recording is' : 'recordings are'} selected. Choose how to handle the unreviewed recordings.</DialogDescription>
      </DialogHeader>
      <div className="grid gap-3">
        <Button className="h-auto justify-start whitespace-normal p-4 text-left" disabled={busy} onClick={() => onChoose('review_first')}>
          <span><strong className="block">Transcribe, then review</strong><span className="block text-xs font-normal">Save transcripts and stop before summaries and graph processing. Existing drafts are kept.</span></span>
        </Button>
        <Button variant="outline" className="h-auto justify-start whitespace-normal p-4 text-left" disabled={busy} onClick={() => onChoose('direct')}>
          <span><strong className="block">Process without review</strong><span className="block text-xs font-normal">Use the latest saved transcripts, transcribe where needed, and continue processing.</span></span>
        </Button>
      </div>
      {!!plan?.skipped_count && <p className="text-xs text-muted-foreground">{plan.skipped_count} already processed or active files will be skipped.</p>}
      <Button variant="ghost" size="sm" onClick={() => { setCursor(0); setShowFiles(v => !v) }}>View affected files</Button>
      {showFiles && <div>
        {page.isFetching && <p className="text-xs">Loading selected files…</p>}
        {page.error && <p role="alert" className="text-xs">Could not load the selected files. <button onClick={() => void page.refetch()}>Retry</button></p>}
        <ul className="max-h-40 overflow-auto text-xs">{files.map(file => <li key={file.id} className="py-1">{file.name}{file.reason ? ` — ${file.reason}` : ''}</li>)}</ul>
        {(plan?.file_count ?? 0) > 100 && <div className="flex items-center gap-2 text-xs">
          <Button size="sm" variant="ghost" disabled={!cursor || page.isFetching} onClick={() => setCursor(v => Math.max(0, v - 100))}>Previous files</Button>
          <span>{cursor + 1}–{Math.min(cursor + 100, plan!.file_count)} of {plan!.file_count}</span>
          <Button size="sm" variant="ghost" disabled={page.isFetching || page.data?.next_cursor == null} onClick={() => setCursor(page.data!.next_cursor!)}>Next files</Button>
        </div>}
      </div>}
      <DialogFooter><Button variant="ghost" disabled={busy} onClick={onCancel}>Cancel</Button></DialogFooter>
    </DialogContent>
  </Dialog>
}
