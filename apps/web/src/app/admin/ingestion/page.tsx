'use client'
import { useState } from 'react'
import api from '@/lib/api'

export default function IngestionPage() {
  const [repoUrl, setRepoUrl] = useState('')
  const [status, setStatus] = useState('')

  const handleIngestCode = async () => {
    try {
        setStatus('Starting ingestion...')
        await api.post('/api/v1/ingest/code', {
            repo_url: repoUrl,
            collection_name: 'test_collection'
        })
        setStatus('Ingestion started!')
        setRepoUrl('')
    } catch (e) {
        setStatus('Error starting ingestion')
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
                 <button
                    onClick={handleIngestCode}
                    disabled={!repoUrl}
                    className="bg-primary text-primary-foreground px-4 py-2 rounded w-full disabled:opacity-50"
                >
                    Start Ingestion
                </button>
                {status && <p className="text-sm text-muted-foreground">{status}</p>}
            </div>

            <div className="bg-card p-6 rounded border space-y-4">
                <h2 className="font-semibold text-xl">Document Ingestion</h2>
                <p className="text-sm text-muted-foreground">Upload PDFs or add URLs.</p>

                <div className="border-2 border-dashed p-8 rounded text-center text-muted-foreground">
                    Drag and drop PDFs here
                </div>
                 <button className="bg-secondary text-secondary-foreground px-4 py-2 rounded w-full">
                    Upload
                </button>
            </div>
        </div>
    </div>
  )
}
