'use client'
import { useState, useEffect } from 'react'
import api from '@/lib/api'

export default function SettingsPage() {
  const [heapSize, setHeapSize] = useState('512m')
  const [concurrency, setConcurrency] = useState(4)
  const [status, setStatus] = useState('')

  useEffect(() => {
      // Load settings
      api.get('/api/v1/settings/').then(res => {
          if (res.data.opensearch_heap) setHeapSize(res.data.opensearch_heap)
          if (res.data.worker_concurrency) setConcurrency(res.data.worker_concurrency)
      }).catch(console.error)
  }, [])

  const handleSave = async () => {
      setStatus('Saving...')
      try {
          await api.post('/api/v1/settings/', {
              settings: {
                  opensearch_heap: heapSize,
                  worker_concurrency: concurrency
              }
          })
          setStatus('Saved! Services restarting...')
      } catch (e) {
          setStatus('Error saving settings')
      }
  }

  return (
    <div className="space-y-6">
        <h1 className="text-3xl font-bold">System Settings</h1>

        <div className="bg-card p-6 rounded border space-y-6">
            <div>
                <h3 className="font-semibold mb-2">OpenSearch Configuration</h3>
                <div className="grid gap-4 max-w-md">
                    <div>
                        <label className="block text-sm font-medium mb-1">Heap Size</label>
                        <input
                            className="border p-2 rounded w-full"
                            value={heapSize}
                            onChange={e => setHeapSize(e.target.value)}
                        />
                    </div>
                </div>
            </div>

            <div className="border-t pt-6">
                <h3 className="font-semibold mb-2">Service Resources</h3>
                <div className="grid gap-4 max-w-md">
                    <div>
                        <label className="block text-sm font-medium mb-1">Worker Concurrency</label>
                        <input
                            type="number"
                            className="border p-2 rounded w-full"
                            value={concurrency}
                            onChange={e => setConcurrency(parseInt(e.target.value))}
                        />
                    </div>
                </div>
            </div>

             <div className="border-t pt-6">
                <button
                    onClick={handleSave}
                    className="bg-primary text-primary-foreground px-4 py-2 rounded"
                >
                    Save Changes & Restart Services
                </button>
                <p className="text-xs text-muted-foreground mt-2">
                    Warning: Applying changes will trigger a rolling restart of affected services.
                </p>
                {status && <p className="text-sm font-bold mt-2">{status}</p>}
            </div>
        </div>
    </div>
  )
}
