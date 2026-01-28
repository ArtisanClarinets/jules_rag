import axios from 'axios'
import { z } from 'zod'

const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || '/api',
})

// Schemas
export const JobSchema = z.object({
  id: z.string(),
  source_id: z.string(),
  status: z.string(),
  created_at: z.string().optional().nullable(),
  started_at: z.string().optional().nullable(),
  completed_at: z.string().optional().nullable()
})

export const SearchResultSchema = z.object({
  results: z.array(z.any())
})

// Types
export type Job = z.infer<typeof JobSchema>
export type SearchResult = z.infer<typeof SearchResultSchema>

// Methods

export const search = async (query: string, collection_name: string, limit: number = 10, rerank: boolean = true) => {
    const res = await api.post('/api/v1/query/search', {
        query,
        collection_name,
        limit,
        rerank
    })
    return res.data
}

export const getTenants = async () => {
    const res = await api.get('/api/v1/tenants/')
    return res.data
}

export const createTenant = async (name: string) => {
    const res = await api.post('/api/v1/tenants/', { name })
    return res.data
}

export const ingestCode = async (repo_url: string, collection_name: string, source_id: string) => {
    const res = await api.post('/api/v1/ingest/code', {
        repo_url,
        collection_name,
        source_id
    })
    return res.data
}

export const ingestDoc = async (file_path: string, collection_name: string, source_id: string) => {
    const res = await api.post('/api/v1/ingest/doc', {
        file_path,
        collection_name,
        source_id
    })
    return res.data
}

export const uploadFile = async (formData: FormData) => {
    const res = await api.post('/api/v1/ingest/upload', formData, {
        headers: {
            'Content-Type': 'multipart/form-data'
        }
    })
    return res.data
}

export const getJobs = async () => {
    const res = await api.get('/api/v1/ingest/jobs')
    return res.data as Job[]
}

export const getSettings = async () => {
    const res = await api.get('/api/v1/settings/')
    return res.data
}

export const updateSettings = async (settings: Record<string, any>) => {
    const res = await api.post('/api/v1/settings/', { settings })
    return res.data
}

export default api
