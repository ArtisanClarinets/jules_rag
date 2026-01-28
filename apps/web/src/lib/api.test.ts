import { describe, it, expect, vi, afterEach } from 'vitest'
import * as apiModule from './api'
import { JobSchema } from './api'

const api = apiModule.default

describe('API Client', () => {
    afterEach(() => {
        vi.restoreAllMocks()
    })

    it('search calls correct endpoint', async () => {
        const postSpy = vi.spyOn(api, 'post').mockResolvedValue({ data: { results: [] } })
        await apiModule.search('test', 'col', 5, false)
        expect(postSpy).toHaveBeenCalledWith('/api/v1/query/search', {
            query: 'test',
            collection_name: 'col',
            limit: 5,
            rerank: false
        })
    })

    it('ingestCode calls correct endpoint', async () => {
        const postSpy = vi.spyOn(api, 'post').mockResolvedValue({ data: { status: 'queued' } })
        await apiModule.ingestCode('http://repo', 'col', 'src')
        expect(postSpy).toHaveBeenCalledWith('/api/v1/ingest/code', {
            repo_url: 'http://repo',
            collection_name: 'col',
            source_id: 'src'
        })
    })

    it('JobSchema validates correct job', () => {
        const validJob = {
            id: '123',
            source_id: 'src',
            status: 'pending',
            created_at: null,
            started_at: null,
            completed_at: null
        }
        expect(JobSchema.parse(validJob)).toEqual(validJob)
    })
})
