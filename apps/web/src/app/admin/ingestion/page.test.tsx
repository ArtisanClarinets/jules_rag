import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import { describe, it, expect, vi, afterEach } from 'vitest'
import '@testing-library/jest-dom'
import IngestionPage from './page'
import * as apiModule from '@/lib/api'

// Mock useQuery
vi.mock('@tanstack/react-query', () => ({
    useQuery: () => ({
        data: [],
        refetch: vi.fn()
    })
}))

// Mock API methods
vi.spyOn(apiModule, 'ingestCode').mockResolvedValue({})
vi.spyOn(apiModule, 'getJobs').mockResolvedValue([])

describe('IngestionPage', () => {
    afterEach(() => {
        cleanup()
    })

    it('renders code ingestion form', () => {
        render(<IngestionPage />)
        expect(screen.getByText('Code Ingestion')).toBeDefined()
        expect(screen.getByPlaceholderText('https://github.com/...')).toBeDefined()
    })

    it('validates inputs', () => {
        render(<IngestionPage />)
        const button = screen.getByTestId('start-ingestion-btn')
        expect(button).toBeDisabled()

        const input = screen.getByPlaceholderText('https://github.com/...')
        fireEvent.change(input, { target: { value: 'http://foo' } })
        expect(button).not.toBeDisabled()
    })
})
