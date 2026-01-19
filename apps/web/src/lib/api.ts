import axios from 'axios'

const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || '/api',
})

export const search = async (query: string, collection_name: string) => {
    const res = await api.post('/api/v1/query/search', {
        query,
        collection_name,
        limit: 10,
        rerank: true
    })
    return res.data
}

export const getTenants = async () => {
    const res = await api.get('/api/v1/tenants/')
    return res.data
}

export default api
