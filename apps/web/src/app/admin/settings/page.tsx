'use client'
import { useState, useEffect } from 'react'
import api, { getSettings, updateSettings } from '@/lib/api'

export default function SettingsPage() {
  const [settings, setSettings] = useState<Record<string, any>>({})
  const [newKey, setNewKey] = useState('')
  const [newValue, setNewValue] = useState('')
  const [status, setStatus] = useState('')

  useEffect(() => {
      loadSettings()
  }, [])

  const loadSettings = () => {
      getSettings().then(res => setSettings(res)).catch(console.error)
  }

  const handleSave = async () => {
      setStatus('Saving...')
      try {
          await updateSettings(settings)
          setStatus('Saved! Services restarting...')
      } catch (e) {
          setStatus('Error saving settings')
      }
  }

  const handleUpdate = (key: string, value: string) => {
      setSettings(prev => ({ ...prev, [key]: value }))
  }

  const handleAdd = () => {
      if (newKey && newValue) {
          setSettings(prev => ({ ...prev, [newKey]: newValue }))
          setNewKey('')
          setNewValue('')
      }
  }

  return (
    <div className="space-y-6">
        <h1 className="text-3xl font-bold">System Settings</h1>

        <div className="bg-card p-6 rounded border space-y-6">
            <h3 className="font-semibold mb-2">Configuration</h3>

            <div className="overflow-x-auto">
                <table className="w-full text-sm text-left">
                    <thead className="bg-muted text-muted-foreground">
                        <tr>
                            <th className="p-2">Key</th>
                            <th className="p-2">Value</th>
                            <th className="p-2">Action</th>
                        </tr>
                    </thead>
                    <tbody>
                        {Object.entries(settings).map(([key, value]) => (
                            <tr key={key} className="border-b">
                                <td className="p-2 font-mono">{key}</td>
                                <td className="p-2">
                                    <input
                                        className="border p-1 rounded w-full"
                                        value={value as string}
                                        onChange={e => handleUpdate(key, e.target.value)}
                                    />
                                </td>
                                <td className="p-2">
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>

            <div className="border-t pt-4">
                <h4 className="font-medium mb-2">Add New Setting</h4>
                <div className="flex gap-2">
                    <input
                        className="border p-2 rounded flex-1"
                        placeholder="Key"
                        value={newKey}
                        onChange={e => setNewKey(e.target.value)}
                    />
                    <input
                        className="border p-2 rounded flex-1"
                        placeholder="Value"
                        value={newValue}
                        onChange={e => setNewValue(e.target.value)}
                    />
                    <button onClick={handleAdd} className="bg-secondary text-secondary-foreground px-4 py-2 rounded">Add</button>
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
