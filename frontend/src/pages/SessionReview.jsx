import { useEffect, useState } from 'react'
import apiClient from '../api/client'
import {
  formatRatioPercent,
  formatRubricEntry,
} from '../utils/formatters'

function AnswerAudioPlayer({ audioUrl }) {
  const [blobUrl, setBlobUrl] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    let active = true
    let createdUrl = null

    if (!audioUrl) return

    setLoading(true)
    setError(null)

    apiClient
      .get(audioUrl, { responseType: 'blob' })
      .then((res) => {
        if (!active) return
        createdUrl = URL.createObjectURL(res.data)
        setBlobUrl(createdUrl)
        setLoading(false)
      })
      .catch(() => {
        if (!active) return
        setLoading(false)
        setError('Audio recording unavailable.')
      })

    return () => {
      active = false
      if (createdUrl) {
        URL.revokeObjectURL(createdUrl)
      }
    }
  }, [audioUrl])

  if (!audioUrl) return null

  return (
    <div className="audio-player-box" style={{ marginTop: '12px' }}>
      <span className="eyebrow" style={{ display: 'block', marginBottom: '6px' }}>AUDIO RECORDING</span>
      {loading && <p className="muted" style={{ fontSize: '13px', margin: '4px 0' }}>Loading audio recording…</p>}
      {error && <p className="muted" style={{ fontSize: '13px', margin: '4px 0' }}>{error}</p>}
      {blobUrl && (
        <audio
          controls
          src={blobUrl}
          preload="metadata"
          style={{ width: '100%', height: '36px', display: 'block' }}
        >
          Your browser does not support the audio element.
        </audio>
      )}
    </div>
  )
}

export default function SessionReview({ sessionId, navigate }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [score, setScore] = useState({})
  const [reason, setReason] = useState({})
  const [message, setMessage] = useState('')

  useEffect(() => {
    apiClient
      .get(`/api/viva/sessions/${sessionId}/report`)
      .then(({ data: value }) => setData(value))
      .catch((e) => setError(e.userMessage || 'Could not load session.'))
  }, [sessionId])

  const save = async (answerId) => {
    try {
      await apiClient.put(`/api/viva/sessions/${sessionId}/scores/${answerId}`, {
        score: Number(score[answerId]),
        justification: reason[answerId],
      })
      setMessage('Score override saved.')
      const refreshed = await apiClient.get(`/api/viva/sessions/${sessionId}/report`)
      setData(refreshed.data)
    } catch (e) {
      setError(e.userMessage || 'Could not save override.')
    }
  }

  return (
    <main className="page-shell">
      <button className="back-button" onClick={() => navigate('/teacher')}>
        ← All sessions
      </button>
      {error && <p className="error-text" role="alert">{error}</p>}
      {!data ? (
        <p className="muted">Loading session review…</p>
      ) : (
        <>
          <p className="eyebrow">SESSION REVIEW</p>
          <h1>
            {data.student_name || 'Student'} <span className="muted">·</span> {data.course_name}
          </h1>
          <p className="muted">
            Overall score {formatRatioPercent(data.total_score)} · {data.status}
          </p>
          {message && <p className="success-text" role="status">{message}</p>}
          {(data.behavior_flags || []).length > 0 && (
            <section className="review-flags">
              <div>
                <span className="eyebrow">CAMERA REVIEW CUES</span>
                <p>
                  These approximate local cues are provided for context only. They are not proof of cheating and do not change the score.
                </p>
              </div>
              <ul>
                {data.behavior_flags.map((flag, index) => (
                  <li key={`${flag.occurred_at}-${index}`}>
                    <strong>
                      {flag.cue_type === 'additional_faces'
                        ? 'Additional face detected'
                        : 'Repeated off-screen gaze cue'}
                    </strong>
                    <time>{new Date(flag.occurred_at).toLocaleString()}</time>
                  </li>
                ))}
              </ul>
            </section>
          )}
          <div className="answer-cards">
            {(data.answers || []).map((a, i) => {
              const effectiveRatio = a.override_score ?? a.fused_score
              const isOverridden = a.override_score !== null && a.override_score !== undefined
              const defaultScoreInput = isOverridden
                ? Math.round(Number(a.override_score) * 100)
                : (a.fused_score !== null && a.fused_score !== undefined
                    ? Math.round(Number(a.fused_score) * 100)
                    : '')

              const rubricItems = a.rubric_breakdown
                ? Object.entries(a.rubric_breakdown)
                    .map(([key, val]) => formatRubricEntry(key, val))
                    .filter(Boolean)
                : []

              return (
                <article className="answer-card" key={a.id}>
                  <div className="answer-card-head">
                    <span>ANSWER 0{i + 1}</span>
                    <div>
                      {isOverridden && (
                        <small className="muted" style={{ marginRight: '8px' }}>
                          (Overridden from {formatRatioPercent(a.fused_score)})
                        </small>
                      )}
                      <strong>{formatRatioPercent(effectiveRatio)}</strong>
                    </div>
                  </div>
                  <h3>{a.question_text}</h3>
                  <div className="report-transcript">
                    <span className="eyebrow">TRANSCRIPT</span>
                    <p>{a.transcript || 'No transcript available.'}</p>
                  </div>
                  {a.audio_url && <AnswerAudioPlayer audioUrl={a.audio_url} />}
                  {rubricItems.length > 0 && (
                    <div className="rubric-grid">
                      {rubricItems.map(({ label, value }) => (
                        <span key={label}>
                          {label}: <b>{value}</b>
                        </span>
                      ))}
                    </div>
                  )}
                  <form
                    className="override-form"
                    onSubmit={(e) => {
                      e.preventDefault()
                      save(a.id)
                    }}
                  >
                    <label>
                      Override score (0–100)
                      <input
                        type="number"
                        min="0"
                        max="100"
                        value={score[a.id] ?? defaultScoreInput}
                        onChange={(e) => setScore({ ...score, [a.id]: e.target.value })}
                      />
                    </label>
                    <label>
                      Reason
                      <input
                        required
                        value={reason[a.id] ?? (a.override_justification || '')}
                        onChange={(e) => setReason({ ...reason, [a.id]: e.target.value })}
                        placeholder="Briefly explain the adjustment"
                      />
                    </label>
                    <button className="button secondary">Save override</button>
                  </form>
                </article>
              )
            })}
          </div>
        </>
      )}
    </main>
  )
}
