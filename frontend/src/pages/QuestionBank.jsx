import { useEffect, useMemo, useState } from 'react'
import apiClient from '../api/client'
import { inspectCsvText } from '../utils/assessmentHelpers'
import '../teacher-tools.css'

const PAGE_SIZE = 25
const blankForm = {
  topic_id: '',
  question_text: '',
  expected_key_points: '',
  difficulty: 'medium',
  question_type: 'conceptual',
  tags: '',
  explanation: '',
}

export default function QuestionBank({ navigate, initialCourseId }) {
  const [courses, setCourses] = useState([])
  const [questions, setQuestions] = useState([])
  const [total, setTotal] = useState(0)
  const [filters, setFilters] = useState({
    search: '',
    course_id: initialCourseId || '',
    topic_id: '',
    difficulty: '',
    question_type: '',
  })
  const [form, setForm] = useState(blankForm)
  const [editingId, setEditingId] = useState('')
  const [offset, setOffset] = useState(0)
  const [reload, setReload] = useState(0)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [loading, setLoading] = useState(true)

  // CSV Import State
  const [showCsvImport, setShowCsvImport] = useState(false)
  const [csvText, setCsvText] = useState('')
  const [csvCourseId, setCsvCourseId] = useState(initialCourseId || '')
  const [csvTopicId, setCsvTopicId] = useState('')
  const [csvImporting, setCsvImporting] = useState(false)
  const [csvSummary, setCsvSummary] = useState(null)

  const topics = useMemo(
    () => courses.flatMap((course) => (course.topics || []).map((topic) => ({ ...topic, course }))),
    [courses],
  )
  const visibleTopics = useMemo(
    () => topics.filter((topic) => !filters.course_id || topic.course_id === filters.course_id),
    [filters.course_id, topics],
  )
  const csvTopics = useMemo(
    () => topics.filter((topic) => !csvCourseId || topic.course_id === csvCourseId),
    [csvCourseId, topics],
  )

  useEffect(() => {
    apiClient
      .get('/api/courses')
      .then(({ data }) => setCourses(data))
      .catch((cause) => setError(cause.userMessage || 'Could not load courses.'))
  }, [])

  useEffect(() => {
    let active = true
    const params = {
      offset,
      limit: PAGE_SIZE,
      search: filters.search || undefined,
      course_id: filters.course_id || undefined,
      topic_id: filters.topic_id || undefined,
      difficulty: filters.difficulty || undefined,
      question_type: filters.question_type || undefined,
    }
    setLoading(true)
    apiClient
      .get('/api/questions', { params })
      .then(({ data }) => {
        if (!active) return
        setQuestions(data.items)
        setTotal(data.total)
        setError('')
      })
      .catch((cause) => {
        if (active) setError(cause.userMessage || 'Could not load the question bank.')
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [filters, offset, reload])

  const updateFilter = (name, value) => {
    setOffset(0)
    setFilters((current) => ({
      ...current,
      [name]: value,
      ...(name === 'course_id' ? { topic_id: '' } : {}),
    }))
  }

  const beginEdit = (question) => {
    setEditingId(question.id)
    setForm({
      topic_id: question.topic_id,
      question_text: question.question_text,
      expected_key_points: (question.expected_key_points || []).join('\n'),
      difficulty: question.difficulty,
      question_type: question.question_type || '',
      tags: (question.tags || []).join(', '),
      explanation: question.explanation || '',
    })
    setError('')
    setNotice('')
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const resetForm = () => {
    setForm(blankForm)
    setEditingId('')
  }

  const saveQuestion = async (event) => {
    event.preventDefault()
    setError('')
    setNotice('')
    const payload = {
      ...form,
      expected_key_points: form.expected_key_points
        .split('\n')
        .map((item) => item.trim())
        .filter(Boolean),
      tags: form.tags
        .split(',')
        .map((item) => item.trim())
        .filter(Boolean),
      question_type: form.question_type || null,
      explanation: form.explanation || null,
    }
    try {
      if (editingId) {
        await apiClient.put(`/api/questions/${editingId}`, payload)
        setNotice('Question updated.')
      } else {
        await apiClient.post('/api/questions', payload)
        setNotice('Question added to the bank.')
      }
      resetForm()
      setReload((value) => value + 1)
    } catch (cause) {
      setError(cause.userMessage || 'Could not save this question.')
    }
  }

  const toggleApproval = async (question) => {
    setError('')
    try {
      await apiClient.put(`/api/questions/${question.id}`, { is_approved: !question.is_approved })
      setReload((value) => value + 1)
    } catch (cause) {
      setError(cause.userMessage || 'Could not update the question.')
    }
  }

  const deleteQuestion = async (question) => {
    if (!window.confirm('Delete this question permanently?')) return
    setError('')
    try {
      await apiClient.delete(`/api/questions/${question.id}`)
      setNotice('Question deleted.')
      setReload((value) => value + 1)
    } catch (cause) {
      setError(cause.userMessage || 'Could not delete the question.')
    }
  }

  const downloadTemplate = async () => {
    try {
      const res = await apiClient.get('/api/questions/csv-template')
      const blob = new Blob([res.data], { type: 'text/csv;charset=utf-8;' })
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.setAttribute('download', 'parakh_questions_template.csv')
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
    } catch {
      setError('Could not download the CSV template.')
    }
  }

  const handleFileUpload = (event) => {
    const file = event.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = (e) => {
      setCsvText(e.target?.result || '')
    }
    reader.readAsText(file)
  }

  const submitCsvImport = async (event) => {
    event.preventDefault()
    if (!csvText.trim()) {
      setError('Please select a CSV file or paste CSV content.')
      return
    }
    setCsvImporting(true)
    setError('')
    setNotice('')
    setCsvSummary(null)
    try {
      const formData = new FormData()
      formData.append('csv_text', csvText)
      if (csvCourseId) formData.append('course_id', csvCourseId)
      if (csvTopicId) formData.append('topic_id', csvTopicId)

      const res = await apiClient.post('/api/questions/import-csv', formData)
      setCsvSummary(res.data)
      if (res.data.imported_count > 0) {
        setNotice(`Successfully imported ${res.data.imported_count} questions!`)
        setReload((v) => v + 1)
      }
    } catch (cause) {
      setError(cause.userMessage || 'CSV import failed.')
    } finally {
      setCsvImporting(false)
    }
  }

  const csvPreview = inspectCsvText(csvText)

  return (
    <main className="page-shell">
      <div className="welcome-row">
        <div>
          <p className="eyebrow">TEACHING TOOLS</p>
          <h1>Question Bank</h1>
          <p className="muted">
            Create, search, edit, approve, and bulk-import questions linked to your course topics.
          </p>
        </div>
        <div style={{ display: 'flex', gap: '10px' }}>
          <button
            className="button secondary"
            type="button"
            onClick={() => setShowCsvImport(!showCsvImport)}
          >
            {showCsvImport ? '✕ Close Import' : '📥 Bulk CSV Import'}
          </button>
          <button className="button secondary" type="button" onClick={downloadTemplate}>
            ↓ Download Template
          </button>
        </div>
      </div>

      {error && (
        <p role="alert" className="error-text notice">
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className="success-text notice">
          {notice}
        </p>
      )}

      {/* CSV Bulk Import Section */}
      {showCsvImport && (
        <section className="table-card" style={{ marginBottom: '32px', border: '1px solid #719b88' }}>
          <div className="section-heading">
            <div>
              <p className="eyebrow" style={{ color: '#41765f' }}>BULK OPERATIONS</p>
              <h2>Bulk Import Questions via CSV</h2>
            </div>
            <button className="button secondary small-button" type="button" onClick={downloadTemplate}>
              📥 Get Sample CSV
            </button>
          </div>
          <p className="muted" style={{ fontSize: '13px', marginTop: '-12px', marginBottom: '16px' }}>
            Headers supported: <code>question_text, expected_key_points, difficulty, question_type, explanation, topic_name</code>. Separate key points with semicolons.
          </p>

          <form onSubmit={submitCsvImport}>
            <div className="form-grid" style={{ marginBottom: '16px' }}>
              <label>
                Target Course (Optional default)
                <select
                  value={csvCourseId}
                  onChange={(e) => {
                    setCsvCourseId(e.target.value)
                    setCsvTopicId('')
                  }}
                >
                  <option value="">Any matching course</option>
                  {courses.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name} ({c.code})
                    </option>
                  ))}
                </select>
              </label>

              <label>
                Target Topic (Optional default)
                <select value={csvTopicId} onChange={(e) => setCsvTopicId(e.target.value)}>
                  <option value="">Match by topic_name in CSV</option>
                  {csvTopics.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                Upload CSV File
                <input type="file" accept=".csv,text/csv" onChange={handleFileUpload} />
              </label>
            </div>

            <label>
              Or Paste CSV Text Directly
              <textarea
                rows={5}
                placeholder="question_text,expected_key_points,difficulty,question_type,explanation,topic_name"
                value={csvText}
                onChange={(e) => setCsvText(e.target.value)}
                style={{ fontFamily: 'monospace', fontSize: '13px' }}
              />
            </label>

            {csvText.trim() && (
              <div style={{ margin: '10px 0 16px', fontSize: '12px', color: '#555' }}>
                <span>Detected: ~{csvPreview.rowCount} rows</span>
                {csvPreview.warnings.map((w, idx) => (
                  <span key={idx} style={{ color: '#a54439', display: 'block', marginTop: '2px' }}>
                    ⚠️ {w}
                  </span>
                ))}
              </div>
            )}

            <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
              <button className="button primary" type="submit" disabled={csvImporting || !csvText.trim()}>
                {csvImporting ? 'Importing…' : 'Start Import'}
              </button>
              <button
                className="button secondary"
                type="button"
                onClick={() => {
                  setCsvText('')
                  setCsvSummary(null)
                }}
              >
                Clear
              </button>
            </div>
          </form>

          {csvSummary && (
            <div
              style={{
                marginTop: '18px',
                padding: '14px',
                borderRadius: '8px',
                background: csvSummary.imported_count > 0 ? '#f0f7f3' : '#faeceb',
                border: `1px solid ${csvSummary.imported_count > 0 ? '#b8decb' : '#f0b8b0'}`,
              }}
            >
              <strong>{csvSummary.message}</strong>
              <div style={{ fontSize: '13px', marginTop: '4px' }}>
                <span>Imported: {csvSummary.imported_count} questions</span>
                {csvSummary.failed_count > 0 && (
                  <span style={{ color: '#a54439', marginLeft: '12px' }}>
                    Failed: {csvSummary.failed_count} rows
                  </span>
                )}
              </div>
              {csvSummary.errors && csvSummary.errors.length > 0 && (
                <ul style={{ margin: '8px 0 0', paddingLeft: '20px', fontSize: '12px', color: '#a54439' }}>
                  {csvSummary.errors.map((err, idx) => (
                    <li key={idx}>{err}</li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </section>
      )}

      {/* Question Form */}
      <section className="table-card" style={{ marginBottom: '32px' }}>
        <div className="section-heading">
          <div>
            <p className="eyebrow">{editingId ? 'EDIT QUESTION' : 'NEW QUESTION'}</p>
            <h2>{editingId ? 'Update question' : 'Add to question bank'}</h2>
          </div>
          {editingId && (
            <button className="button secondary" type="button" onClick={resetForm}>
              Cancel edit
            </button>
          )}
        </div>
        <form className="question-form" onSubmit={saveQuestion}>
          <label>
            Course topic
            <select
              required
              value={form.topic_id}
              onChange={(event) => setForm({ ...form, topic_id: event.target.value })}
            >
              <option value="">Choose a topic</option>
              {topics.map((topic) => (
                <option key={topic.id} value={topic.id}>
                  {topic.course.name} · {topic.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Question
            <textarea
              required
              minLength={1}
              maxLength={12000}
              rows={3}
              value={form.question_text}
              onChange={(event) => setForm({ ...form, question_text: event.target.value })}
            />
          </label>
          <label>
            Expected answer points / Rubric criteria (one per line)
            <textarea
              required
              rows={3}
              value={form.expected_key_points}
              onChange={(event) => setForm({ ...form, expected_key_points: event.target.value })}
            />
          </label>
          <div className="form-grid">
            <label>
              Difficulty
              <select
                value={form.difficulty}
                onChange={(event) => setForm({ ...form, difficulty: event.target.value })}
              >
                <option value="easy">Easy</option>
                <option value="medium">Medium</option>
                <option value="hard">Hard</option>
              </select>
            </label>
            <label>
              Question type
              <select
                value={form.question_type}
                onChange={(event) => setForm({ ...form, question_type: event.target.value })}
              >
                <option value="conceptual">Conceptual</option>
                <option value="practical">Practical</option>
                <option value="analytical">Analytical</option>
                <option value="application">Application</option>
              </select>
            </label>
            <label>
              Tags (comma-separated)
              <input
                value={form.tags}
                onChange={(event) => setForm({ ...form, tags: event.target.value })}
              />
            </label>
          </div>
          <label>
            Explanation or model answer notes
            <textarea
              rows={2}
              value={form.explanation}
              onChange={(event) => setForm({ ...form, explanation: event.target.value })}
            />
          </label>
          <button className="button primary" type="submit">
            {editingId ? 'Save changes' : 'Add question'}
          </button>
        </form>
      </section>

      {/* Question Library Section */}
      <section className="table-card">
        <div className="section-heading">
          <div>
            <p className="eyebrow">QUESTION LIBRARY</p>
            <h2>{total} questions</h2>
          </div>
        </div>
        <div className="form-grid">
          <label>
            Search
            <input
              value={filters.search}
              onChange={(event) => updateFilter('search', event.target.value)}
              placeholder="Search question text"
            />
          </label>
          <label>
            Course
            <select
              value={filters.course_id}
              onChange={(event) => updateFilter('course_id', event.target.value)}
            >
              <option value="">All courses</option>
              {courses.map((course) => (
                <option key={course.id} value={course.id}>
                  {course.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Topic
            <select
              value={filters.topic_id}
              onChange={(event) => updateFilter('topic_id', event.target.value)}
            >
              <option value="">All topics</option>
              {visibleTopics.map((topic) => (
                <option key={topic.id} value={topic.id}>
                  {topic.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Difficulty
            <select
              value={filters.difficulty}
              onChange={(event) => updateFilter('difficulty', event.target.value)}
            >
              <option value="">Any difficulty</option>
              <option value="easy">Easy</option>
              <option value="medium">Medium</option>
              <option value="hard">Hard</option>
            </select>
          </label>
          <label>
            Type
            <select
              value={filters.question_type}
              onChange={(event) => updateFilter('question_type', event.target.value)}
            >
              <option value="">Any type</option>
              <option value="conceptual">Conceptual</option>
              <option value="practical">Practical</option>
              <option value="analytical">Analytical</option>
              <option value="application">Application</option>
            </select>
          </label>
        </div>

        {loading ? (
          <p className="muted">Loading questions…</p>
        ) : questions.length ? (
          <div className="question-bank-list">
            {questions.map((question) => (
              <article className="answer-card" key={question.id}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <p className="eyebrow">
                    {question.course_name ? `${question.course_name} · ` : ''}
                    {question.topic_name ? `${question.topic_name} · ` : ''}
                    {question.difficulty} · {question.question_type || 'question'} ·{' '}
                    {question.is_approved ? 'Approved' : 'Needs review'}
                  </p>
                  <span className="count-pill" style={{ fontSize: '11px' }}>
                    Used {question.times_used || 0} times
                  </span>
                </div>
                <h3>{question.question_text}</h3>
                <p className="muted">
                  Key points: {(question.expected_key_points || []).join(' · ') || 'Not specified'}
                </p>
                {question.explanation && (
                  <p style={{ fontSize: '13px', color: '#4b5563', fontStyle: 'italic' }}>
                    Notes: {question.explanation}
                  </p>
                )}
                {!!question.tags?.length && <p className="muted">Tags: {question.tags.join(', ')}</p>}
                <div className="row-actions">
                  <button className="button secondary" onClick={() => beginEdit(question)}>
                    Edit
                  </button>
                  <button className="button secondary" onClick={() => toggleApproval(question)}>
                    {question.is_approved ? 'Unapprove' : 'Approve'}
                  </button>
                  <button className="button danger" onClick={() => deleteQuestion(question)}>
                    Delete
                  </button>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <p className="muted">No questions match these filters.</p>
        )}
        <div className="row-actions">
          <button
            className="button secondary"
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
          >
            Previous
          </button>
          <span className="muted">
            {total ? offset + 1 : 0}–{Math.min(offset + PAGE_SIZE, total)} of {total}
          </span>
          <button
            className="button secondary"
            disabled={offset + PAGE_SIZE >= total}
            onClick={() => setOffset(offset + PAGE_SIZE)}
          >
            Next
          </button>
        </div>
      </section>
    </main>
  )
}
