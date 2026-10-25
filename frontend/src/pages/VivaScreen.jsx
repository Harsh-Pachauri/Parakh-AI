import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useViva } from '../hooks/useViva'
import { useAuth } from '../hooks/useAuth'
import { useBehaviorMonitor } from '../hooks/useBehaviorMonitor'
import useLiveInterview from '../hooks/useLiveInterview'
import apiClient from '../api/client'
import { BrandMark } from '../components/Brand'
import ConsentModal from '../components/ConsentModal'
import Timer from '../components/Timer'
import { getVivaOpeningGreeting } from '../utils/conversationalHelpers'
import '../live-interview.css'

const mediaConstraints = (cameraId, microphoneId) => ({
  audio: {
    ...(microphoneId ? { deviceId: { exact: microphoneId } } : {}),
    echoCancellation: true,
    noiseSuppression: true,
    autoGainControl: true,
  },
  video: {
    ...(cameraId ? { deviceId: { exact: cameraId } } : { facingMode: 'user' }),
    width: { ideal: 1280 },
    height: { ideal: 720 },
  },
})

function mediaErrorMessage(error) {
  if (error.name === 'NotAllowedError' || error.name === 'SecurityError') {
    return 'Camera or microphone permission was denied. Allow both in your browser site settings, then retry.'
  }
  if (error.name === 'NotFoundError' || error.name === 'DevicesNotFoundError') {
    return 'No camera or microphone was found. Connect a device and retry.'
  }
  if (error.name === 'NotReadableError' || error.name === 'TrackStartError') {
    return 'The camera or microphone is in use by another app. Close it there and retry.'
  }
  if (!navigator.mediaDevices?.getUserMedia) {
    return 'Camera access needs a supported browser on HTTPS or localhost.'
  }
  return error.message || 'Could not initialize the camera and microphone. Check device permissions and retry.'
}

