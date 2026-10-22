import { useState } from 'react'
import apiClient from '../api/client'

export function useViva() {
  const [sessionId, setSessionId] = useState(null)
  const [currentQuestion, setCurrentQuestion] = useState(null)
  const [answers, setAnswers] = useState([])
  const [isRecording, setRecording] = useState(false)
  const [isProcessing, setProcessing] = useState(false)
  const [error, setError] = useState('')
  const startSession = async (config = {}) => {
    setError('')
    const { data } = await apiClient.post('/api/viva/sessions', config)
    setSessionId(data.id)
    return data
  }
  const getNextQuestion = async (id = sessionId) => {
    if (!id) throw new Error('Start an interview session before loading a question.')
    const { data } = await apiClient.post(`/api/viva/sessions/${id}/next`)
    if (!data.question_id) { await finishSession(id); return null }
    setCurrentQuestion(data); return data
  }
  const submitAnswer = async (blob) => {
    setProcessing(true); setError('')
    try {
      const form = new FormData(); form.append('file', blob, 'answer.webm'); form.append('question_id', currentQuestion.question_id)
      const { data } = await apiClient.post(`/api/viva/sessions/${sessionId}/answer`, form)
      const answer = { ...data, question: currentQuestion }
      setAnswers((items) => [...items, answer]); return answer
    } catch (err) { setError(err.userMessage || 'We could not process that recording. Please try again.'); throw err }
    finally { setProcessing(false) }
  }
  const finishSession = async (id = sessionId) => { if (id) await apiClient.post(`/api/viva/sessions/${id}/finish`); return id }
  return { sessionId, currentQuestion, setCurrentQuestion, answers, isRecording, setRecording, isProcessing, error, setError, startSession, submitAnswer, getNextQuestion, finishSession }
}
