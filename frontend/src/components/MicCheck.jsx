import { useCallback, useEffect, useRef, useState } from 'react'
import { getMicCheckStateMessage, calculateAudioLevel } from '../utils/micCheckHelpers'

export default function MicCheck({ onReadyChange, onBeforeBeginRef }) {
  const [status, setStatus] = useState('not_tested')
  const [errorDetails, setErrorDetails] = useState('')
  const [level, setLevel] = useState(0)

  const streamRef = useRef(null)
  const audioContextRef = useRef(null)
  const animFrameRef = useRef(null)
  const autoDoneTimerRef = useRef(null)

  const cleanup = useCallback(() => {
    if (autoDoneTimerRef.current) {
      clearTimeout(autoDoneTimerRef.current)
      autoDoneTimerRef.current = null
    }
    if (animFrameRef.current) {
      cancelAnimationFrame(animFrameRef.current)
      animFrameRef.current = null
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => {
        try {
          track.stop()
        } catch {
          // ignore
        }
      })
      streamRef.current = null
    }
    if (audioContextRef.current) {
      try {
        if (audioContextRef.current.state !== 'closed') {
          audioContextRef.current.close().catch(() => {})
        }
      } catch {
        // ignore
      }
      audioContextRef.current = null
    }
    setLevel(0)
  }, [])

  useEffect(() => {
    if (onBeforeBeginRef) {
      onBeforeBeginRef.current = cleanup
    }
    return () => {
      if (onBeforeBeginRef) {
        onBeforeBeginRef.current = null
      }
    }
  }, [cleanup, onBeforeBeginRef])

  useEffect(() => {
    return () => {
      cleanup()
    }
  }, [cleanup])

  const finishTesting = useCallback(() => {
    cleanup()
    setStatus('ready')
    onReadyChange?.(true)
  }, [cleanup, onReadyChange])

  const testMicrophone = async () => {
    cleanup()
    setErrorDetails('')

    if (!navigator?.mediaDevices?.getUserMedia) {
      setStatus('unsupported')
      onReadyChange?.(false)
      return
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      })
      streamRef.current = stream

      setStatus('testing')
      onReadyChange?.(true)

      const AudioCtx = window.AudioContext || window.webkitAudioContext
      if (AudioCtx) {
        const audioCtx = new AudioCtx()
        audioCtx.resume?.().catch(() => {})
        audioContextRef.current = audioCtx
        const source = audioCtx.createMediaStreamSource(stream)
        const analyser = audioCtx.createAnalyser()
        analyser.fftSize = 256
        source.connect(analyser)
        const dataArray = new Uint8Array(analyser.frequencyBinCount)

        const updateMeter = () => {
          if (!streamRef.current) return
          analyser.getByteFrequencyData(dataArray)
          const lvl = calculateAudioLevel(dataArray)
          setLevel(lvl)
          animFrameRef.current = requestAnimationFrame(updateMeter)
        }
        updateMeter()
      }

      autoDoneTimerRef.current = setTimeout(() => {
        finishTesting()
      }, 5000)
    } catch (err) {
      cleanup()
      onReadyChange?.(false)

      if (err.name === 'NotAllowedError' || err.name === 'SecurityError') {
        setStatus('permission_denied')
      } else if (err.name === 'NotFoundError' || err.name === 'DevicesNotFoundError') {
        setStatus('unavailable')
      } else {
        setStatus('error')
        setErrorDetails(err.message || 'Microphone access failed.')
      }
    }
  }

  const isReady = status === 'ready'
  const isTesting = status === 'testing'
  const message = getMicCheckStateMessage(status, errorDetails)

  return (
    <div
      className="mic-check-card"
      style={{
        margin: '16px 0',
        padding: '16px',
        background: '#f8f6f2',
        borderRadius: '8px',
        border: isReady
          ? '1px solid #7baf83'
          : status.includes('denied') || status.includes('unavailable') || status.includes('error')
            ? '1px solid #e2a89d'
            : '1px solid #ded9d0',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
        <span className="eyebrow" style={{ margin: 0 }}>MICROPHONE CHECK</span>
        <span className={`status-tag ${isReady ? 'completed' : isTesting ? 'in_progress' : ''}`}>
          {isReady ? 'Ready' : isTesting ? 'Testing' : status === 'not_tested' ? 'Not tested' : 'Attention'}
        </span>
      </div>

      <p
        style={{
          margin: '6px 0',
          fontSize: '13px',
          color: isReady
            ? '#41765f'
            : status.includes('denied') || status.includes('unavailable') || status.includes('error')
              ? '#a54439'
              : 'inherit',
        }}
      >
        {message}
      </p>

      {isTesting && (
        <div style={{ margin: '10px 0' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: '#687078', marginBottom: '4px' }}>
            <span>Input volume</span>
            <span>{level}%</span>
          </div>
          <div style={{ width: '100%', height: '8px', background: '#e0ded8', borderRadius: '4px', overflow: 'hidden' }}>
            <div
              style={{
                width: `${Math.max(level, 4)}%`,
                height: '100%',
                background: level > 12 ? '#41765f' : '#bc603e',
                transition: 'width 0.1s ease',
              }}
            />
          </div>
        </div>
      )}

      <div style={{ marginTop: '10px', display: 'flex', gap: '8px', alignItems: 'center' }}>
        {status === 'not_tested' && (
          <button type="button" className="button secondary" onClick={testMicrophone} style={{ padding: '8px 14px', fontSize: '13px' }}>
            Check microphone
          </button>
        )}

        {isTesting && (
          <button type="button" className="button secondary" onClick={finishTesting} style={{ padding: '8px 14px', fontSize: '13px' }}>
            Done testing
          </button>
        )}

        {isReady && (
          <button type="button" className="text-button" onClick={testMicrophone} style={{ fontSize: '12px' }}>
            Test again
          </button>
        )}

        {(status === 'permission_denied' || status === 'unavailable' || status === 'error') && (
          <button type="button" className="button secondary" onClick={testMicrophone} style={{ padding: '8px 14px', fontSize: '13px' }}>
            Retry check
          </button>
        )}
      </div>
    </div>
  )
}
