import { useEffect, useState } from 'react'
import { getCompletionClosingMessage } from '../utils/conversationalHelpers'
import apiClient from '../api/client'
import {
  formatRatioPercent,
  formatRubricEntry,
} from '../utils/formatters'
import {
  formatDifficultyBadge,
  summarizeAdaptiveProgress,
  buildAdaptivePracticeUrl,
} from '../utils/adaptiveHelpers'

export default function FeedbackReport({ sessionId, navigate }) {
  const [report, setReport] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    apiClient
      .get(`/api/viva/sessions/${sessionId}/report`)
      .then(({ data }) => setReport(data))
      .catch((e) => setError(e.userMessage || 'The report is not available yet.'))
  }, [sessionId])

  if (error) {
    return (
      <main className="page-shell">
        <p className="error-text" role="alert">{error}</p>
        <button className="button secondary" onClick={() => navigate('/')}>Back to courses</button>
      </main>
    )
  }

  if (!report) {
    return (
      <main className="page-shell">
        <p className="muted">Preparing your feedback…</p>
      </main>
    )
  }

  const hasTotalScore = report.total_score !== null && report.total_score !== undefined
  const overallPercent = hasTotalScore ? Math.round(Number(report.total_score) * 100) : null
  const overallDisplay = hasTotalScore ? `${overallPercent}` : '—'
  const summaryStats = summarizeAdaptiveProgress(report.adaptive_summary)

  return (
    <main className="page-shell report-shell">
      <p className="eyebrow">SESSION COMPLETE</p>
      <h1>Your practice, reflected.</h1>
      <p className="muted" style={{ fontSize: '0.98rem', color: '#cbd5e1', marginBottom: '24px', lineHeight: 1.5 }}>
        {getCompletionClosingMessage(report.total_score, report.student_name, report.answers?.length)}
      </p>

      <section className="score-hero">
        <div>
          <span className="eyebrow">OVERALL SCORE</span>
          <strong>{overallDisplay}<small>/100</small></strong>
        </div>
        <div className="score-track">
          <i style={{ width: `${overallPercent !== null ? Math.max(0, Math.min(100, overallPercent)) : 0}%` }} />
        </div>
        <p>
          {report.answers?.length || 0} answers · Scores are automated practice feedback for teacher review.
        </p>
      </section>

      {report.adaptive_summary && (
        <section className="adaptive-summary-card" style={{ marginBottom: '28px', padding: '20px', background: 'var(--surface-color, #1e293b)', borderRadius: '12px', border: '1px solid rgba(255,255,255,0.08)' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '14px', flexWrap: 'wrap', gap: '8px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ fontSize: '1.2rem' }}>🎯</span>
              <h2 style={{ margin: 0, fontSize: '1.25rem' }}>Adaptive Learning Summary</h2>
            </div>
            <span className="status-tag completed" style={{ fontSize: '0.8rem' }}>AI Adaptive Viva</span>
          </div>

          <p style={{ margin: '0 0 16px 0', fontSize: '0.95rem', color: '#94a3b8' }}>
            {summaryStats.note}
          </p>

          {report.adaptive_summary.difficulty_progression?.length > 0 && (
            <div style={{ marginBottom: '18px' }}>
              <span className="eyebrow" style={{ display: 'block', marginBottom: '8px' }}>DIFFICULTY PROGRESSION</span>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
                {report.adaptive_summary.difficulty_progression.map((diff, idx) => {
                  const badge = formatDifficultyBadge(diff)
                  return (
                    <div key={idx} style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span className={`status-tag ${diff === 'hard' ? 'in_progress' : (diff === 'easy' ? '' : 'completed')}`}>
                        Q{idx + 1}: {badge.label}
                      </span>
                      {idx < report.adaptive_summary.difficulty_progression.length - 1 && (
                        <span style={{ color: '#64748b' }}>➔</span>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {report.adaptive_summary.topics_practiced?.length > 0 && (
            <div style={{ marginBottom: '18px' }}>
              <span className="eyebrow" style={{ display: 'block', marginBottom: '8px' }}>TOPICS PRACTICED</span>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: '10px' }}>
                {report.adaptive_summary.topics_practiced.map((tp) => (
                  <div key={tp.topic_id} style={{ padding: '10px 14px', background: 'rgba(255,255,255,0.03)', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.05)' }}>
                    <div style={{ fontWeight: 600, fontSize: '0.9rem', marginBottom: '4px' }}>{tp.topic_name}</div>
                    <div style={{ fontSize: '0.8rem', color: '#94a3b8' }}>
                      {tp.questions_count} question{tp.questions_count > 1 ? 's' : ''} · Avg: <b style={{ color: '#f8fafc' }}>{tp.average_score_percent}</b>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {report.adaptive_summary.topics_showing_improvement?.length > 0 && (
            <div style={{ marginBottom: '18px' }}>
              <span className="eyebrow" style={{ display: 'block', marginBottom: '8px', color: '#10b981' }}>📈 TOPICS SHOWING IMPROVEMENT</span>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {report.adaptive_summary.topics_showing_improvement.map((ti) => (
                  <div key={ti.topic_id} style={{ padding: '8px 12px', background: 'rgba(16, 185, 129, 0.08)', borderRadius: '6px', borderLeft: '3px solid #10b981', fontSize: '0.88rem' }}>
                    <b>{ti.topic_name}</b>: Score improved from {ti.initial_score_percent} to <b>{ti.final_score_percent}</b> ({ti.delta_percent}). {ti.insight}
                  </div>
                ))}
              </div>
            </div>
          )}

          {report.adaptive_summary.topics_needing_attention?.length > 0 && (
            <div style={{ marginBottom: '18px' }}>
              <span className="eyebrow" style={{ display: 'block', marginBottom: '8px', color: '#f59e0b' }}>⚠️ TOPICS STILL NEEDING ATTENTION</span>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {report.adaptive_summary.topics_needing_attention.map((ta) => (
                  <div key={ta.topic_id} style={{ padding: '8px 12px', background: 'rgba(245, 158, 11, 0.08)', borderRadius: '6px', borderLeft: '3px solid #f59e0b', fontSize: '0.88rem' }}>
                    <b>{ta.topic_name}</b> (Average {ta.average_score_percent}): {ta.recommendation}
                  </div>
                ))}
              </div>
            </div>
          )}

          {report.adaptive_summary.suggested_next_topics?.length > 0 && (
            <div style={{ marginTop: '16px' }}>
              <span className="eyebrow" style={{ display: 'block', marginBottom: '8px' }}>RECOMMENDED NEXT PRACTICE</span>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px' }}>
                {report.adaptive_summary.suggested_next_topics.map((st) => (
                  <button
                    key={st.topic_id}
                    className="button secondary small"
                    onClick={() => navigate(buildAdaptivePracticeUrl(report.course_id, st.topic_id))}
                    title={st.reason}
                  >
                    🎯 Practice {st.topic_name}
                  </button>
                ))}
              </div>
            </div>
          )}
        </section>
      )}

      <h2>Answer breakdown</h2>
      <div className="answer-cards">
        {(report.answers || []).map((answer, i) => {
          const rawScore = answer.override_score ?? answer.fused_score ?? answer.embedding_score
          const hasScore = rawScore !== null && rawScore !== undefined
          const scorePercent = hasScore ? Math.round(Number(rawScore) * 100) : null
          const scoreDisplay = formatRatioPercent(rawScore)

          const rubricItems = answer.rubric_breakdown
            ? Object.entries(answer.rubric_breakdown)
                .map(([key, val]) => formatRubricEntry(key, val))
                .filter(Boolean)
            : []

          return (
            <article className="answer-card" key={answer.id}>
              <div className="answer-card-head">
                <span>0{i + 1}</span>
                <strong>{scoreDisplay}</strong>
              </div>
              <h3>{answer.question_text}</h3>
              <div className="score-track">
                <i style={{ width: `${scorePercent !== null ? Math.max(0, Math.min(100, scorePercent)) : 0}%` }} />
              </div>
              <Transcript text={answer.transcript} />
              {rubricItems.length > 0 && (
                <div className="rubric-grid">
                  {rubricItems.map(({ label, value }) => (
                    <span key={label}>
                      {label}: <b>{value}</b>
                    </span>
                  ))}
                </div>
              )}
              {answer.rubric_breakdown?.justification && (
                <p className="small-muted" style={{ marginTop: '8px', textAlign: 'left' }}>
                  {answer.rubric_breakdown.justification}
                </p>
              )}
            </article>
          )
        })}
      </div>
      <button className="button primary" onClick={() => navigate('/')}>Back to courses</button>
    </main>
  )
}

function Transcript({ text }) {
  return (
    <div className="report-transcript">
      <span className="eyebrow">TRANSCRIPT</span>
      <p>{text || 'No transcript available.'}</p>
    </div>
  )
}
