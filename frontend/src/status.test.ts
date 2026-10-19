import { describe, expect, it } from 'vitest'
import { isFinished, severityRank, statusColor } from './status'

describe('status helpers', () => {
  it('uses a neutral color for unknown statuses', () => {
    expect(statusColor('model_generated')).toBe('#2563eb')
    expect(statusColor('something_else')).toBe('#6b7280')
  })

  it('ranks errors before warnings before info', () => {
    expect(severityRank('error')).toBeLessThan(severityRank('warning'))
    expect(severityRank('warning')).toBeLessThan(severityRank('info'))
    expect(severityRank('other')).toBeGreaterThan(severityRank('info'))
  })

  it('detects finished runs', () => {
    expect(isFinished('succeeded')).toBe(true)
    expect(isFinished('blocked')).toBe(true)
    expect(isFinished('running')).toBe(false)
  })
})
