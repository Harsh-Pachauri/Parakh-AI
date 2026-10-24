import test from 'node:test'
import assert from 'node:assert/strict'
import { getMicCheckStateMessage, calculateAudioLevel } from './micCheckHelpers.js'

test('getMicCheckStateMessage returns accurate messages for all states', () => {
  assert.match(getMicCheckStateMessage('not_tested'), /not been checked/)
  assert.match(getMicCheckStateMessage('testing'), /Microphone active/)
  assert.match(getMicCheckStateMessage('ready'), /Microphone ready/)
  assert.match(getMicCheckStateMessage('permission_denied'), /permission was denied/)
  assert.match(getMicCheckStateMessage('unavailable'), /No microphone found/)
  assert.match(getMicCheckStateMessage('unsupported'), /MediaDevices/)
  assert.equal(getMicCheckStateMessage('error', 'Device busy'), 'Device busy')
})

test('calculateAudioLevel computes normalized percentage from frequency data', () => {
  // Empty or null
  assert.equal(calculateAudioLevel([]), 0)
  assert.equal(calculateAudioLevel(null), 0)

  // Silence
  const silence = new Uint8Array([0, 0, 0, 0])
  assert.equal(calculateAudioLevel(silence), 0)

  // Medium volume (average 64 / 128 = 50%)
  const medium = new Uint8Array([64, 64, 64, 64])
  assert.equal(calculateAudioLevel(medium), 50)

  // High volume (clamped at 100%)
  const loud = new Uint8Array([200, 255, 180, 220])
  assert.equal(calculateAudioLevel(loud), 100)
})
