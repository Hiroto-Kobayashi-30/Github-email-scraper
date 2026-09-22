'use client'

import { CircleCheck as CheckCircle2 } from 'lucide-react'
import { Progress } from '../lib/api'

type Props = {
  progress: Progress
}

export default function LiveResults({ progress }: Props) {
  const breakdown = [
    { label: 'No profile email', value: progress.skipped_no_email },
    { label: 'Not Gmail / quality gate', value: progress.skipped_not_gmail },
    { label: 'Year rule', value: progress.skipped_year_mismatch },
    { label: 'Already collected', value: progress.skipped_duplicate },
    { label: 'Repository range', value: progress.skipped_repo_range },
  ]
  const total = Math.max(progress.skipped, 1)

  return (
    <div className="card">
      <div className="cardTitle">
        <div>
          <p className="eyebrow">LIVE RESULTS</p>
          <h2>Accepted accounts</h2>
        </div>
        <CheckCircle2 size={19} />
      </div>
      <div className="tableWrap">
        <table>
          <thead>
            <tr>
              <th>GitHub</th>
              <th>Email</th>
              <th>Created → First Commit</th>
              <th>Gap</th>
            </tr>
          </thead>
          <tbody>
            {progress.recent?.length ? (
              progress.recent.map((r, i) => (
                <tr key={`${r.login}-${i}`}>
                  <td>
                    <a
                      href={`https://github.com/${r.login}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="ghLink"
                    >
                      {r.login}
                    </a>
                  </td>
                  <td>{r.email}</td>
                  <td>
                    {r.account_creation_year} → {r.first_commit_year}
                  </td>
                  <td className={r.difference < 0 ? 'gapNeg' : 'gapPos'}>
                    {r.difference > 0 ? `+${r.difference}` : r.difference}
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={4} className="empty">
                  Accepted users will appear here.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
