'use client'

import { useEffect, useState } from 'react'
import { KeyRound, RefreshCw } from 'lucide-react'
import { TokenStatus as TokenStatusData, fetchTokenStatus } from '../lib/api'

function formatDuration(seconds: number) {
  if (seconds <= 0) return 'Ready'
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = seconds % 60
  if (h) return `${h}h ${m}m`
  if (m) return `${m}m ${s}s`
  return `${s}s`
}

export default function TokenStatus() {
  const [tokens, setTokens] = useState<TokenStatusData[]>([])

  useEffect(() => {
    let mounted = true
    const load = () => fetchTokenStatus().then(d => {
      if (mounted) setTokens(d.tokens)
    }).catch(() => {})

    load()
    const id = window.setInterval(load, 1000)
    return () => {
      mounted = false
      window.clearInterval(id)
    }
  }, [])

  return (
    <div className="card tokenCard">
      <div className="cardTitle tokenTitle">
        <div>
          <p className="eyebrow">GITHUB API</p>
          <h2>Token usage</h2>
        </div>
        <div className="tokenHint"><RefreshCw size={14} /> Live</div>
      </div>

      {tokens.length ? (
        <div className="tokenTableWrap">
          <table className="tokenTable">
            <thead>
              <tr>
                <th>Token</th>
                <th>Hourly usage</th>
                <th>Remaining</th>
                <th>Cooldown / reset</th>
                <th>In flight</th>
              </tr>
            </thead>
            <tbody>
              {tokens.map(token => {
                const usage = token.usage_percent
                const busy = token.cooldown_active || token.invalid
                return (
                  <tr key={token.token_index}>
                    <td>
                      <div className="tokenName">
                        <KeyRound size={14} />
                        <span>{token.label}</span>
                        <code>{token.masked}</code>
                      </div>
                    </td>
                    <td>
                      <div className="tokenUsage">
                        <div className="miniTrack">
                          <i style={{ width: `${usage ?? 0}%` }} />
                        </div>
                        <span>{usage == null ? 'Waiting for response' : `${usage.toFixed(1)}%`}</span>
                      </div>
                    </td>
                    <td className="tokenRemaining">
                      {token.initialized ? `${token.remaining?.toLocaleString()} / ${token.limit?.toLocaleString()}` : '—'}
                    </td>
                    <td className={busy ? 'tokenCooldown' : ''}>
                      {token.invalid
                        ? 'Unauthorized'
                        : token.cooldown_active
                          ? `Cooldown ${formatDuration(token.cooldown_seconds)}`
                          : token.initialized
                            ? `Reset ${formatDuration(token.reset_seconds)}`
                            : 'Waiting for response'}
                    </td>
                    <td>{token.in_flight}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="empty tokenEmpty">No GitHub tokens configured.</div>
      )}

      <p className="tokenFootnote">
        Usage and reset times come from GitHub's live rate-limit response for each token.
        Cooldown appears only after GitHub reports throttling for that token.
      </p>
    </div>
  )
}
