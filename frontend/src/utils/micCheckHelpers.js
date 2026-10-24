export function getMicCheckStateMessage(status, errorDetails) {
  switch (status) {
    case 'not_tested':
      return 'Microphone has not been checked yet.'
    case 'testing':
      return 'Microphone active. Speak to test your audio input.'
    case 'ready':
      return 'Microphone ready! Device connected and input detected.'
    case 'permission_denied':
      return 'Microphone permission was denied. Please allow microphone access in your browser settings.'
    case 'unavailable':
      return 'No microphone found. Please connect an audio input device.'
    case 'unsupported':
      return 'Microphone check requires a modern browser supporting MediaDevices over HTTPS or localhost.'
    case 'error':
      return errorDetails || 'Could not initialize microphone. Please check your system audio settings.'
    default:
      return ''
  }
}

export function calculateAudioLevel(dataArray) {
  if (!dataArray || dataArray.length === 0) return 0
  let sum = 0
  for (let i = 0; i < dataArray.length; i++) {
    sum += dataArray[i]
  }
  const average = sum / dataArray.length
  return Math.min(100, Math.round((average / 128) * 100))
}
