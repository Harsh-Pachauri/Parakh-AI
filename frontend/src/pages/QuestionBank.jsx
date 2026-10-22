import { useEffect, useMemo, useState } from 'react'
import apiClient from '../api/client'
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

export default function QuestionBank() {
  const [courses, setCourses] = useState([])
  const [questions, setQuestions] = useState([])
  const [total, setTotal] = useState(0)
  const [filters, setFilters] = useState({ search: '', course_id: '', topic_id: '', difficulty: '', question_type: '' })
  const [form, setForm] = useState(blankForm)
  const [editingId, setEditingId] = useState('')
  const [offset, setOffset] = useState(0)
  const [reload, setReload] = useState(0)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [loading, setLoading] = useState(true)

  const topics = useMemo(
    () => courses.flatMap((course) => (course.topics || []).map((topic) => ({ ...topic, course }))),
    [courses],
  )
  const visibleTopics = useMemo(
    () => topics.filter((topic) => !filters.course_id || topic.course_id === filters.course_id),
    [filters.course_id, topics],
  )

  useEffect(() => {
    apiClient.get('/api/courses')
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
    apiClient.get('/api/questions', { params })
      .then(({ data }) => {
        if (!active) return
        setQuestions(data.items)
        setTotal(data.total)
        setError('')
      })
      .catch((cause) => {
        if (active) setError(cause.userMessage || 'Could not load the question bank.')
      })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
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
      expected_key_points: form.expected_key_points.split('\n').map((item) => item.trim()).filter(Boolean),
      tags: form.tags.split(',').map((item) => item.trim()).filter(Boolean),
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

  return (
    <main className="page-shell">
      <p className="eyebrow">TEACHING TOOLS</p>
      <h1>Question bank</h1>
      <p className="muted">Create, search, edit, and approve questions linked to your course topics.</p>
      {error && <p role="alert" className="error-text">{error}</p>}
      {notice && <p role="status" className="success-text">{notice}</p>}

      <section className="table-card">
        <div className="section-heading">
          <div><p className="eyebrow">{editingId ? 'EDIT QUESTION' : 'NEW QUESTION'}</p><h2>{editingId ? 'Update question' : 'Add to question bank'}</h2></div>
          {editingId && <button className="button secondary" type="button" onClick={resetForm}>Cancel edit</button>}
        </div>
        <form className="question-form" onSubmit={saveQuestion}>
          <label>Course topic
            <select required value={form.topic_id} onChange={(event) => setForm({ ...form, topic_id: event.target.value })}>
              <option value="">Choose a topic</option>
              {topics.map((topic) => <option key={topic.id} value={topic.id}>{topic.course.name} · {topic.name}</option>)}
            </select>
          </label>
          <label>Question
            <textarea required minLength={1} maxLength={12000} rows={3} value={form.question_text} onChange={(event) => setForm({ ...form, question_text: event.target.value })} />
          </label>
          <label>Expected answer points (one per line)
            <textarea required rows={3} value={form.expected_key_points} onChange={(event) => setForm({ ...form, expected_key_points: event.target.value })} />
          </label>
          <div className="form-grid">
            <label>Difficulty
              <select value={form.difficulty} onChange={(event) => setForm({ ...form, difficulty: event.target.value })}>
                <option value="easy">Easy</option><option value="medium">Medium</option><option value="hard">Hard</option>
              </select>
            </label>
            <label>Question type
              <select value={form.question_type} onChange={(event) => setForm({ ...form, question_type: event.target.value })}>
                <option value="conceptual">Conceptual</option><option value="practical">Practical</option><option value="analytical">Analytical</option><option value="application">Application</option>
              </select>
            </label>
            <label>Tags (comma-separated)
              <input value={form.tags} onChange={(event) => setForm({ ...form, tags: event.target.value })} />
            </label>
          </div>
          <label>Explanation or evaluation notes
            <textarea rows={2} value={form.explanation} onChange={(event) => setForm({ ...form, explanation: event.target.value })} />
          </label>
          <button className="button primary" type="submit">{editingId ? 'Save changes' : 'Add question'}</button>
        </form>
      </section>

      <section className="table-card">
        <div className="section-heading"><div><p className="eyebrow">QUESTION LIBRARY</p><h2>{total} questions</h2></div></div>
        <div className="form-grid">
          <label>Search<input value={filters.search} onChange={(event) => updateFilter('search', event.target.value)} placeholder="Search question text" /></label>
          <label>Course<select value={filters.course_id} onChange={(event) => updateFilter('course_id', event.target.value)}><option value="">All courses</option>{courses.map((course) => <option key={course.id} value={course.id}>{course.name}</option>)}</select></label>
          <label>Topic<select value={filters.topic_id} onChange={(event) => updateFilter('topic_id', event.target.value)}><option value="">All topics</option>{visibleTopics.map((topic) => <option key={topic.id} value={topic.id}>{topic.name}</option>)}</select></label>
          <label>Difficulty<select value={filters.difficulty} onChange={(event) => updateFilter('difficulty', event.target.value)}><option value="">Any difficulty</option><option value="easy">Easy</option><option value="medium">Medium</option><option value="hard">Hard</option></select></label>
          <label>Type<select value={filters.question_type} onChange={(event) => updateFilter('question_type', event.target.value)}><option value="">Any type</option><option value="conceptual">Conceptual</option><option value="practical">Practical</option><option value="analytical">Analytical</option><option value="application">Application</option></select></label>
        </div>
        {loading ? <p className="muted">Loading questions…</p> : questions.length ? (
          <div className="question-bank-list">
            {questions.map((question) => (
              <article className="answer-card" key={question.id}>
                <p className="eyebrow">{question.difficulty} · {question.question_type || 'question'} · {question.is_approved ? 'Approved' : 'Needs review'}</p>
                <h3>{question.question_text}</h3>
                <p className="muted">Key points: {(question.expected_key_points || []).join(' · ') || 'Not specified'}</p>
                {!!question.tags?.length && <p className="muted">Tags: {question.tags.join(', ')}</p>}
                <div className="row-actions">
                  <button className="button secondary" onClick={() => beginEdit(question)}>Edit</button>
                  <button className="button secondary" onClick={() => toggleApproval(question)}>{question.is_approved ? 'Unapprove' : 'Approve'}</button>
                  <button className="button danger" onClick={() => deleteQuestion(question)}>Delete</button>
                </div>
              </article>
            ))}
          </div>
        ) : <p className="muted">No questions match these filters.</p>}
        <div className="row-actions">
          <button className="button secondary" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>Previous</button>
          <span className="muted">{total ? offset + 1 : 0}–{Math.min(offset + PAGE_SIZE, total)} of {total}</span>
          <button className="button secondary" disabled={offset + PAGE_SIZE >= total} onClick={() => setOffset(offset + PAGE_SIZE)}>Next</button>
        </div>
      </section>
    </main>
  )
}
