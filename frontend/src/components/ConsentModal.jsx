import { useRef, useState } from 'react'
import MicCheck from './MicCheck'

export default function ConsentModal({ onBegin, busy }) {
  const [cameraConsent, setCameraConsent] = useState(false)
  const [retainAudio, setRetainAudio] = useState(false)
  const [micReady, setMicReady] = useState(false)
  const onBeforeBeginRef = useRef(null)

  const handleBegin = () => {
    if (onBeforeBeginRef.current) {
      onBeforeBeginRef.current()
    }
    onBegin(retainAudio, cameraConsent)
  }

  return (
    <div className="modal-backdrop" role="presentation">
      <section className="modal" role="dialog" aria-modal="true" aria-labelledby="consent-title">
        <span className="eyebrow">Before you begin</span>
        <h2 id="consent-title">Your voice, your choice</h2>
        <p>
          Your microphone is used for live speech recognition. Your finalized transcript and evaluation are saved with this interview. Browser speech recognition may use the browser's speech service. If unavailable, brief answer recordings are sent to the configured backend transcription service and are deleted after processing.
        </p>
        <p>
          Your live camera preview stays in this browser and is never sent to the AI. Optional local face cues are approximate and may create a teacher review flag; they do not determine your score.
        </p>

        <MicCheck onReadyChange={setMicReady} onBeforeBeginRef={onBeforeBeginRef} />

        <label className="consent-choice">
          <input
            type="checkbox"
            checked={cameraConsent}
            onChange={(event) => setCameraConsent(event.target.checked)}
          />{' '}
          Opt in to local camera cue checking for this practice session.
        </label>
        <label className="consent-choice">
          <input
            type="checkbox"
            checked={retainAudio}
            onChange={(event) => setRetainAudio(event.target.checked)}
          />{' '}
          Allow answer audio to be retained for teacher review.
        </label>
        <div className="modal-actions">
          <button
            className="button primary"
            onClick={handleBegin}
            disabled={busy || !micReady}
          >
            {busy ? 'Starting…' : !micReady ? 'Test microphone to begin' : 'Allow camera and begin'}
          </button>
        </div>
      </section>
    </div>
  )
}
