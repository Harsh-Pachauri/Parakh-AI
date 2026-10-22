import { useCallback, useEffect, useRef, useState } from 'react'

const TRANSITIONS = {
  initializing: ['ready', 'error', 'ended'],
  ready: ['ai_speaking', 'listening', 'error', 'ended'],
  ai_speaking: ['listening', 'paused', 'error', 'ended'],
  listening: ['processing_answer', 'ai_speaking', 'paused', 'error', 'ended'],
  processing_answer: ['generating_response', 'error', 'ended'],
  generating_response: ['ai_speaking', 'listening', 'error', 'ended'],
  paused: ['ai_speaking', 'listening', 'ended', 'error'],
  error: ['listening', 'ai_speaking', 'processing_answer', 'ended'],
  ended: [],
}

const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition
const SILENCE_MS = 2800

export function transitionInterview(current, next) {
  if (!TRANSITIONS[current]?.includes(next)) {
    throw new Error(`Invalid interview transition: ${current} -> ${next}`)
  }
  return next
}

export default function useLiveInterview({
  stream,
  microphoneEnabled = true,
  onTurn,
  onAudioTurn,
  onError,
  onComplete,
}) {
  const [phase, setPhase] = useState('initializing')
  const [interim, setInterim] = useState('')
  const [messages, setMessages] = useState([])
  const [recognitionSupported, setRecognitionSupported] = useState(Boolean(Recognition))
  const [captionsVisible, setCaptionsVisible] = useState(true)
  const [speakerMuted, setSpeakerMuted] = useState(false)
  const [error, setError] = useState('')
  const phaseRef = useRef(phase)
  const recognitionRef = useRef(null)
  const finalTranscriptRef = useRef('')
  const committedTranscriptRef = useRef('')
  const interimRef = useRef('')
  const silenceTimerRef = useRef(null)
  const retryTranscriptRef = useRef('')
  const retryAudioRef = useRef(null)
  const processingRef = useRef(false)
  const onTurnRef = useRef(onTurn)
  const onAudioTurnRef = useRef(onAudioTurn)
  const onErrorRef = useRef(onError)
  const onCompleteRef = useRef(onComplete)
  const streamRef = useRef(stream)
  const audioContextRef = useRef(null)
  const rafRef = useRef(null)
  const recorderRef = useRef(null)
  const recorderChunksRef = useRef([])
  const candidateMessagePendingRef = useRef(false)
  const cancelSpeechRef = useRef(false)
  const microphoneEnabledRef = useRef(microphoneEnabled)
  const requestIdRef = useRef(0)
  const speakRef = useRef(null)
  const recorderFallbackRef = useRef(null)
  const disposedRef = useRef(false)

  onTurnRef.current = onTurn
  onAudioTurnRef.current = onAudioTurn
  onErrorRef.current = onError
  onCompleteRef.current = onComplete
  streamRef.current = stream

  const move = useCallback((next) => {
    if (disposedRef.current) return
    phaseRef.current = transitionInterview(phaseRef.current, next)
    setPhase(next)
  }, [])

  const clearSilenceTimer = useCallback(() => {
    if (silenceTimerRef.current) window.clearTimeout(silenceTimerRef.current)
    silenceTimerRef.current = null
  }, [])

  const stopRecognition = useCallback(() => {
    clearSilenceTimer()
    const recognition = recognitionRef.current
    recognitionRef.current = null
    if (recognition) {
      recognition.onend = null
      recognition.onerror = null
      recognition.onresult = null
      try { recognition.stop() } catch { /* It may already have ended. */ }
    }
  }, [clearSilenceTimer])

  const appendMessage = useCallback((speaker, text) => {
    const content = text.trim()
    if (!content) return
    setMessages((items) => [...items, { id: crypto.randomUUID(), speaker, text: content, at: Date.now() }])
  }, [])

  const finishAnswer = useCallback(async (transcript, audioBlob = null, isRetry = false) => {
    if (disposedRef.current || processingRef.current || phaseRef.current !== 'listening') return
    const candidateText = transcript.trim()
    if (!candidateText && !audioBlob) return
    processingRef.current = true
    stopRecognition()
    if (phaseRef.current === 'listening') move('processing_answer')
    setInterim('')
    interimRef.current = ''
    retryTranscriptRef.current = candidateText
    retryAudioRef.current = audioBlob
    candidateMessagePendingRef.current = true
    const requestId = ++requestIdRef.current
    if (candidateText && !isRetry) appendMessage('candidate', candidateText)
    move('generating_response')
    setError('')

    try {
      const response = audioBlob
        ? await onAudioTurnRef.current(audioBlob)
        : await onTurnRef.current(candidateText)
      if (disposedRef.current || requestId !== requestIdRef.current || phaseRef.current === 'ended') return
      if (!candidateText && response.transcript && candidateMessagePendingRef.current) {
        appendMessage('candidate', response.transcript)
      }
      candidateMessagePendingRef.current = false
      retryTranscriptRef.current = ''
      retryAudioRef.current = null
      processingRef.current = false
      if (response.completed) {
        appendMessage('ai', response.interviewer_text)
        move('ended')
        onCompleteRef.current?.()
        return
      }
      appendMessage('ai', response.interviewer_text)
      await speakRef.current(response.interviewer_text)
    } catch (cause) {
      if (disposedRef.current || requestId !== requestIdRef.current || phaseRef.current === 'ended') return
      processingRef.current = false
      const message = cause.userMessage || cause.message || 'The answer could not be processed. Retry or try speaking again.'
      setError(message)
      onErrorRef.current?.(message)
      move('error')
    }
  }, [appendMessage, move, stopRecognition])

  const scheduleSilence = useCallback(() => {
    if (disposedRef.current) return
    clearSilenceTimer()
    silenceTimerRef.current = window.setTimeout(() => {
      if (disposedRef.current) return
      const transcript = [finalTranscriptRef.current, interimRef.current].filter(Boolean).join(' ').trim()
      if (transcript) void finishAnswer(transcript)
    }, SILENCE_MS)
  }, [clearSilenceTimer, finishAnswer])

  const startBrowserRecognition = useCallback(() => {
    if (disposedRef.current || !Recognition || phaseRef.current !== 'listening') return
    const recognition = new Recognition()
    recognition.continuous = true
    recognition.interimResults = true
    recognition.lang = 'en-US'
    recognitionRef.current = recognition
    recognition.onresult = (event) => {
      if (disposedRef.current) return
      const finalParts = []
      const interimParts = []
      for (let index = 0; index < event.results.length; index += 1) {
        const result = event.results[index]
        const text = result[0]?.transcript?.trim()
        if (!text) continue
        if (result.isFinal) finalParts.push(text)
        else interimParts.push(text)
      }
      finalTranscriptRef.current = [committedTranscriptRef.current, finalParts.join(' ')]
        .filter(Boolean)
        .join(' ')
      interimRef.current = interimParts.join(' ')
      setInterim(interimRef.current)
      if (finalTranscriptRef.current || interimRef.current) scheduleSilence()
    }
    recognition.onerror = (event) => {
      if (disposedRef.current) return
      if (event.error === 'no-speech' || event.error === 'aborted') return
      if (event.error === 'network' || event.error === 'service-not-allowed') {
        recognitionRef.current = null
        recognition.onend = null
        recognition.onerror = null
        recognition.onresult = null
        try { recognition.stop() } catch { /* The recognition service may already be disconnected. */ }
        setRecognitionSupported(false)
        setError('Browser live transcription is unavailable. Switching to automatic audio capture; captions will appear after each answer is transcribed.')
        window.setTimeout(() => recorderFallbackRef.current?.(), 0)
        return
      }
      const message = event.error === 'not-allowed'
        ? 'Speech recognition permission was denied. Allow microphone access and retry.'
        : `Live speech recognition stopped (${event.error}). Retry, or use a supported Chrome/Edge browser.`
      setError(message)
      onErrorRef.current?.(message)
      if (phaseRef.current === 'listening') move('error')
    }
    recognition.onend = () => {
      if (disposedRef.current) return
      if (recognitionRef.current !== recognition) return
      recognitionRef.current = null
      if (phaseRef.current === 'listening') {
        committedTranscriptRef.current = finalTranscriptRef.current
        window.setTimeout(() => {
          if (!disposedRef.current && phaseRef.current === 'listening') startBrowserRecognition()
        }, 200)
      }
    }
    try {
      recognition.start()
    } catch (cause) {
      if (disposedRef.current) return
      recognitionRef.current = null
      if (cause.name !== 'NotAllowedError') {
        setRecognitionSupported(false)
        setError('Live speech recognition could not start. Switching to automatic audio capture.')
        window.setTimeout(() => recorderFallbackRef.current?.(), 0)
        return
      }
      setError(cause.message || 'Could not start browser speech recognition. Retry the microphone.')
      move('error')
    }
  }, [move, scheduleSilence])

  const startRecorderFallback = useCallback(() => {
    if (disposedRef.current || phaseRef.current !== 'listening') return
    const mediaStream = streamRef.current
    if (!mediaStream || !window.MediaRecorder) {
      const message = 'This browser has no live speech recognition or audio recording support. Use a current version of Chrome or Edge.'
      setError(message)
      onErrorRef.current?.(message)
      move('error')
      return
    }
    const audioTracks = mediaStream.getAudioTracks().filter((track) => track.enabled && track.readyState === 'live')
    if (!audioTracks.length) return
    let context
    try {
      context = new AudioContext()
      audioContextRef.current = context
      if (context.state === 'suspended') {
        void context.resume().catch(() => {
          setError('Automatic voice detection could not resume audio processing. Retry microphone access.')
          move('error')
        })
      }
      const analyser = context.createAnalyser()
      analyser.fftSize = 512
      context.createMediaStreamSource(new MediaStream(audioTracks)).connect(analyser)
      const samples = new Uint8Array(analyser.fftSize)
      let speaking = false
      let lastVoiceAt = 0
      let recorder = null
      recorderChunksRef.current = []

      const sample = () => {
        if (disposedRef.current || phaseRef.current !== 'listening') return
        analyser.getByteTimeDomainData(samples)
        const rms = Math.sqrt(samples.reduce((total, value) => {
          const normalized = (value - 128) / 128
          return total + normalized * normalized
        }, 0) / samples.length)
        if (rms > 0.025) {
          lastVoiceAt = Date.now()
          if (!speaking) {
            speaking = true
            const audioStream = new MediaStream(audioTracks)
            const mimeType = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4']
              .find((type) => MediaRecorder.isTypeSupported(type))
            recorder = new MediaRecorder(audioStream, mimeType ? { mimeType } : undefined)
            recorderChunksRef.current = []
            recorder.ondataavailable = (event) => {
              if (event.data.size) recorderChunksRef.current.push(event.data)
            }
            recorder.onstop = () => {
              const blob = new Blob(recorderChunksRef.current, { type: recorder.mimeType || 'audio/webm' })
              if (blob.size) void finishAnswer('', blob)
            }
            recorder.start(250)
            recorderRef.current = recorder
          }
        } else if (speaking && Date.now() - lastVoiceAt >= SILENCE_MS) {
          speaking = false
          recorder?.stop()
        }
        if (speaking) setInterim('Listening…')
        rafRef.current = window.requestAnimationFrame(sample)
      }
      rafRef.current = window.requestAnimationFrame(sample)
    } catch (cause) {
      setError(`Automatic audio capture could not start: ${cause.message || 'check microphone permissions.'}`)
      move('error')
    }
  }, [finishAnswer, move])
  recorderFallbackRef.current = startRecorderFallback

  const listen = useCallback((preserveTranscript = false) => {
    if (disposedRef.current) return
    clearSilenceTimer()
    const hasEnabledMicrophone = streamRef.current?.getAudioTracks().some(
      (track) => track.enabled && track.readyState === 'live',
    )
    if (!hasEnabledMicrophone) {
      if (phaseRef.current !== 'paused') move('paused')
      return
    }
    if (!preserveTranscript) {
      finalTranscriptRef.current = ''
      committedTranscriptRef.current = ''
      interimRef.current = ''
    }
    processingRef.current = false
    setInterim('')
    setError('')
    if (phaseRef.current !== 'listening') move('listening')
    window.setTimeout(() => {
      if (disposedRef.current || phaseRef.current !== 'listening') return
      if (Recognition) startBrowserRecognition()
      else startRecorderFallback()
    }, 450)
  }, [clearSilenceTimer, move, startBrowserRecognition, startRecorderFallback])

  const speak = useCallback((text) => new Promise((resolve, reject) => {
    stopRecognition()
    if (rafRef.current) window.cancelAnimationFrame(rafRef.current)
    if (audioContextRef.current) {
      void audioContextRef.current.close()
      audioContextRef.current = null
    }
    if (recorderRef.current?.state === 'recording') recorderRef.current.stop()
    setInterim('')
    if (!text || !window.speechSynthesis || typeof SpeechSynthesisUtterance === 'undefined') {
      const message = 'Text-to-speech is unavailable in this browser. Enable browser speech synthesis to hear the interviewer.'
      setError(message)
      move('error')
      reject(new Error(message))
      return
    }
    move('ai_speaking')
    if (speakerMuted) {
      listen()
      resolve()
      return
    }
    window.speechSynthesis.cancel()
    const utterance = new SpeechSynthesisUtterance(text)
    utterance.rate = 0.96
    utterance.onend = () => {
      if (disposedRef.current) return resolve()
      cancelSpeechRef.current = false
      if (phaseRef.current === 'ai_speaking') listen()
      resolve()
    }
    utterance.onerror = (event) => {
      if (disposedRef.current) return resolve()
      if (cancelSpeechRef.current) {
        cancelSpeechRef.current = false
        resolve()
        return
      }
      if (phaseRef.current === 'ended') return resolve()
      const message = `Interviewer audio could not be played (${event.error || 'speech error'}). Use Hear question to retry.`
      setError(message)
      move('error')
      reject(new Error(message))
    }
    window.speechSynthesis.speak(utterance)
  }), [listen, move, speakerMuted, stopRecognition])
  speakRef.current = speak

  const ask = useCallback(async (text) => {
    if (disposedRef.current || !text || phaseRef.current === 'ended') return
    appendMessage('ai', text)
    try {
      await speak(text)
    } catch (cause) {
      setError(cause.message)
    }
  }, [appendMessage, speak])

  const repeat = useCallback((text) => {
    if (
      disposedRef.current
      || !text
      || phaseRef.current === 'ended'
      || phaseRef.current === 'listening'
      || phaseRef.current === 'processing_answer'
      || phaseRef.current === 'generating_response'
      || retryTranscriptRef.current
      || retryAudioRef.current
    ) return
    void speak(text).catch((cause) => setError(cause.message))
  }, [speak])

  const retry = useCallback(() => {
    const text = retryTranscriptRef.current
    const audioBlob = retryAudioRef.current
    if (text || audioBlob) {
      move('listening')
      void finishAnswer(text, audioBlob, true)
    } else {
      listen()
    }
  }, [finishAnswer, listen, move])

  const interrupt = useCallback(() => {
    if (phaseRef.current !== 'ai_speaking') return
    cancelSpeechRef.current = true
    window.speechSynthesis?.cancel()
    listen()
  }, [listen])

  const toggleSpeaker = useCallback(() => {
    const muted = !speakerMuted
    setSpeakerMuted(muted)
    if (muted && phaseRef.current === 'ai_speaking') {
      cancelSpeechRef.current = true
      window.speechSynthesis?.cancel()
      listen()
    }
  }, [listen, speakerMuted])

  const pause = useCallback(() => {
    if (phaseRef.current === 'ai_speaking') {
      window.speechSynthesis?.pause()
      move('paused')
    } else if (phaseRef.current === 'listening') {
      if (Recognition) {
        committedTranscriptRef.current = [
          finalTranscriptRef.current,
          interimRef.current,
        ].filter(Boolean).join(' ')
        finalTranscriptRef.current = committedTranscriptRef.current
        interimRef.current = ''
      }
      stopRecognition()
      if (rafRef.current) window.cancelAnimationFrame(rafRef.current)
      if (recorderRef.current?.state === 'recording') recorderRef.current.stop()
      move('paused')
    }
  }, [move, stopRecognition])

  const resume = useCallback(() => {
    if (phaseRef.current !== 'paused') return
    if (window.speechSynthesis?.paused) {
      window.speechSynthesis.resume()
      move('ai_speaking')
    } else {
      listen(true)
    }
  }, [listen, move])

  const end = useCallback(() => {
    requestIdRef.current += 1
    processingRef.current = true
    stopRecognition()
    if (rafRef.current) window.cancelAnimationFrame(rafRef.current)
    if (audioContextRef.current) {
      void audioContextRef.current.close()
      audioContextRef.current = null
    }
    if (recorderRef.current?.state === 'recording') recorderRef.current.stop()
    window.speechSynthesis?.cancel()
    if (phaseRef.current !== 'ended') move('ended')
    setInterim('')
  }, [move, stopRecognition])

  useEffect(() => {
    disposedRef.current = false
    return () => {
      disposedRef.current = true
      requestIdRef.current += 1
      stopRecognition()
      if (rafRef.current) window.cancelAnimationFrame(rafRef.current)
      if (audioContextRef.current) void audioContextRef.current.close()
      window.speechSynthesis?.cancel()
    }
  }, [stopRecognition])

  useEffect(() => {
    if (phaseRef.current === 'initializing') move('ready')
  }, [move, phase])

  useEffect(() => {
    if (disposedRef.current) return
    if (microphoneEnabledRef.current === microphoneEnabled) return
    microphoneEnabledRef.current = microphoneEnabled
    if (!microphoneEnabled && phaseRef.current === 'listening') {
      stopRecognition()
      if (rafRef.current) window.cancelAnimationFrame(rafRef.current)
      if (recorderRef.current?.state === 'recording') recorderRef.current.stop()
      move('paused')
    } else if (microphoneEnabled && phaseRef.current === 'paused') {
      listen()
    }
  }, [listen, microphoneEnabled, move, stopRecognition])

  return {
    phase,
    interim,
    messages,
    recognitionSupported,
    captionsVisible,
    setCaptionsVisible,
    speakerMuted,
    setSpeakerMuted,
    toggleSpeaker,
    error,
    setError,
    ask,
    repeat,
    canRepeat: !retryTranscriptRef.current
      && !retryAudioRef.current
      && !['listening', 'processing_answer', 'generating_response', 'ended'].includes(phase),
    listen,
    retry,
    interrupt,
    pause,
    resume,
    end,
  }
}
