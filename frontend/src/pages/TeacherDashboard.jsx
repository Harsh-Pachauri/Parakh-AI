import { useEffect, useMemo, useState } from 'react'
import apiClient from '../api/client'
import '../teacher-tools.css'

const blankCourse = {
  name: '',
  subject: '',
  code: '',
  academic_level: '',
  description: '',
  syllabus_text: '',
  interview_config: {
    max_questions: 5,
    max_duration_sec: 900,
    difficulty: 'medium',
    topic_ids: [],
  },
}

export default function TeacherDashboard({ navigate }) {
  const [sessions, setSessions] = useState([])
  const [courses, setCourses] = useState([])
  const [selectedCourseId, setSelectedCourseId] = useState('')
  const [courseForm, setCourseForm] = useState(blankCourse)
  const [topicDrafts, setTopicDrafts] = useState({})
  const [filter, setFilter] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  const selectedCourse = useMemo(
    () => courses.find((course) => course.id === selectedCourseId),
    [courses, selectedCourseId],
  )
  const visible = sessions.filter((session) => !filter || session.course_id === filter)

  const loadData = async () => {
    const [sessionResponse, courseResponse] = await Promise.all([
      apiClient.get('/api/teacher/sessions'),
      apiClient.get('/api/courses'),
    ])
    setSessions(sessionResponse.data)
    setCourses(courseResponse.data)
  }

  useEffect(() => {
    loadData()
      .catch((cause) => setError(cause.userMessage || 'Could not load the teacher workspace.'))
      .finally(() => setLoading(false))
  }, [])

  const exportCsv = async () => {
    try {
      const { data } = await apiClient.get('/api/reports/export', {
        params: { course_id: filter || undefined },
        responseType: 'blob',
      })
      const url = URL.createObjectURL(data)
      const link = document.createElement('a')
      link.href = url
      link.download = 'viva-sessions.csv'
      link.click()
      URL.revokeObjectURL(url)
    } catch (cause) {
      setError(cause.userMessage || 'CSV export is unavailable.')
    }
  }

  const openCourse = (id) => {
    setSelectedCourseId(id)
    setNotice('')
    setError('')
    if (!id) {
      setCourseForm(blankCourse)
      setTopicDrafts({})
      return
    }
    const course = courses.find((item) => item.id === id)
    if (!course) return
    setCourseForm({
      name: course.name,
      subject: course.subject || '',
      code: course.code,
      academic_level: course.academic_level || '',
      description: course.description || '',
      syllabus_text: course.syllabus_text || '',
      interview_config: {
        max_questions: course.interview_config?.max_questions || 5,
        max_duration_sec: course.interview_config?.max_duration_sec || 900,
        difficulty: course.interview_config?.difficulty || 'medium',
        topic_ids: course.interview_config?.topic_ids || [],
      },
    })
    setTopicDrafts(Object.fromEntries((course.topics || []).map((topic) => [topic.id, topic.name])))
  }

  const saveCourse = async (event) => {
    event.preventDefault()
    setSaving(true)
    setError('')
    setNotice('')
    try {
      const response = selectedCourseId
        ? await apiClient.put(`/api/courses/${selectedCourseId}`, courseForm)
        : await apiClient.post('/api/courses', courseForm)
      const saved = response.data
      setCourses((existing) => [
        saved,
        ...existing.filter((course) => course.id !== saved.id),
      ])
      setSelectedCourseId(saved.id)
      setNotice('Course and syllabus saved.')
    } catch (cause) {
      setError(cause.userMessage || 'Could not save this course.')
    } finally {
      setSaving(false)
    }
  }

  const analyzeSyllabus = async () => {
    if (!selectedCourseId) return
    setSaving(true)
    setError('')
    setNotice('')
    try {
      const { data } = await apiClient.post(`/api/courses/${selectedCourseId}/syllabus/analyze`)
      setCourses((existing) => existing.map((course) => (course.id === data.id ? data : course)))
      setTopicDrafts(Object.fromEntries((data.topics || []).map((topic) => [topic.id, topic.name])))
      setNotice('Syllabus analyzed. Review the extracted topics below before interviews.')
    } catch (cause) {
      setError(cause.userMessage || 'Syllabus analysis failed.')
    } finally {
      setSaving(false)
    }
  }

  const saveTopicName = async (topic) => {
    const name = (topicDrafts[topic.id] || '').trim()
    if (!name) {
      setError('A topic name cannot be empty.')
      return
    }
    setError('')
    try {
      const { data } = await apiClient.put(
        `/api/courses/${selectedCourseId}/syllabus/topics/${topic.id}`,
        { name },
      )
      setCourses((existing) => existing.map((course) => (course.id === data.id ? data : course)))
      setTopicDrafts(Object.fromEntries((data.topics || []).map((item) => [item.id, item.name])))
      setNotice('Syllabus topic updated.')
    } catch (cause) {
      setError(cause.userMessage || 'Could not update the topic.')
    }
  }

  const setInterviewConfig = (key, value) => {
    setCourseForm((current) => ({
      ...current,
      interview_config: { ...current.interview_config, [key]: value },
    }))
  }

  const toggleInterviewTopic = (topicId) => {
    const selected = courseForm.interview_config.topic_ids || []
    setInterviewConfig(
      'topic_ids',
      selected.includes(topicId) ? selected.filter((id) => id !== topicId) : [...selected, topicId],
    )
  }

  return (
    <main className="page-shell">
      <div className="welcome-row">
        <div><p className="eyebrow">TEACHER WORKSPACE</p><h1>Review the thinking.</h1><p className="muted">Manage course syllabi, configure autonomous interviews, and review student sessions.</p></div>
        <button className="button secondary" onClick={exportCsv}>↓ Export CSV</button>
      </div>
      {error && <p className="error-text notice" role="alert">{error}</p>}
      {notice && <p className="success-text notice" role="status">{notice}</p>}

      <section className="table-card course-editor">
        <div className="section-heading">
          <div><p className="eyebrow">COURSE & SYLLABUS</p><h2>{selectedCourseId ? 'Edit a course' : 'Configure a course'}</h2></div>
          <label className="filter-label">Saved courses
            <select value={selectedCourseId} onChange={(event) => openCourse(event.target.value)}>
              <option value="">Create a course</option>
              {courses.map((course) => <option key={course.id} value={course.id}>{course.name}</option>)}
            </select>
          </label>
        </div>
        <form className="question-form" onSubmit={saveCourse}>
          <div className="form-grid">
            <label>Course name<input required maxLength={255} value={courseForm.name} onChange={(event) => setCourseForm({ ...courseForm, name: event.target.value })} /></label>
            <label>Subject<input value={courseForm.subject} maxLength={255} onChange={(event) => setCourseForm({ ...courseForm, subject: event.target.value })} /></label>
            <label>Course code<input required maxLength={50} value={courseForm.code} onChange={(event) => setCourseForm({ ...courseForm, code: event.target.value })} /></label>
            <label>Academic level<input value={courseForm.academic_level} maxLength={100} placeholder="e.g. Undergraduate" onChange={(event) => setCourseForm({ ...courseForm, academic_level: event.target.value })} /></label>
          </div>
          <label>Course description<textarea rows={2} value={courseForm.description} onChange={(event) => setCourseForm({ ...courseForm, description: event.target.value })} /></label>
          <label>Complete syllabus<textarea required rows={10} value={courseForm.syllabus_text} onChange={(event) => setCourseForm({ ...courseForm, syllabus_text: event.target.value })} placeholder="Paste the original course syllabus here. It is stored as the source of truth." /></label>
          <div className="section-heading"><div><p className="eyebrow">AUTONOMOUS INTERVIEW</p><h3>Interview defaults</h3></div></div>
          <div className="form-grid">
            <label>Question count<input type="number" min="1" max="10" value={courseForm.interview_config.max_questions} onChange={(event) => setInterviewConfig('max_questions', Number(event.target.value))} /></label>
            <label>Duration (minutes)<input type="number" min="1" max="120" value={Math.round(courseForm.interview_config.max_duration_sec / 60)} onChange={(event) => setInterviewConfig('max_duration_sec', Number(event.target.value) * 60)} /></label>
            <label>Difficulty<select value={courseForm.interview_config.difficulty} onChange={(event) => setInterviewConfig('difficulty', event.target.value)}><option value="easy">Easy</option><option value="medium">Medium</option><option value="hard">Hard</option></select></label>
          </div>
          {!!selectedCourse?.topics?.length && <fieldset className="topic-coverage"><legend>Topics to cover (leave all unchecked to include every topic)</legend>{selectedCourse.topics.map((topic) => <label key={topic.id}><input type="checkbox" checked={courseForm.interview_config.topic_ids.includes(topic.id)} onChange={() => toggleInterviewTopic(topic.id)} />{topic.name}</label>)}</fieldset>}
          <div className="row-actions">
            <button className="button primary" type="submit" disabled={saving}>{saving ? 'Saving…' : 'Save course and syllabus'}</button>
            {selectedCourseId && <button className="button secondary" type="button" disabled={saving || !courseForm.syllabus_text.trim()} onClick={analyzeSyllabus}>Analyze syllabus with Groq</button>}
          </div>
        </form>
        {selectedCourse?.syllabus_analysis?.modules?.length > 0 && (
          <section className="syllabus-review">
            <p className="eyebrow">EXTRACTED TOPICS · REVIEW & EDIT</p>
            {selectedCourse.syllabus_analysis.modules.map((module, index) => (
              <details key={`${module.name}-${index}`} open>
                <summary>{module.name}</summary>
                <div className="topic-editor-list">
                  {(module.topics || []).map((item) => {
                    const topic = selectedCourse.topics.find((savedTopic) => savedTopic.name.toLowerCase() === item.name.toLowerCase())
                    if (!topic) return <p key={item.name}>{item.name}</p>
                    return <div className="topic-editor-row" key={topic.id}>
                      <input aria-label={`Topic name for ${item.name}`} value={topicDrafts[topic.id] ?? topic.name} onChange={(event) => setTopicDrafts({ ...topicDrafts, [topic.id]: event.target.value })} />
                      <button className="button secondary" type="button" onClick={() => saveTopicName(topic)}>Save topic</button>
                      <span className="muted">{item.key_concepts?.join(' · ')}</span>
                    </div>
                  })}
                </div>
              </details>
            ))}
          </section>
        )}
      </section>

      <section className="table-card recent-section">
        <div className="section-heading">
          <div><p className="eyebrow">SESSION OVERVIEW</p><h2>Student sessions</h2></div>
          <label className="filter-label">Course<select aria-label="Filter sessions by course" value={filter} onChange={(event) => setFilter(event.target.value)}><option value="">All courses</option>{courses.map((course) => <option value={course.id} key={course.id}>{course.name}</option>)}</select></label>
        </div>
        {loading ? <p className="muted">Loading sessions…</p> : visible.length ? (
          <div className="session-list">{visible.map((session) => (
            <div className="session-row" key={session.id}>
              <div><strong>{session.student_name || 'Student'}</strong><span>{session.course_name} · {new Date(session.created_at).toLocaleString()}</span></div>
              <span className={`status-tag ${session.status}`}>{session.status}</span>
              <span className="session-score">{session.total_score == null ? '—' : `${Math.round(session.total_score * 100)}%`}</span>
              <button className="text-button" onClick={() => navigate(`/review/${session.id}`)}>Review →</button>
            </div>
          ))}</div>
        ) : <div className="empty-state"><h3>No sessions to review</h3><p>Completed student viva sessions will appear here.</p></div>}
      </section>

      <section className="teacher-tools">
        <article><span className="eyebrow">CONTENT</span><h3>Question bank</h3><p>Review and manage questions across your course topics.</p><button className="text-button" onClick={() => navigate('/questions')}>Open question bank →</button></article>
        <article><span className="eyebrow">COURSES</span><h3>{courses.length} active courses</h3><p>Saved syllabi and interview defaults are persisted with each course.</p></article>
      </section>
    </main>
  )
}
