import { useEffect, useMemo } from 'react'
import Uppy from '@uppy/core'
import Tus from '@uppy/tus'
import Dashboard from '@uppy/react/dashboard'
import '@uppy/core/css/style.min.css'
import '@uppy/dashboard/css/style.min.css'

/**
 * Resumable evidence uploader (tus). For large Cellebrite .zip archives that
 * the legacy single-POST path can't carry reliably (30GB+). Chunks the file,
 * survives network drops / page reloads (tus stores the upload URL), and on
 * completion tusd's post-finish hook auto-routes it into the Cellebrite
 * ingest pipeline — same as a normal upload. Endpoint /files is proxied to
 * tusd by Vite (same origin). See deploy/owl-tusd.service + tus-hooks/.
 */
export default function UppyEvidenceUploader({ caseId, owner, disabled }) {
  const uppy = useMemo(() => {
    const u = new Uppy({
      autoProceed: false,
      // Cellebrite exports are zipped; this widget is the large-archive path.
      restrictions: { allowedFileTypes: ['.zip', 'application/zip', 'application/x-zip-compressed'] },
      meta: { case_id: caseId || '', owner: owner || '' },
    })
    u.use(Tus, {
      endpoint: '/files',
      chunkSize: 50 * 1024 * 1024, // 50MB chunks -> tiny proxy footprint, fast resume
      retryDelays: [0, 1000, 3000, 5000, 10000, 30000],
      removeFingerprintOnSuccess: true,
      // authenticate each chunk the same way the API client does
      headers: () => ({ Authorization: `Bearer ${localStorage.getItem('authToken') || ''}` }),
    })
    return u
  }, []) // one Uppy instance for the component's lifetime

  // keep case/owner fresh, and give tusd the `filename` its hooks require
  useEffect(() => {
    uppy.setMeta({ case_id: caseId || '', owner: owner || '' })
  }, [uppy, caseId, owner])

  useEffect(() => {
    const onAdded = (file) =>
      uppy.setFileMeta(file.id, { filename: file.name, case_id: caseId || '', owner: owner || '' })
    uppy.on('file-added', onAdded)
    return () => uppy.off('file-added', onAdded)
  }, [uppy, caseId, owner])

  useEffect(() => () => { try { uppy.destroy() } catch { /* noop */ } }, [uppy])

  return (
    <div className="rounded-lg border border-light-300 bg-light-50 p-4">
      <div className="mb-2 flex items-center justify-between">
        <h4 className="text-sm font-semibold text-dark-800">Large file upload (resumable)</h4>
        <span className="text-xs text-light-700">For Cellebrite .zip archives — survives network drops</span>
      </div>
      <div className={disabled ? 'pointer-events-none opacity-50' : ''}>
        <Dashboard
          uppy={uppy}
          proudlyDisplayPoweredByUppy={false}
          showProgressDetails
          height={300}
          note="Drag a Cellebrite .zip here. Uploads in chunks; if the connection drops it resumes where it left off. Processing starts automatically when the upload finishes."
        />
      </div>
      {!caseId && (
        <p className="mt-2 text-xs text-red-600">Select a case before uploading.</p>
      )}
    </div>
  )
}
