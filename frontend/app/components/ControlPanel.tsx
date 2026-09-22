'use client'

import { useState } from 'react'
import { Play, CircleStop, Search } from 'lucide-react'
import { RunForm, startRun, cancelRun } from '../lib/api'

type Props = {
  busy: boolean
  onStarted: () => void
  onProgressUpdate: () => void
}

const defaults: RunForm = {
  location: '',
  min_repos: 0,
  max_repos: 100,
  target_count: 50,
  start_year: 2008,
  end_year: new Date().getFullYear(),
  strict_quality_gmail: true,
  max_scanned_users: 200,
}

export default function ControlPanel({ busy, onStarted, onProgressUpdate }: Props) {
  const [form, setForm] = useState<RunForm>(defaults)
  const [error, setError] = useState('')

  const set = <K extends keyof RunForm>(key: K, value: RunForm[K]) =>
    setForm(prev => ({ ...prev, [key]: value }))

  const handleStart = async () => {
    setError('')
    if (!form.location.trim()) return setError('Enter a GitHub location first.')
    if (form.max_repos < form.min_repos)
      return setError('Maximum repositories must be greater than or equal to minimum.')
    if (form.end_year < form.start_year)
      return setError('End year must be greater than or equal to start year.')
    onStarted()
    try {
      await startRun(form)
      onProgressUpdate()
    } catch (e: any) {
      setError(e.message || 'Could not start run')
    }
  }

  const handleCancel = async () => {
    await cancelRun().catch(() => {})
    onProgressUpdate()
  }

  return (
    <div className="card configCard">
      <div className="cardTitle">
        <div>
          <p className="eyebrow">NEW RUN</p>
          <h2>Scrape configuration</h2>
        </div>
        <Search size={19} />
      </div>
      <div className="formGrid">
        <label className="wide">
          Location
          <input
            value={form.location}
            onChange={e => set('location', e.target.value)}
            placeholder="e.g. Japan, Tokyo, Brazil"
          />
        </label>
        <label>
          Min repositories
          <input type="number" min={0} value={form.min_repos} onChange={e => set('min_repos', +e.target.value)} />
        </label>
        <label>
          Max repositories
          <input type="number" min={0} value={form.max_repos} onChange={e => set('max_repos', +e.target.value)} />
        </label>
        <label>
          Target Gmail accounts
          <input type="number" min={1} value={form.target_count} onChange={e => set('target_count', +e.target.value)} />
        </label>
        <label>
          Account years from
          <input type="number" min={2008} value={form.start_year} onChange={e => set('start_year', +e.target.value)} />
        </label>
        <label>
          Account years to
          <input type="number" min={2008} value={form.end_year} onChange={e => set('end_year', +e.target.value)} />
        </label>
        <label className="wide">
          Max users to scan
          <input type="number" min={1} value={form.max_scanned_users} onChange={e => set('max_scanned_users', +e.target.value)} />
        </label>
      </div>
      <label className="check">
        <input
          type="checkbox"
          checked={form.strict_quality_gmail}
          onChange={e => set('strict_quality_gmail', e.target.checked)}
        />
        <span>Exclude role-style Gmail addresses</span>
      </label>
      {error && <div className="error">{error}</div>}
      <div className="actions">
        <button className="primary" disabled={busy} onClick={handleStart}>
          <Play size={17} />
          {busy ? 'Scraping…' : 'Start scrape'}
        </button>
        {busy && (
          <button className="secondary" onClick={handleCancel}>
            <CircleStop size={17} />
            Stop
          </button>
        )}
      </div>
      <p className="hint">
        Year rule: <b>creation year − first observable commit year &lt; 4</b>. Same year and later first commit years pass.
      </p>
    </div>
  )
}

}