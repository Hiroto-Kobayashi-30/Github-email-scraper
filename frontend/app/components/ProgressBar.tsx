'use client'

import { Activity, Users, Mail, ShieldAlert, Database, Download } from 'lucide-react'
import { Progress, runFileUrl } from '../lib/api'

type Props = {
  progress: Progress
  historical: number
}

export default function ProgressBar({ progress, historical }: Props) {
  const pct = Math.min(100, progress.progress_percent || 0)
  const rate = progress.elapsed_seconds
    ? (progress.scanned_users / progress.elapsed_seconds).toFixed(1)
    : '0.0'

  const stageLabels: Record<string, string> = {
    idle: 'Idle',
    repository_filter: 'Filtering repositories',
    profile_email: 'Extracting profile email',
    gmail_filter: 'Checking Gmail filter',
    first_commit_year: 'Finding first commit year',
    deduplication: 'Deduplicating',
    finished: 'Finished',
  }

  const stageLabel = stageLabels[progress.current_stage || 'idle'] || progress.current_stage || 'Idle'
  const runFile = progress.run_csv ? runFileUrl(progress.run_csv) : '#'

  return (
    <div className="card runCard">
      <div className="cardTitle">
        <div>
          <p className="eyebrow">CURRENT RUN</p>
          <h2>{progress.location || 'Ready to scrape'}</h2>
        </div>
        <div className="bigNumber">
          {progress.extracted}
          <small>/{progress.target || 0}</small>
        </div>
      </div>
      <div className="progressTrack">
        <div style={{ width: `${pct}%` }} />
      </div>
      <div className="progressMeta">
        <span>{pct.toFixed(0)}% target reached</span>
        <span>{rate} users/sec</span>
      </div>
      <div className="metricGrid">
        <Metric icon={<Users size={17} />} label="Scanned" value={progress.scanned_users} />
        <Metric icon={<Mail size={17} />} label="Accepted" value={progress.extracted} />
        <Metric icon={<ShieldAlert size={17} />} label="Skipped" value={progress.skipped} />
        <Metric icon={<Database size={17} />} label="History" value={historical} />
      </div>
      <div className="stage">
        <span className="dot liveDot" /> {stageLabel}
        {progress.current_username && <b> · {progress.current_username}</b>}
        <span className="stageTime">{progress.elapsed_seconds?.toFixed(1)}s</span>
      </div>
      {progress.last_error && progress.status !== 'running' && (
        <div className="error" style={{ marginTop: '10px' }}>{progress.last_error}</div>
      )}
      {progress.run_csv && progress.status !== 'running' && (
        <a className="download" href={runFile}>
          <Download size={16} /> Download this run CSV
        </a>
      )}
    </div>
  )
}

function Metric({ icon, label, value }: { icon: React.ReactNode; label: string; value: number }) {
  return (
    <div className="metric">
      <span>{icon}</span>
      <div>
        <b>{value}</b>
        <small>{label}</small>
      </div>
    </div>
  )
}
