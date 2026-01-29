'use client'
import { useState, useEffect } from 'react'
import api, { ingestCode, ingestDoc, uploadFile, getJobs, Job } from '@/lib/api'
import { useQuery } from '@tanstack/react-query'

export default function IngestionPage() {
  // Code Ingestion State
  const [repoUrl, setRepoUrl] = useState('')
  const [codeCollection, setCodeCollection] = useState('test_collection')
  const [codeSourceId, setCodeSourceId] = useState('default_source')
  const [codeStatus, setCodeStatus] = useState('')

  // Doc Ingestion State
  const [file, setFile] = useState<File | null>(null)
  const [docCollection, setDocCollection] = useState('test_collection')
  const [docSourceId, setDocSourceId] = useState('default_doc_source')
  const [docStatus, setDocStatus] = useState('')

  // Jobs Query
  const { data: jobs, refetch: refetchJobs } = useQuery({
    queryKey: ['jobs'],
    queryFn: getJobs,
    refetchInterval: 5000 // Poll every 5s
  })

  const handleIngestCode = async () => {
    try {
        setCodeStatus('Starting ingestion...')
        await ingestCode(repoUrl, codeCollection, codeSourceId)
        setCodeStatus('Ingestion queued!')
        setRepoUrl('')
        refetchJobs()
    } catch (e) {
        setCodeStatus('Error starting ingestion')
        console.error(e)
    }
  }

  const handleIngestDoc = async () => {
    if (!file) return
    try {
        setDocStatus('Uploading...')
        const formData = new FormData()
        formData.append('file', file)
        const uploadRes = await uploadFile(formData)
        const filePath = uploadRes.file_path

        setDocStatus('Ingesting...')
        await ingestDoc(filePath, docCollection, docSourceId)
        setDocStatus('Ingestion queued!')
        setFile(null)
        refetchJobs()
    } catch (e) {
        setDocStatus('Error uploading/ingesting')
        console.error(e)
    }
  }

  return (
    <div className="space-y-6">
        <h1 className="text-3xl font-bold">Ingestion</h1>

        <div className="grid md:grid-cols-2 gap-6">
            <div className="bg-card p-6 rounded border space-y-4">
                <h2 className="font-semibold text-xl">Code Ingestion</h2>
                <p className="text-sm text-muted-foreground">Clone and index a Git repository.</p>

                <div className="space-y-2">
                    <label className="text-sm font-medium">Repository URL</label>
                    <input
                        className="border p-2 rounded w-full"
                        placeholder="https://github.com/..."
                        value={repoUrl}
                        onChange={e => setRepoUrl(e.target.value)}
                    />
                </div>
                <div className="grid grid-cols-2 gap-2">
                     <div className="space-y-2">
                        <label className="text-sm font-medium">Collection</label>
                        <input
                            className="border p-2 rounded w-full"
                            value={codeCollection}
                            onChange={e => setCodeCollection(e.target.value)}
                        />
                    </div>
                    <div className="space-y-2">
                        <label className="text-sm font-medium">Source ID</label>
                        <input
                            className="border p-2 rounded w-full"
                            value={codeSourceId}
                            onChange={e => setCodeSourceId(e.target.value)}
                        />
                    </div>
                </div>

                 <button
                    onClick={handleIngestCode}
                    disabled={!repoUrl}
                    data-testid="start-ingestion-btn"
                    className="bg-primary text-primary-foreground px-4 py-2 rounded w-full disabled:opacity-50"
                >
                    Start Ingestion
                </button>
                {codeStatus && <p className="text-sm text-muted-foreground">{codeStatus}</p>}
            </div>

            <div className="bg-card p-6 rounded border space-y-4">
                <h2 className="font-semibold text-xl">Document Ingestion</h2>
                <p className="text-sm text-muted-foreground">Upload PDFs or add URLs.</p>

                 <div className="space-y-2">
                    <label className="text-sm font-medium">File (PDF)</label>
                    <input
                        type="file"
                        accept=".pdf"
                        className="border p-2 rounded w-full"
                        onChange={e => setFile(e.target.files?.[0] || null)}
                    />
                </div>
                <div className="grid grid-cols-2 gap-2">
                     <div className="space-y-2">
                        <label className="text-sm font-medium">Collection</label>
                        <input
                            className="border p-2 rounded w-full"
                            value={docCollection}
                            onChange={e => setDocCollection(e.target.value)}
                        />
                    </div>
                    <div className="space-y-2">
                        <label className="text-sm font-medium">Source ID</label>
                        <input
                            className="border p-2 rounded w-full"
                            value={docSourceId}
                            onChange={e => setDocSourceId(e.target.value)}
                        />
                    </div>
                </div>

                 <button
                    onClick={handleIngestDoc}
                    disabled={!file}
                    className="bg-secondary text-secondary-foreground px-4 py-2 rounded w-full disabled:opacity-50"
                >
                    Upload & Ingest
                </button>
                {docStatus && <p className="text-sm text-muted-foreground">{docStatus}</p>}
            </div>
        </div>

        <div className="bg-card p-6 rounded border space-y-4">
             <div className="flex justify-between items-center">
                <h2 className="font-semibold text-xl">Recent Jobs</h2>
                <button onClick={() => refetchJobs()} className="text-sm text-blue-500 hover:underline">Refresh</button>
             </div>
             <div className="overflow-auto">
                <table className="w-full text-sm text-left">
                    <thead className="bg-muted text-muted-foreground">
                        <tr>
                            <th className="p-2">ID</th>
                            <th className="p-2">Source</th>
                            <th className="p-2">Status</th>
                            <th className="p-2">Created</th>
                            <th className="p-2">Completed</th>
                        </tr>
                    </thead>
                    <tbody>
                        {jobs?.map((job) => (
                            <tr key={job.id} className="border-b">
                                <td className="p-2 font-mono text-xs">{job.id.slice(0, 8)}...</td>
                                <td className="p-2">{job.source_id}</td>
                                <td className="p-2">
                                    <span className={`px-2 py-1 rounded text-xs ${
                                        job.status === 'completed' ? 'bg-green-100 text-green-800' :
                                        job.status === 'failed' ? 'bg-red-100 text-red-800' :
                                        job.status === 'running' ? 'bg-blue-100 text-blue-800' :
                                        'bg-gray-100 text-gray-800'
                                    }`}>
                                        {job.status}
                                    </span>
                                </td>
                                <td className="p-2">{job.created_at ? new Date(job.created_at).toLocaleString() : '-'}</td>
                                <td className="p-2">{job.completed_at ? new Date(job.completed_at).toLocaleString() : '-'}</td>
                            </tr>
                        ))}
                        {!jobs?.length && (
                            <tr><td colSpan={5} className="p-4 text-center text-muted-foreground">No jobs found</td></tr>
                        )}
                    </tbody>
                </table>
             </div>
        </div>
    </div>
  )
}