export default function VivaScreen({ navigate, courseId, topicId, assessmentId, assignmentId }) {
  const [assessmentTitle, setAssessmentTitle] = useState('')
  const viva = useViva()
  const { user } = useAuth()
  const [step, setStep] = useState('consent')
  const [busy, setBusy] = useState(false)
  const [startedAt, setStartedAt] = useState(Date.now())
  const [interviewLimits, setInterviewLimits] = useState({ maxQuestions: 5, durationSec: 900 })
  const [mediaStream, setMediaStream] = useState(null)
  const streamRef = useRef(null)
  const [videoElement, setVideoElement] = useState(null)
  const [mediaError, setMediaError] = useState('')
  const [cameraOn, setCameraOn] = useState(true)
  const [micOn, setMicOn] = useState(true)
  const [cameraConsent, setCameraConsent] = useState(false)
  const [devices, setDevices] = useState({ cameras: [], microphones: [] })
  const [cameraId, setCameraId] = useState('')
  const [microphoneId, setMicrophoneId] = useState('')
  const [connected, setConnected] = useState(false)
  const [now, setNow] = useState(Date.now())
  const transcriptRef = useRef(null)
  const endingRef = useRef(false)
  const shouldAutoScrollRef = useRef(true)

  const handleTextTurn = useCallback(async (transcript) => {
    const questionId = viva.currentQuestion?.question_id
    if (!questionId || !viva.sessionId) throw new Error('The current interview question is missing. End and restart the interview.')
    const { data } = await apiClient.post(`/api/viva/sessions/${viva.sessionId}/turn`, {
      question_id: questionId,
      transcript,
    })
    viva.setCurrentQuestion(data.next_question)
    return data
  }, [viva.currentQuestion?.question_id, viva.sessionId, viva.setCurrentQuestion])

  const handleAudioTurn = useCallback(async (blob) => {
    const questionId = viva.currentQuestion?.question_id
    if (!questionId || !viva.sessionId) throw new Error('The current interview question is missing. End and restart the interview.')
    const form = new FormData()
    form.append('file', blob, 'answer.webm')
    form.append('question_id', questionId)
    const { data } = await apiClient.post(`/api/viva/sessions/${viva.sessionId}/turn/audio`, form)
    viva.setCurrentQuestion(data.next_question)
    return data
  }, [viva.currentQuestion?.question_id, viva.sessionId, viva.setCurrentQuestion])

  const conversation = useLiveInterview({
    stream: mediaStream,
    microphoneEnabled: micOn,
    onTurn: handleTextTurn,
    onAudioTurn: handleAudioTurn,
    onComplete: () => navigate(viva.sessionId ? `/report/${viva.sessionId}` : '/'),
  })

  const videoRef = useRef(null)
  const monitorEnabled = Boolean(
    viva.sessionId && step === 'interview' && cameraOn && cameraConsent,
  )
  const {
    status: monitorStatus,
    warning: cueWarning,
    dismissWarning,
  } = useBehaviorMonitor(videoRef, viva.sessionId, monitorEnabled)

  const questionNumber = useMemo(
    () => Math.min(interviewLimits.maxQuestions, conversation.messages.filter((message) => message.speaker === 'candidate').length + 1),
    [conversation.messages, interviewLimits.maxQuestions],
  )

  useEffect(() => {
    let disposed = false
    const checkConnection = async () => {
      try {
        await apiClient.get('/api/health', { timeout: 5000 })
        if (!disposed) setConnected(true)
      } catch {
        if (!disposed) setConnected(false)
      }
    }
    void checkConnection()
    const interval = window.setInterval(checkConnection, 15000)
    return () => {
      disposed = true
      window.clearInterval(interval)
    }
  }, [])

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [])

  useEffect(() => {
    if (!transcriptRef.current || !shouldAutoScrollRef.current) return
    transcriptRef.current.scrollTop = transcriptRef.current.scrollHeight
  }, [conversation.messages, conversation.interim])

  useEffect(() => {
    if (!videoElement || !mediaStream) return undefined
    videoRef.current = videoElement
    videoElement.srcObject = mediaStream
    const play = () => {
      videoElement.play().catch((error) => {
        setMediaError(`The live camera preview could not start: ${error.message || 'press Retry camera.'}`)
      })
    }
    if (videoElement.readyState >= HTMLMediaElement.HAVE_METADATA) play()
    else videoElement.addEventListener('loadedmetadata', play, { once: true })
    return () => {
      videoElement.removeEventListener('loadedmetadata', play)
      if (videoElement.srcObject === mediaStream) videoElement.srcObject = null
    }
  }, [videoElement, mediaStream])

  useEffect(() => {
    if (!mediaStream) return undefined
    const handleEnded = (event) => {
      if (!streamRef.current?.getTracks().includes(event.target)) return
      if (event.target.kind === 'video') {
        setCameraOn(false)
        setMediaError('The camera disconnected. Reconnect it and use Retry camera to continue.')
      } else {
        setMicOn(false)
        setMediaError('The microphone disconnected. Reconnect it and retry microphone access.')
      }
    }
    const tracks = mediaStream.getTracks()
    tracks.forEach((track) => track.addEventListener('ended', handleEnded))
    return () => tracks.forEach((track) => track.removeEventListener('ended', handleEnded))
  }, [mediaStream])

  useEffect(() => {
    if (!mediaStream || !navigator.mediaDevices?.enumerateDevices) return undefined
    let disposed = false
    const refresh = async () => {
      try {
        const inputs = await navigator.mediaDevices.enumerateDevices()
        if (disposed) return
        setDevices({
          cameras: inputs.filter((device) => device.kind === 'videoinput'),
          microphones: inputs.filter((device) => device.kind === 'audioinput'),
        })
      } catch {
        setMediaError('Could not list available devices. The current camera and microphone remain active.')
      }
    }
    void refresh()
    navigator.mediaDevices.addEventListener?.('devicechange', refresh)
    return () => {
      disposed = true
      navigator.mediaDevices.removeEventListener?.('devicechange', refresh)
    }
  }, [mediaStream])

  useEffect(() => () => {
    streamRef.current?.getTracks().forEach((track) => track.stop())
  }, [])

  const acquireMedia = useCallback(async (
    selectedCamera = cameraId,
    selectedMicrophone = microphoneId,
    preserveToggleState = false,
  ) => {
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error('Camera access needs a supported browser on HTTPS or localhost.')
    }
    const newStream = await navigator.mediaDevices.getUserMedia(
      mediaConstraints(selectedCamera, selectedMicrophone),
    )
    if (preserveToggleState) {
      newStream.getVideoTracks().forEach((track) => { track.enabled = cameraOn })
      newStream.getAudioTracks().forEach((track) => { track.enabled = micOn })
    }
    const previousStream = streamRef.current
    streamRef.current = newStream
    setMediaStream(newStream)
    setCameraOn(preserveToggleState ? cameraOn : true)
    setMicOn(preserveToggleState ? micOn : true)
    previousStream?.getTracks().forEach((track) => track.stop())
    setMediaError('')
    return newStream
  }, [cameraId, cameraOn, microphoneId, micOn])

  const begin = async (retainAudio, enableCameraCues) => {
    setBusy(true)
    setMediaError('')
    viva.setError('')
    let session
    try {
      await acquireMedia()
      try {
        await apiClient.get('/api/health/ai')
      } catch (healthError) {
        const status = healthError.response?.status
        const detail = healthError.response?.data?.detail || healthError.userMessage || ''
        const isConfigOrAuthError =
          status === 401 ||
          status === 403 ||
          detail.includes('GROQ_API_KEY is not configured') ||
          detail.includes('authentication failed')

        if (isConfigOrAuthError) {
          throw healthError
        }
        console.warn('AI health probe encountered a transient issue; continuing with viva session:', detail)
      }
      const startPayload = {}
      if (courseId) startPayload.course_id = courseId
      if (topicId) startPayload.topic_ids = [topicId]
      if (assessmentId) startPayload.assessment_id = assessmentId
      if (assignmentId) startPayload.assignment_id = assignmentId
      session = await viva.startSession(startPayload)
      if (session.assignment_title) setAssessmentTitle(session.assignment_title)
      else if (session.assessment_title) setAssessmentTitle(session.assessment_title)
      setInterviewLimits({
        maxQuestions: session.max_questions || 5,
        durationSec: session.max_duration_sec || 900,
      })
      await apiClient.post('/api/consent', {
        session_id: session.id,
        audio_retention_consent: retainAudio,
        transcript_consent: true,
        camera_analysis_consent: enableCameraCues,
      })
      setCameraConsent(enableCameraCues)
      const question = await viva.getNextQuestion(session.id)
      if (!question) {
        navigate(`/report/${session.id}`)
        return
      }
      setStartedAt(Date.now())
      setStep('interview')
      const opening = question.opening_greeting || getVivaOpeningGreeting(user?.full_name, !assessmentId && !assignmentId, assessmentTitle)
      const spokenText = opening ? `${opening} ${question.question_text}` : question.question_text
      void conversation.ask(spokenText)
    } catch (error) {
      streamRef.current?.getTracks().forEach((track) => track.stop())
      streamRef.current = null
      setMediaStream(null)
      if (session) {
        try { await apiClient.post(`/api/viva/sessions/${session.id}/finish`) } catch { /* Session cleanup is best effort when startup fails. */ }
      }
      const message = error.userMessage || mediaErrorMessage(error)
      setMediaError(message)
      viva.setError(message)
    } finally {
      setBusy(false)
    }
  }

  const retryDevices = async () => {
    try {
      await acquireMedia()
      if (step === 'interview' && conversation.phase === 'error') conversation.retry()
    } catch (error) {
      setMediaError(mediaErrorMessage(error))
    }
  }

  const changeDevice = async (kind, id) => {
    const nextCameraId = kind === 'camera' ? id : cameraId
    const nextMicrophoneId = kind === 'microphone' ? id : microphoneId
    try {
      await acquireMedia(nextCameraId, nextMicrophoneId, true)
      if (kind === 'camera') setCameraId(id)
      else setMicrophoneId(id)
      setMediaError('')
    } catch (error) {
      setMediaError(mediaErrorMessage(error))
    }
  }

  const toggleCamera = () => {
    const enabled = !cameraOn
    mediaStream?.getVideoTracks().forEach((track) => { track.enabled = enabled })
    setCameraOn(enabled)
    if (enabled && !mediaStream?.getVideoTracks().some((track) => track.readyState === 'live')) {
      void retryDevices()
    }
  }

  const toggleMicrophone = () => {
    const enabled = !micOn
    mediaStream?.getAudioTracks().forEach((track) => { track.enabled = enabled })
    setMicOn(enabled)
  }

  const endInterview = async () => {
    if (endingRef.current) return
    endingRef.current = true
    conversation.end()
    streamRef.current?.getTracks().forEach((track) => track.stop())
    streamRef.current = null
    setMediaStream(null)
    try {
      await viva.finishSession()
    } catch {
      setMediaError('The interview ended locally, but the server could not save its completion status.')
    }
    navigate(viva.sessionId ? `/report/${viva.sessionId}` : '/')
  }

  useEffect(() => {
    if (step === 'interview' && now - startedAt >= interviewLimits.durationSec * 1000) {
      void endInterview()
    }
  }, [interviewLimits.durationSec, now, startedAt, step])

  const retryConversation = () => {
    conversation.setError('')
    viva.setError('')
    conversation.retry()
  }

  if (step === 'consent') {
    return (
      <>
        {mediaError && (
          <main className="page-shell">
            <p className="error-text notice" role="alert">{mediaError}</p>
            <button className="button secondary" onClick={() => setMediaError('')}>Dismiss</button>
          </main>
        )}
        <ConsentModal busy={busy} onBegin={begin} onClose={() => navigate('/')} />
      </>
    )
  }

  const currentSpeaker = conversation.phase === 'ai_speaking'
    ? 'AI interviewer is speaking'
    : conversation.phase === 'listening'
      ? conversation.interim ? 'You are speaking' : 'Listening to you'
      : conversation.phase === 'processing_answer' || conversation.phase === 'generating_response'
        ? 'Preparing a response'
        : conversation.phase === 'paused'
          ? 'Interview paused'
          : conversation.phase === 'error'
            ? 'Needs attention'
            : 'Interview ready'

  return (
    <main className="live-interview">
      <header className="live-header">
        <button className="live-exit" onClick={endInterview}>← End interview</button>
        <div className="live-title">
          <BrandMark size={30} />
          <div><strong>AI VIDEO INTERVIEW</strong><small>Private practice session</small></div>
        </div>
        <div className="live-status">
          <span className={`connection-indicator ${connected ? 'connected' : ''}`} />
          {connected ? 'Connected' : 'Reconnecting'}
          <Timer startedAt={startedAt} />
        </div>
      </header>

      <div className="live-main">
        <section className="live-call">
          <div className="live-call-heading">
            <div>
              <span className="eyebrow">INTERVIEWER · VIVA AI</span>
              <h1>Take your time, {user?.full_name?.split(' ')[0] || 'there'}.</h1>
            </div>
            <span className="live-progress">QUESTION {questionNumber} / 5</span>
          </div>

          <section className="video-stage" aria-label="Live interview video">
            <article className="ai-video-tile">
              <div className={`ai-avatar ${conversation.phase === 'ai_speaking' ? 'avatar-speaking' : ''}`}>
                <span className="avatar-halo" />
                <span className="avatar-face"><i /><i /><b /></span>
              </div>
              <div className="video-nameplate">
                <span className={`voice-dot ${conversation.phase === 'ai_speaking' ? 'voice-active' : ''}`} />
                AI Interviewer
              </div>
              <span className="tile-label-top">AI INTERVIEWER · ANIMATED AVATAR</span>
              {conversation.phase === 'ai_speaking' && <span className="speaking-rings" aria-hidden="true" />}
            </article>

            <article className="candidate-video-tile">
              <video
                ref={setVideoElement}
                autoPlay
                playsInline
                muted
                aria-label="Your live camera preview"
                className={!cameraOn ? 'video-disabled' : ''}
              />
              {!cameraOn && (
                <div className="video-placeholder">
                  <span>{user?.full_name?.slice(0, 1)?.toUpperCase() || 'Y'}</span>
                  <p>Camera is off</p>
                </div>
              )}
              <div className="video-nameplate">
                <span className={`voice-dot ${conversation.phase === 'listening' && conversation.interim ? 'voice-active' : ''}`} />
                {user?.full_name || 'You'}
                {!micOn && <span className="muted-label"> · muted</span>}
              </div>
              <span className="tile-label-top">YOU · LIVE PREVIEW</span>
            </article>
          </section>

          <div className="interview-state" role="status">
            <span className={`state-pulse state-${conversation.phase}`} />
            <span>{currentSpeaker}</span>
            {!conversation.recognitionSupported && conversation.phase === 'listening' && (
              <small>Automatic voice-activity capture · transcription appears after you finish speaking</small>
            )}
          </div>

          {mediaError && (
            <div className="live-error" role="alert">
              <span>{mediaError}</span>
              <button className="button secondary small-button" onClick={retryDevices}>Retry camera &amp; mic</button>
            </div>
          )}
          {(conversation.error || viva.error) && (
            <div className="live-error" role="alert">
              <span>{conversation.error || viva.error}</span>
              <button className="button secondary small-button" onClick={retryConversation}>Retry</button>
            </div>
          )}

          {cueWarning && (
            <div className="cue-warning" role="status">
              <strong>Camera cue</strong><span>{cueWarning} The cue is approximate and is only shared with your teacher.</span>
              <button aria-label="Dismiss camera cue" onClick={dismissWarning}>×</button>
            </div>
          )}
          {monitorStatus === 'unavailable' && cameraConsent && (
            <p className="monitor-note">Optional local camera cue checking is unavailable. Your live interview can continue.</p>
          )}

          <section className="live-question" aria-live="polite">
            <span className="eyebrow">{assessmentTitle ? `ASSESSMENT: ${assessmentTitle.toUpperCase()}` : 'CURRENT QUESTION'}</span>
            <h2>{viva.currentQuestion?.question_text || 'The interviewer is preparing the next question.'}</h2>
            <button
              className="live-control repeat-question"
              onClick={() => conversation.repeat(viva.currentQuestion?.question_text)}
              disabled={!conversation.canRepeat || !viva.currentQuestion?.question_text}
            >
              ↻ Repeat question aloud
            </button>
          </section>

          {conversation.captionsVisible && (
            <section className="live-caption" aria-live="polite" aria-label="Live caption">
              <span>{conversation.phase === 'ai_speaking' ? 'AI Interviewer' : 'You'}</span>
              <p>{conversation.phase === 'listening'
                ? conversation.interim || 'Your microphone is ready. Speak naturally when you are ready.'
                : conversation.messages.at(-1)?.text || 'Captions will appear here as the conversation continues.'}</p>
            </section>
          )}

          <div className="device-settings">
            {devices.cameras.length > 1 && (
              <label>
                Camera
                <select value={cameraId} onChange={(event) => void changeDevice('camera', event.target.value)}>
                  {devices.cameras.map((device, index) => (
                    <option value={device.deviceId} key={device.deviceId}>{device.label || `Camera ${index + 1}`}</option>
                  ))}
                </select>
              </label>
            )}
            {devices.microphones.length > 1 && (
              <label>
                Microphone
                <select value={microphoneId} onChange={(event) => void changeDevice('microphone', event.target.value)}>
                  {devices.microphones.map((device, index) => (
                    <option value={device.deviceId} key={device.deviceId}>{device.label || `Microphone ${index + 1}`}</option>
                  ))}
                </select>
              </label>
            )}
          </div>

          <footer className="live-controls" aria-label="Interview controls">
            <button className={`live-control ${!micOn ? 'control-off' : ''}`} onClick={toggleMicrophone}>
              <span>{micOn ? '🎙' : '🔇'}</span>{micOn ? 'Mute mic' : 'Unmute mic'}
            </button>
            <button className={`live-control ${!cameraOn ? 'control-off' : ''}`} onClick={toggleCamera}>
              <span>{cameraOn ? '▣' : '□'}</span>{cameraOn ? 'Camera on' : 'Camera off'}
            </button>
            <button className={`live-control ${conversation.speakerMuted ? 'control-off' : ''}`} onClick={conversation.toggleSpeaker}>
              <span>{conversation.speakerMuted ? '🔈' : '🔊'}</span>{conversation.speakerMuted ? 'Unmute audio' : 'Mute audio'}
            </button>
            <button className="live-control" onClick={() => conversation.setCaptionsVisible((visible) => !visible)}>
              <span>CC</span>{conversation.captionsVisible ? 'Hide captions' : 'Show captions'}
            </button>
            {conversation.phase === 'ai_speaking' && (
              <button className="live-control" onClick={conversation.interrupt}>Interrupt</button>
            )}
            {['ai_speaking', 'listening'].includes(conversation.phase) && (
              <button className="live-control" onClick={conversation.pause}>Pause</button>
            )}
            {conversation.phase === 'paused' && (
              <button className="live-control" onClick={conversation.resume}>Resume</button>
            )}
            <button className="live-control live-end" onClick={endInterview}><span>×</span>End call</button>
          </footer>
          <p className="live-privacy">
            Your camera video is shown only in this browser and is not sent to the AI. Browser live speech recognition may use the browser's speech service; when unavailable, audio is sent to your configured backend transcription provider.
          </p>
        </section>

        <aside className="conversation-panel" aria-label="Interview transcript">
          <header>
            <div><span className="eyebrow">LIVE TRANSCRIPT</span><h2>Conversation</h2></div>
            <span className="transcript-count">{conversation.messages.length}</span>
          </header>
          <div
            className="conversation-list"
            ref={transcriptRef}
            role="log"
            aria-live="polite"
            onScroll={(event) => {
              const element = event.currentTarget
              shouldAutoScrollRef.current =
                element.scrollHeight - element.scrollTop - element.clientHeight < 48
            }}
          >
            {conversation.messages.length === 0 && (
              <p className="conversation-empty">Your interview transcript will appear here as you speak with the interviewer.</p>
            )}
            {conversation.messages.map((message) => (
              <article className={`conversation-message ${message.speaker}`} key={message.id}>
                <div>
                  <strong>{message.speaker === 'ai' ? 'AI Interviewer' : 'You'}</strong>
                  <time dateTime={new Date(message.at).toISOString()}>
                    {String(Math.floor((message.at - startedAt) / 60000)).padStart(2, '0')}:
                    {String(Math.floor(((message.at - startedAt) % 60000) / 1000)).padStart(2, '0')}
                  </time>
                </div>
                <p>{message.text}</p>
              </article>
            ))}
            {conversation.phase === 'listening' && conversation.interim && (
              <article className="conversation-message candidate interim-message">
                <div><strong>You · live caption</strong><span className="interim-dot" /></div>
                <p>{conversation.interim}</p>
              </article>
            )}
          </div>
          <footer className="transcript-footer">
            <span className={`connection-indicator ${connected ? 'connected' : ''}`} />
            {connected ? 'Conversation saved with interview results' : 'Connection lost · answers cannot be saved'}
          </footer>
        </aside>
      </div>
    </main>
  )
}
