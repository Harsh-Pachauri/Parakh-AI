import { useEffect, useMemo, useState } from 'react'
import apiClient from '../api/client'
import {
  validateAssessmentForm,
  formatAssessmentStatus,
  filterAssessments,
} from '../utils/assessmentHelpers'

const blankForm = {
  course_id: '',
  title: '',
  description: '',
  instructions: '',
  duration_minutes: 15,
  max_questions: 5,
  difficulty: 'medium',
  is_published: false,
}

export default function CustomVivaBuilder({ navigate, courses = [] }) {
  const [assessments, setAssessments] = useState([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  // Form states
  const [form, setForm] = useState(blankForm)
  const [editingId, setEditingId] = useState('')
  const [selectedQuestionIds, setSelectedQuestionIds] = useState([])
  const [availableQuestions, setAvailableQuestions] = useState([])
  const [loadingQuestions, setLoadingQuestions] = useState(false)

  // Filter states
  const [filterCourseId, setFilterCourseId] = useState('')
  const [filterStatus, setFilterStatus] = useState('all')
  const [searchQuery, setSearchQuery] = useState('')

  const loadAssessments = async () => {
    setLoading(true)
    setError('')
    try {
      const res = await apiClient.get('/api/assessments')
      setAssessments(Array.isArray(res.data) ? res.data : [])
    } catch (err) {
      setError(err.userMessage || 'Could not load custom assessments.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadAssessments()
  }, [])

  // Load questions for the selected course in the form
  useEffect(() => {
    if (!form.course_id) {
      setAvailableQuestions([])
      return
    }
    let active = true
    setLoadingQuestions(true)
    apiClient
      .get('/api/questions', { params: { course_id: form.course_id, limit: 100 } })
      .then((res) => {
        if (!active) return
        setAvailableQuestions(res.data?.items || [])
      })
      .catch(() => {
        if (active) setAvailableQuestions([])
      })
      .finally(() => {
        if (active) setLoadingQuestions(false)
      })
    return () => {
      active = false
    }
  }, [form.course_id])

  const toggleQuestionSelection = (questionId) => {
    setSelectedQuestionIds((prev) =>
      prev.includes(questionId) ? prev.filter((id) => id !== questionId) : [...prev, questionId],
    )
  }

  const selectAllQuestions = () => {
    setSelectedQuestionIds(availableQuestions.map((q) => q.id))
  }

  const clearSelectedQuestions = () => {
    setSelectedQuestionIds([])
  }

  const resetForm = () => {
    setForm(blankForm)
    setEditingId('')
    setSelectedQuestionIds([])
    setError('')
    setNotice('')
  }

  const beginEdit = (assessment) => {
    setEditingId(assessment.id)
    setForm({
      course_id: assessment.course_id,
      title: assessment.title,
      description: assessment.description || '',
      instructions: assessment.instructions || '',
      duration_minutes: assessment.duration_minutes || 15,
      max_questions: assessment.max_questions || 5,
      difficulty: assessment.difficulty || 'medium',
      is_published: assessment.is_published,
    })
    setSelectedQuestionIds(assessment.question_ids || [])
    setError('')
    setNotice('')
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const handleSave = async (event, publishFlag = null) => {
    event.preventDefault()
    setError('')
    setNotice('')

    const isPublished = publishFlag !== null ? publishFlag : form.is_published
    const payload = {
      ...form,
      title: form.title.trim(),
      description: form.description.trim() || null,
      instructions: form.instructions.trim() || null,
      duration_minutes: Number(form.duration_minutes),
      max_questions: Number(form.max_questions),
      is_published: isPublished,
      question_ids: selectedQuestionIds,
    }

    const validation = validateAssessmentForm(payload)
    if (!validation.valid) {
      const firstErr = Object.values(validation.errors)[0]
      setError(firstErr)
      return
    }

    setSaving(true)
    try {
      if (editingId) {
        await apiClient.put(`/api/assessments/${editingId}`, payload)
        setNotice('Custom oral assessment updated.')
      } else {
        await apiClient.post('/api/assessments', payload)
        setNotice(
          isPublished
            ? 'Custom oral assessment created and published to students!'
            : 'Custom oral assessment saved as draft.',
        )
      }
      resetForm()
      await loadAssessments()
    } catch (err) {
      setError(err.userMessage || 'Could not save assessment.')
    } finally {
      setSaving(false)
    }
  }

  const togglePublish = async (assessment) => {
    setError('')
    try {
      const res = await apiClient.post(`/api/assessments/${assessment.id}/publish`)
      const updated = res.data
      setNotice(
        updated.is_published
          ? `"${updated.title}" is now published and available to students.`
          : `"${updated.title}" was reverted to draft.`,
      )
      setAssessments((prev) => prev.map((a) => (a.id === updated.id ? updated : a)))
    } catch (err) {
      setError(err.userMessage || 'Could not update publication status.')
    }
  }

  const deleteAssessment = async (assessment) => {
    if (!window.confirm(`Permanently delete assessment "${assessment.title}"?`)) return
    setError('')
    try {
      await apiClient.delete(`/api/assessments/${assessment.id}`)
      setNotice('Assessment deleted.')
      setAssessments((prev) => prev.filter((a) => a.id !== assessment.id))
      if (editingId === assessment.id) resetForm()
    } catch (err) {
      setError(err.userMessage || 'Could not delete assessment.')
    }
  }

  const filtered = useMemo(() => {
    let list = filterAssessments(assessments, searchQuery, filterCourseId)
    if (filterStatus === 'published') list = list.filter((a) => a.is_published)
    if (filterStatus === 'draft') list = list.filter((a) => !a.is_published)
    return list
  }, [assessments, searchQuery, filterCourseId, filterStatus])

  return (
    <div className="custom-viva-builder">
      {error && (
        <div className="notice error-text" role="alert" style={{ marginBottom: '20px' }}>
          {error}
        </div>
      )}
      {notice && (
        <div className="notice success-text" role="status" style={{ marginBottom: '20px' }}>
          {notice}
        </div>
      )}

      {/* Assessment Creator / Editor Form */}
      <section className="table-card" style={{ marginBottom: '32px' }}>
        <div className="section-heading">
          <div>
            <p className="eyebrow" style={{ color: 'var(--accent-dark)' }}>
              {editingId ? 'EDIT ASSESSMENT' : 'NEW CUSTOM VIVA'}
            </p>
            <h2>{editingId ? 'Edit Oral Assessment' : 'Create Custom Oral Exam'}</h2>
          </div>
          {editingId && (
            <button className="button secondary" type="button" onClick={resetForm}>
              Cancel Edit
            </button>
          )}
        </div>

        <form onSubmit={(e) => handleSave(e)}>
          <div className="form-grid" style={{ marginBottom: '16px' }}>
            <label>
              Course <span style={{ color: '#a54439' }}>*</span>
              <select
                required
                value={form.course_id}
                onChange={(e) => setForm({ ...form, course_id: e.target.value })}
              >
                <option value="">Select a course</option>
                {courses.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name} ({c.code})
                  </option>
                ))}
              </select>
            </label>

            <label>
              Assessment Title <span style={{ color: '#a54439' }}>*</span>
              <input
                required
                maxLength={255}
                placeholder="e.g. Midterm Oral Examination: Systems"
                value={form.title}
                onChange={(e) => setForm({ ...form, title: e.target.value })}
              />
            </label>
          </div>

          <div className="form-grid" style={{ marginBottom: '16px' }}>
            <label>
              Duration (minutes) <span style={{ color: '#a54439' }}>*</span>
              <input
                type="number"
                min={1}
                max={180}
                required
                value={form.duration_minutes}
                onChange={(e) => setForm({ ...form, duration_minutes: e.target.value })}
              />
            </label>

            <label>
              Total Questions in Exam <span style={{ color: '#a54439' }}>*</span>
              <input
                type="number"
                min={1}
                max={20}
                required
                value={form.max_questions}
                onChange={(e) => setForm({ ...form, max_questions: e.target.value })}
              />
            </label>

            <label>
              Difficulty
              <select
                value={form.difficulty}
                onChange={(e) => setForm({ ...form, difficulty: e.target.value })}
              >
                <option value="easy">Easy</option>
                <option value="medium">Medium</option>
                <option value="hard">Hard</option>
                <option value="adaptive">Adaptive</option>
              </select>
            </label>
          </div>

          <label style={{ display: 'block', marginBottom: '16px' }}>
            Description (Public overview)
            <textarea
              rows={2}
              placeholder="Brief context regarding what this viva evaluates..."
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
            />
          </label>

          <label style={{ display: 'block', marginBottom: '16px' }}>
            Candidate Instructions (Displayed prior to starting)
            <textarea
              rows={2}
              placeholder="e.g. You will have 15 minutes. Explain core principles with clear terminology..."
              value={form.instructions}
              onChange={(e) => setForm({ ...form, instructions: e.target.value })}
            />
          </label>

          {/* Question Picker */}
          {form.course_id && (
            <div
              style={{
                background: '#faf8f5',
                border: '1px solid var(--line)',
                borderRadius: '8px',
                padding: '16px 18px',
                marginBottom: '20px',
              }}
            >
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  marginBottom: '12px',
                }}
              >
                <div>
                  <strong style={{ fontSize: '14px' }}>
                    Select Specific Questions ({selectedQuestionIds.length} chosen)
                  </strong>
                  <p className="muted" style={{ margin: '2px 0 0', fontSize: '12px' }}>
                    Lock in exact questions from your question bank, or leave unselected to draw dynamically.
                  </p>
                </div>
                {availableQuestions.length > 0 && (
                  <div style={{ display: 'flex', gap: '8px' }}>
                    <button
                      className="button secondary small-button"
                      type="button"
                      onClick={selectAllQuestions}
                    >
                      Select All ({availableQuestions.length})
                    </button>
                    <button
                      className="button secondary small-button"
                      type="button"
                      onClick={clearSelectedQuestions}
                    >
                      Clear
                    </button>
                  </div>
                )}
              </div>

              {loadingQuestions ? (
                <p className="muted" style={{ fontSize: '13px' }}>
                  Loading questions for this course…
                </p>
              ) : availableQuestions.length ? (
                <div
                  style={{
                    maxHeight: '260px',
                    overflowY: 'auto',
                    display: 'grid',
                    gap: '8px',
                    background: '#fff',
                    border: '1px solid var(--line)',
                    borderRadius: '6px',
                    padding: '10px 12px',
                  }}
                >
                  {availableQuestions.map((q) => {
                    const isSelected = selectedQuestionIds.includes(q.id)
                    return (
                      <label
                        key={q.id}
                        style={{
                          display: 'flex',
                          alignItems: 'flex-start',
                          gap: '10px',
                          padding: '8px 10px',
                          borderRadius: '6px',
                          background: isSelected ? '#f0f7f3' : 'transparent',
                          cursor: 'pointer',
                        }}
                      >
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={() => toggleQuestionSelection(q.id)}
                          style={{ marginTop: '3px' }}
                        />
                        <div style={{ fontSize: '13px', lineHeight: 1.4 }}>
                          <strong>{q.question_text}</strong>
                          <span
                            className="muted"
                            style={{ display: 'block', fontSize: '11px', marginTop: '2px' }}
                          >
                            {q.topic_name ? `${q.topic_name} · ` : ''}
                            {q.difficulty} · {q.question_type || 'conceptual'}
                          </span>
                        </div>
                      </label>
                    )
                  })}
                </div>
              ) : (
                <p className="muted" style={{ fontSize: '13px', margin: 0 }}>
                  No questions found for this course. Add questions in the Question Bank tab to select them here.
                </p>
              )}
            </div>
          )}

          <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
            <button
              className="button primary"
              type="button"
              disabled={saving}
              onClick={(e) => handleSave(e, true)}
            >
              {saving ? 'Saving…' : editingId ? 'Save & Publish' : 'Publish Assessment'}
            </button>
            <button
              className="button secondary"
              type="button"
              disabled={saving}
              onClick={(e) => handleSave(e, false)}
            >
              Save as Draft
            </button>
            {editingId && (
              <button className="button secondary" type="button" onClick={resetForm}>
                Cancel
              </button>
            )}
          </div>
        </form>
      </section>

      {/* Existing Assessments Directory */}
      <section className="table-card">
        <div className="section-heading">
          <div>
            <p className="eyebrow">ASSESSMENT DIRECTORY</p>
            <h2>Managed Oral Exams ({assessments.length})</h2>
          </div>
        </div>

        {/* Filter bar */}
        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: '12px',
            marginBottom: '20px',
            alignItems: 'center',
          }}
        >
          <input
            style={{ flex: 1, minWidth: '200px' }}
            placeholder="Search by assessment title or code..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />

          <select
            value={filterCourseId}
            onChange={(e) => setFilterCourseId(e.target.value)}
            style={{ width: 'auto' }}
          >
            <option value="">All Courses</option>
            {courses.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>

          <div style={{ display: 'flex', gap: '6px' }}>
            <button
              type="button"
              className={`filter-tab ${filterStatus === 'all' ? 'active' : ''}`}
              onClick={() => setFilterStatus('all')}
            >
              All
            </button>
            <button
              type="button"
              className={`filter-tab ${filterStatus === 'published' ? 'active' : ''}`}
              onClick={() => setFilterStatus('published')}
            >
              Published
            </button>
            <button
              type="button"
              className={`filter-tab ${filterStatus === 'draft' ? 'active' : ''}`}
              onClick={() => setFilterStatus('draft')}
            >
              Drafts
            </button>
          </div>
        </div>

        {loading ? (
          <p className="muted">Loading assessments…</p>
        ) : filtered.length ? (
          <div style={{ display: 'grid', gap: '14px' }}>
            {filtered.map((a) => {
              const statusInfo = formatAssessmentStatus(a.is_published)
              return (
                <article
                  key={a.id}
                  style={{
                    background: '#fffdfa',
                    border: '1px solid var(--line)',
                    borderRadius: '8px',
                    padding: '16px 20px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '10px',
                  }}
                >
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'flex-start',
                      gap: '12px',
                    }}
                  >
                    <div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                        <span className="course-code">{a.course_code || a.course_name}</span>
                        <span
                          className={statusInfo.className}
                          style={{
                            fontSize: '11px',
                            fontWeight: 700,
                            padding: '3px 8px',
                            borderRadius: '5px',
                            background: a.is_published ? '#e8f3ee' : '#ebe6de',
                            color: a.is_published ? '#41765f' : '#77808a',
                          }}
                        >
                          {statusInfo.label}
                        </span>
                        <span
                          className="count-pill"
                          style={{ fontSize: '11px', textTransform: 'capitalize' }}
                        >
                          {a.difficulty}
                        </span>
                      </div>
                      <h3 style={{ margin: '6px 0 4px', fontSize: '17px' }}>{a.title}</h3>
                      {a.description && (
                        <p style={{ margin: 0, fontSize: '13px', color: 'var(--muted)' }}>
                          {a.description}
                        </p>
                      )}
                    </div>

                    <div style={{ display: 'flex', gap: '8px', flexShrink: 0 }}>
                      <button
                        className="button secondary small-button"
                        type="button"
                        onClick={() => togglePublish(a)}
                      >
                        {a.is_published ? 'Unpublish' : 'Publish'}
                      </button>
                      <button
                        className="button secondary small-button"
                        type="button"
                        onClick={() => beginEdit(a)}
                      >
                        Edit
                      </button>
                      <button
                        className="button danger small-button"
                        type="button"
                        onClick={() => deleteAssessment(a)}
                      >
                        Delete
                      </button>
                    </div>
                  </div>

                  <div
                    style={{
                      display: 'flex',
                      gap: '16px',
                      fontSize: '12px',
                      color: '#77808a',
                      borderTop: '1px solid #f0eee9',
                      paddingTop: '8px',
                    }}
                  >
                    <span>⏱ {a.duration_minutes} minutes duration</span>
                    <span>·</span>
                    <span>📝 {a.max_questions} questions limit</span>
                    <span>·</span>
                    <span>
                      🔒 {a.question_count} locked question
                      {a.question_count === 1 ? '' : 's'}
                    </span>
                    {navigate && (
                      <>
                        <span>·</span>
                        <button
                          type="button"
                          className="text-button"
                          style={{ fontSize: '12px' }}
                          onClick={() => navigate(`/viva/${a.course_id}?assessment=${a.id}`)}
                        >
                          Preview Oral Exam ↗
                        </button>
                      </>
                    )}
                  </div>
                </article>
              )
            })}
          </div>
        ) : (
          <div className="empty-state">
            <h3>No assessments match your criteria</h3>
            <p>
              Use the builder above to configure assessment duration, instructions, and select questions from your question bank.
            </p>
          </div>
        )}
      </section>
    </div>
  )
}
