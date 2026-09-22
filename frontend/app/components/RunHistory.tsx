'use client'

import { useEffect, useState } from 'react'
import { Search, Download, FileText, ChevronDown, ChevronRight } from 'lucide-react'
import { HistoryRecord, ExportEntry, fetchHistory, fetchExports, downloadUrl } from '../lib/api'

type Props = {
  refreshKey: number
}

export default function RunHistory({ refreshKey }: Props) {
  const [tab, setTab] = useState<'history' | 'exports'>('history')
  const [records, setRecords] = useState<HistoryRecord[]>([])
  const [total, setTotal] = useState(0)
  const [exports, setExports] = useState<ExportEntry[]>([])
  const [query, setQuery] = useState('')
  const [expanded, setExpanded] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (tab === 'history') {
      setLoading(true)
      fetchHistory(20, 0, query)
        .then(d => {
          setRecords(d.records)
          setTotal(d.total)
        })
        .catch(() => {})
        .finally(() => setLoading(false))
    } else {
      fetchExports()
        .then(d => setExports(d.exports))
        .catch(() => {})
    }
  }, [tab, query, refreshKey])

  const grouped = exports.reduce<Record<string, ExportEntry[]>>((acc, e) => {
    const parts = e.path.split('/')
    const folderKey = parts.slice(0, -1).join('/')
    if (!acc[folderKey]) acc[folderKey] = []
    acc[folderKey].push(e)
    return acc
  }, {})

  return (
    <div className="card historyCard">
      <div className="cardTitle">
        <div>
          <p className="eyebrow">DATA ARCHIVE</p>
          <h2>History &amp; exports</h2>
        </div>
        <div className="tabToggle">
          <button
            className={tab === 'history' ? 'tabActive' : ''}
            onClick={() => setTab('history')}
          >
            History ({total})
          </button>
          <button
            className={tab === 'exports' ? 'tabActive' : ''}
            onClick={() => setTab('exports')}
          >
            Exports ({exports.length})
          </button>
        </div>
      </div>

      {tab === 'history' && (
        <>
          <div className="searchBox">
            <Search size={15} />
            <input
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder="Search by username or email…"
            />
          </div>
          <div className="tableWrap historyTable">
            <table>
              <thead>
                <tr>
                  <th>Username</th>
                  <th>Email</th>
                  <th>Created</th>
                  <th>First Commit</th>
                  <th>Gap</th>
                  <th>Date</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td colSpan={6} className="empty">Loading…</td>
                  </tr>
                ) : records.length ? (
                  records.map((r, i) => {
                    const created = Number(r.account_creation_year) || 0
                    const first = Number(r.first_commit_year) || 0
                    const gap = created - first
                    return (
                      <tr key={`${r.username}-${i}`}>
                        <td>
                          <a
                            href={`https://github.com/${r.github_username || r.username}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="ghLink"
                          >
                            {r.username}
                          </a>
                        </td>
                        <td>{r.email}</td>
                        <td>{created || '—'}</td>
                        <td>{first || '—'}</td>
                        <td className={gap < 0 ? 'gapNeg' : 'gapPos'}>
                          {gap > 0 ? `+${gap}` : gap}
                        </td>
                        <td className="mutedCell">
                          {r.scraped_at ? new Date(r.scraped_at).toLocaleDateString() : '—'}
                        </td>
                      </tr>
                    )
                  })
                ) : (
                  <tr>
                    <td colSpan={6} className="empty">No records yet.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}

      {tab === 'exports' && (
        <div className="exportsList">
          {exports.length === 0 && <div className="empty">No export files yet.</div>}
          {Object.entries(grouped).map(([folder, files]) => (
            <div key={folder} className="exportGroup">
              <button
                className="exportFolderHeader"
                onClick={() => setExpanded(expanded === folder ? null : folder)}
              >
                {expanded === folder ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                <FileText size={15} />
                <span>{folder.split('/').slice(-2).join(' / ')}</span>
                <span className="folderCount">{files.length} file{files.length !== 1 ? 's' : ''}</span>
              </button>
              {expanded === folder && (
                <div className="exportFiles">
                  {files.map(f => (
                    <a
                      key={f.path}
                      className="exportFile"
                      href={downloadUrl(f.path)}
                    >
                      <Download size={14} />
                      <span>{f.name}</span>
                      <span className="fileSize">{(f.size_bytes / 1024).toFixed(1)} KB</span>
                    </a>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
