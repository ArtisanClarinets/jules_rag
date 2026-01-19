'use client'

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getTenants } from '@/lib/api'
import api from '@/lib/api'

export default function TenantsPage() {
  const queryClient = useQueryClient()
  const [newTenantName, setNewTenantName] = useState('')

  const { data: tenants, isLoading } = useQuery({
    queryKey: ['tenants'],
    queryFn: getTenants
  })

  const createTenantMutation = useMutation({
    mutationFn: async (name: string) => {
        return api.post('/api/v1/tenants/', { name })
    },
    onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: ['tenants'] })
        setNewTenantName('')
    }
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (newTenantName) createTenantMutation.mutate(newTenantName)
  }

  return (
    <div className="space-y-6">
        <h1 className="text-3xl font-bold">Tenants</h1>

        <div className="bg-card p-4 rounded border">
            <h2 className="font-semibold mb-4">Create Tenant</h2>
            <form onSubmit={handleSubmit} className="flex gap-2">
                <input
                    className="border p-2 rounded flex-1"
                    placeholder="Tenant Name"
                    value={newTenantName}
                    onChange={e => setNewTenantName(e.target.value)}
                />
                <button
                    disabled={createTenantMutation.isPending}
                    className="bg-primary text-primary-foreground px-4 py-2 rounded"
                >
                    {createTenantMutation.isPending ? 'Creating...' : 'Create'}
                </button>
            </form>
        </div>

        <div className="grid gap-4">
            {isLoading ? <p>Loading...</p> : tenants?.map((t: any) => (
                <div key={t.id} className="border p-4 rounded flex justify-between items-center bg-card">
                    <div>
                        <h3 className="font-bold">{t.name}</h3>
                        <p className="text-sm text-muted-foreground">{t.id}</p>
                    </div>
                    <div className="text-sm text-muted-foreground">
                        {new Date(t.created_at).toLocaleDateString()}
                    </div>
                </div>
            ))}
        </div>
    </div>
  )
}
