'use client'

import { useEffect, useMemo, useState } from 'react'
import { Activity, CheckCircle2, CircleStop, Database, Download, Github, Mail, Play, Search, ShieldAlert, Users } from 'lucide-react'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
const WS = API.replace(/^http/, 'ws')

type Progress = {
  status: string
  run_id?: string
  location?: string
  target: number
  extracted: number
  skipped: number
  skipped_no_email: number
  skipped_not_gmail: number
  skipped_year_mismatch: number
  skipped_duplicate: number
  skipped_repo_range: number
  errors: number
  scanned_users: number
  progress_percent: number
  current_username?: string | null
  current_stage?: string
  elapsed_seconds: number
  run_csv?: string | null
  recent: Array<{ login: string; email: string; account_creation_year: number; first_commit_year: number; difference: number }>
}

const empty: Progress = {
  status: 'idle', target: 0, extracted: 0, skipped: 0, skipped_no_email: 0,
  skipped_not_gmail: 0, skipped_year_mismatch: 0, skipped_duplicate: 0,
  skipped_repo_range: 0, errors: 0, scanned_users: 0, progress_percent: 0,
  elapsed_seconds: 0, recent: []
}

export default function Home() {
  const [form, setForm] = useState({ location: '', min_repos: 0, max_repos: 100, target_count: 50, start_year: 2008, end_year: new Date().getFullYear(), strict_quality_gmail: true })
  const [progress, setProgress] = useState<Progress>(empty)
  const [busy, setBusy] = useState(false)
  const [historical, setHistorical] = useState(0)
  const [error, setError] = useState('')

  useEffect(() => {
    let socket: WebSocket | null = null
    const poll = async () => {
      try {
        const r = await fetch(`${API}/api/runs/current`, { cache: 'no-store' })
        if (r.ok) {
          const p = await r.json()
          setProgress(p)
          setBusy(['running'].includes(p.status))
        }
      } catch {}
    }
    poll()
    try {
      socket = new WebSocket(`${WS}/ws`)
      socket.onmessage = e => {
        const p = JSON.parse(e.data)
        setProgress(p)
        setBusy(p.status === 'running')
      }
    } catch {}
    const timer = setInterval(poll, 1500)
    return () => { clearInterval(timer); socket?.close() }
  }, [])

  useEffect(() => {
    fetch(`${API}/api/stats`).then(r => r.json()).then(d => setHistorical(d.historical_records || 0)).catch(() => {})
  }, [progress.extracted, progress.status])

  const start = async () => {
    setError('')
    if (!form.location.trim()) return setError('Enter a GitHub location first.')
    if (form.max_repos < form.min_repos) return setError('Maximum repositories must be greater than or equal to minimum.')
    setBusy(true)
    try {
      const r = await fetch(`${API}/api/runs`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(form) })
      const body = await r.json()
      if (!r.ok) throw new Error(body.detail || 'Could not start run')
    } catch (e: any) {
      setBusy(false)
      setError(e.message || 'Could not start run')
    }
  }

  const cancel = async () => { await fetch(`${API}/api/runs/cancel`, { method: 'POST' }).catch(() => {}) }
  const pct = Math.min(100, progress.progress_percent || 0)
  const rate = progress.elapsed_seconds ? (progress.scanned_users / progress.elapsed_seconds).toFixed(1) : '0.0'
  const runFile = progress.run_csv ? `${API}/api/runs/file?path=${encodeURIComponent(progress.run_csv)}` : '#'

  return (
    <main className="shell">
      <header className="topbar">
        <div className="brand"><div className="brandMark"><Github size={20}/></div><div><strong>GitMail</strong><span>production scraper</span></div></div>
        <div className={`statusPill ${progress.status === 'running' ? 'live' : ''}`}><span className="dot"/> {progress.status || 'idle'}</div>
      </header>

      <section className="hero"><div><p className="eyebrow">CONTROL CENTER</p><h1>Find profile-visible Gmail accounts.</h1><p className="sub">Configure a run, watch every filtering stage live, and keep a permanent deduplicated history.</p></div><div className="heroIcon"><Activity size={30}/></div></section>

      <section className="grid mainGrid">
        <div className="card configCard">
          <div className="cardTitle"><div><p className="eyebrow">NEW RUN</p><h2>Scrape configuration</h2></div><Search size={19}/></div>
          <div className="formGrid">
            <label className="wide">Location<input value={form.location} onChange={e=>setForm({...form, location:e.target.value})} placeholder="e.g. Japan, Tokyo, Brazil" /></label>
            <label>Min repositories<input type="number" min="0" value={form.min_repos} onChange={e=>setForm({...form,min_repos:+e.target.value})}/></label>
            <label>Max repositories<input type="number" min="0" value={form.max_repos} onChange={e=>setForm({...form,max_repos:+e.target.value})}/></label>
            <label>Target Gmail accounts<input type="number" min="1" value={form.target_count} onChange={e=>setForm({...form,target_count:+e.target.value})}/></label>
            <label>Account years from<input type="number" min="2008" value={form.start_year} onChange={e=>setForm({...form,start_year:+e.target.value})}/></label>
            <label>Account years to<input type="number" min="2008" value={form.end_year} onChange={e=>setForm({...form,end_year:+e.target.value})}/></label>
          </div>
          <label className="check"><input type="checkbox" checked={form.strict_quality_gmail} onChange={e=>setForm({...form,strict_quality_gmail:e.target.checked})}/><span>Exclude role-style Gmail addresses</span></label>
          {error && <div className="error">{error}</div>}
          <div className="actions"><button className="primary" disabled={busy} onClick={start}><Play size={17}/>{busy ? 'Scraping…' : 'Start scrape'}</button>{busy && <button className="secondary" onClick={cancel}><CircleStop size={17}/>Stop</button>}</div>
          <p className="hint">Year rule: <b>creation year − first observable commit year &lt; 4</b>. Same year and later first commit years pass.</p>
        </div>

        <div className="card runCard">
          <div className="cardTitle"><div><p className="eyebrow">CURRENT RUN</p><h2>{progress.location || 'Ready to scrape'}</h2></div><div className="bigNumber">{progress.extracted}<small>/{progress.target || 0}</small></div></div>
          <div className="progressTrack"><div style={{width:`${pct}%`}}/></div><div className="progressMeta"><span>{pct.toFixed(0)}% target reached</span><span>{rate} users/sec</span></div>
          <div className="metricGrid"><Metric icon={<Users/>} label="Scanned" value={progress.scanned_users}/><Metric icon={<Mail/>} label="Accepted" value={progress.extracted}/><Metric icon={<ShieldAlert/>} label="Skipped" value={progress.skipped}/><Metric icon={<Database/>} label="History" value={historical}/></div>
          <div className="stage"><span className="dot liveDot"/> {progress.current_stage || 'idle'} {progress.current_username && <b>· {progress.current_username}</b>}<span className="stageTime">{progress.elapsed_seconds?.toFixed(1)}s</span></div>
          {progress.run_csv && progress.status !== 'running' && <a className="download" href={runFile}><Download size={16}/> Download this run CSV</a>}
        </div>
      </section>

      <section className="grid lowerGrid">
        <div className="card"><div className="cardTitle"><div><p className="eyebrow">FILTER BREAKDOWN</p><h2>Why users leave the pipeline</h2></div></div><div className="breakdown"><Bar label="No profile email" value={progress.skipped_no_email} total={Math.max(progress.skipped,1)}/><Bar label="Not Gmail / quality gate" value={progress.skipped_not_gmail} total={Math.max(progress.skipped,1)}/><Bar label="Year rule" value={progress.skipped_year_mismatch} total={Math.max(progress.skipped,1)}/><Bar label="Already collected" value={progress.skipped_duplicate} total={Math.max(progress.skipped,1)}/><Bar label="Repository range" value={progress.skipped_repo_range} total={Math.max(progress.skipped,1)}/></div></div>
        <div className="card"><div className="cardTitle"><div><p className="eyebrow">LIVE RESULTS</p><h2>Accepted accounts</h2></div><CheckCircle2 size={19}/></div>
          <div className="tableWrap">
            <table>
              <thead>
                <tr>
                  <th>GitHub</th>
                  <th>Email</th>
                  <th>Years</th>
                </tr>
              </thead>
              <tbody>
                {progress.recent?.length ? (
                  progress.recent.map((r, i) => (
                    <tr key={`${r.login}-${i}`}>
                      <td>{r.login}</td>
                      <td>{r.email}</td>
                      <td>
                        {r.account_creation_year} → {r.first_commit_year}
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={3} className="empty">
                      Accepted users will appear here.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </main>
  )
}

function Metric({icon,label,value}:{icon:React.ReactNode,label:string,value:number}) { return <div className="metric"><span>{icon}</span><div><b>{value}</b><small>{label}</small></div></div> }
function Bar({label,value,total}:{label:string,value:number,total:number}) { const width=Math.min(100,(value/total)*100); return <div className="barRow"><div><span>{label}</span><b>{value}</b></div><div className="miniTrack"><i style={{width:`${width}%`}}/></div></div> }
