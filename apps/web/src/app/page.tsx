'use client'
import Link from 'next/link'
import { useState } from 'react'
import { search } from '@/lib/api'

export default function Home() {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<any[]>([])

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      // Hardcoded collection for demo
      const res = await search(query, "test_collection")
      setResults(res.results)
    } catch (err) {
      console.error(err)
    }
  }

  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b px-6 py-4 flex items-center justify-between">
        <h1 className="text-xl font-bold">Vantus Vector Platform</h1>
        <nav className="space-x-4">
            <Link href="/" className="hover:underline">Search</Link>
            <Link href="/admin/tenants" className="hover:underline">Tenants</Link>
            <Link href="/admin/settings" className="hover:underline">Settings</Link>
        </nav>
      </header>

      <main className="flex-1 container mx-auto p-6">
        <div className="max-w-2xl mx-auto space-y-8">
            <div className="text-center space-y-4">
                <h2 className="text-3xl font-bold">Search Code & Docs</h2>
                <p className="text-muted-foreground">Hybrid retrieval with Qdrant + OpenSearch + Rerank</p>
            </div>

            <form onSubmit={handleSearch} className="flex gap-2">
                <input
                    type="text"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder="Enter query..."
                    className="flex-1 border p-2 rounded"
                />
                <button type="submit" className="bg-primary text-primary-foreground px-4 py-2 rounded">
                    Search
                </button>
            </form>

            <div className="space-y-4">
                {results.map((res: any, i) => (
                    <div key={i} className="border p-4 rounded shadow-sm">
                        <div className="flex justify-between items-start">
                            <h3 className="font-semibold text-lg">Result {i+1}</h3>
                            <span className="text-sm bg-secondary px-2 py-1 rounded">Score: {res.score.toFixed(3)}</span>
                        </div>
                        <pre className="mt-2 text-sm bg-muted p-2 rounded overflow-x-auto">
                            {res.content?.text || JSON.stringify(res.content, null, 2)}
                        </pre>
                    </div>
                ))}
            </div>
        </div>
      </main>
    </div>
  )
}
