'use client'
import Link from 'next/link'
import { useState } from 'react'
import { search } from '@/lib/api'

export default function Home() {
  const [query, setQuery] = useState('')
  const [collection, setCollection] = useState('test_collection')
  const [limit, setLimit] = useState(10)
  const [rerank, setRerank] = useState(true)
  const [results, setResults] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      const res = await search(query, collection, limit, rerank)
      setResults(res.results)
    } catch (err) {
      console.error(err)
      setError('Search failed')
    } finally {
        setLoading(false)
    }
  }

  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b px-6 py-4 flex items-center justify-between">
        <h1 className="text-xl font-bold">Vantus Vector Platform</h1>
        <nav className="space-x-4">
            <Link href="/" className="hover:underline font-bold">Search</Link>
            <Link href="/admin/ingestion" className="hover:underline">Ingestion</Link>
            <Link href="/admin/tenants" className="hover:underline">Tenants</Link>
            <Link href="/admin/settings" className="hover:underline">Settings</Link>
        </nav>
      </header>

      <main className="flex-1 container mx-auto p-6">
        <div className="max-w-4xl mx-auto space-y-8">
            <div className="text-center space-y-4">
                <h2 className="text-3xl font-bold">Search Code & Docs</h2>
                <p className="text-muted-foreground">Hybrid retrieval with Qdrant + OpenSearch + Rerank</p>
            </div>

            <form onSubmit={handleSearch} className="space-y-4 bg-card p-6 rounded border shadow-sm">
                <div className="flex gap-2">
                    <input
                        type="text"
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                        placeholder="Enter query..."
                        className="flex-1 border p-2 rounded"
                    />
                    <button type="submit" disabled={loading} className="bg-primary text-primary-foreground px-4 py-2 rounded">
                        {loading ? 'Searching...' : 'Search'}
                    </button>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
                    <div className="flex flex-col gap-1">
                        <label className="font-medium">Collection</label>
                        <input
                            className="border p-1.5 rounded"
                            value={collection}
                            onChange={e => setCollection(e.target.value)}
                        />
                    </div>
                    <div className="flex flex-col gap-1">
                        <label className="font-medium">Limit</label>
                        <input
                            type="number"
                            className="border p-1.5 rounded"
                            value={limit}
                            onChange={e => setLimit(parseInt(e.target.value))}
                            min={1} max={100}
                        />
                    </div>
                     <div className="flex items-center gap-2 pt-6">
                        <input
                            type="checkbox"
                            id="rerank"
                            checked={rerank}
                            onChange={e => setRerank(e.target.checked)}
                        />
                        <label htmlFor="rerank" className="font-medium">Enable Rerank</label>
                    </div>
                </div>
            </form>

            {error && <p className="text-red-500 text-center">{error}</p>}

            <div className="space-y-4">
                {results.map((res: any, i) => (
                    <div key={i} className="border p-4 rounded shadow-sm bg-white hover:shadow-md transition">
                        <div className="flex justify-between items-start">
                            <h3 className="font-semibold text-lg text-blue-600">Result {i+1}</h3>
                            <span className="text-xs bg-secondary px-2 py-1 rounded">Score: {res.score?.toFixed(3)}</span>
                        </div>
                        <div className="mt-2 text-xs text-muted-foreground flex gap-2">
                            <span>Source: {res.payload?.source_id || 'N/A'}</span>
                            <span>Collection: {collection}</span>
                        </div>
                        <pre className="mt-2 text-sm bg-muted p-2 rounded overflow-x-auto whitespace-pre-wrap">
                            {res.content?.text || res.payload?.text || JSON.stringify(res, null, 2)}
                        </pre>
                    </div>
                ))}
            </div>
        </div>
      </main>
    </div>
  )
}
