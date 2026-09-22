'use client'

import { useEffect, useState, useCallback } from 'react'
import { GitFork as Github } from 'lucide-react'
import { Progress, fetchStats } from './lib/api'
import { useLiveProgress } from './lib/ws'
import ControlPanel from './components/ControlPanel'
import ProgressBar from './components/ProgressBar'
import LiveResults from './components/LiveResults'
import RunHistory from './components/RunHistory'
import TokenStatus from './components/TokenStatus'

const empty: Progress = {
  status: 'idle', target: 0, extracted: 0, skipped: 0, skipped_no_email: 0,
  skipped_not_gmail: 0, skipped_year_mismatch: 0, skipped_duplicate: 0,
  skipped_repo_range: 0, errors: 0, scanned_users: 0, progress_percent: 0,
  elapsed_seconds: 0, recent: []
}

export default function Home() {
  const [progress, setProgress] = useState<Progress>(empty)
  const [busy, setBusy] = useState(false)
  const [historical, setHistorical] = useState(0)
  const [historyRefresh, setHistoryRefresh] = useState(0)

  const handleUpdate = useCallback((p: Progress) => {
    setProgress(p)
    setBusy(p.status === 'running')
    if (p.status !== 'running' && p.extracted > 0) {
      setHistoryRefresh(r => r + 1)
    }
  }, [])

  useLiveProgress(handleUpdate)

  useEffect(() => {
    fetchStats()
      .then(d => setHistorical(d.historical_records || 0))
      .catch(() => {})
  }, [progress.extracted, progress.status])

  const handleStarted = useCallback(() => setBusy(true), [])
  const handleProgressUpdate = useCallback(() => {
    setHistoryRefresh(r => r + 1)
  }, [])

  return (
    <main className="shell">
      <header className="topbar">
        <div className="brand">
          <div className="brandMark"><Github size={20} /></div>
          <div><strong>GitMail</strong><span>production scraper</span></div>
        </div>
        <div className={`statusPill ${progress.status === 'running' ? 'live' : ''}`}>
          <span className="dot" /> {progress.status || 'idle'}
        </div>
      </header>

      <section className="hero">
        <div>
          <p className="eyebrow">CONTROL CENTER</p>
          <h1>Find profile-visible Gmail accounts.</h1>
          <p className="sub">
            Configure a run, watch every filtering stage live, and keep a permanent
            deduplicated history with downloadable per-run exports.
          </p>
        </div>
      </section>

      <section className="grid mainGrid">
        <ControlPanel
          busy={busy}
          onStarted={handleStarted}
          onProgressUpdate={handleProgressUpdate}
        />
        <ProgressBar progress={progress} historical={historical} />
      </section>

      <section className="tokenSection">
        <TokenStatus />
      </section>

      <section className="grid lowerGrid">
        <LiveResults progress={progress} />
        <RunHistory refreshKey={historyRefresh} />
      </section>
    </main>
  )
}
