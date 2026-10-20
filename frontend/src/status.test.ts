import { describe, expect, it } from 'vitest'
import {
  isFinished,
  needsAttention,
  severityRank,
  statusColor,
  statusGroup,
  statusLabel,
} from './status'

describe('status helpers', () => {
  it('uses a neutral style for unknown statuses', () => {
    expect(statusColor('model_generated')).toBe('#2563eb')
    expect(statusColor('something_else')).toBe('#64748b')
    expect(statusLabel('needs_description')).toBe('Needs description')
    expect(statusLabel('something_else')).toBe('Unknown')
  })

  it('folds deterministic into done', () => {
    expect(statusGroup('deterministic')).toBe('done')
    expect(statusGroup('failed')).toBe('failed')
  })

  it('flags elements that need attention', () => {
    expect(needsAttention('needs_review')).toBe(true)
    expect(needsAttention('needs_description')).toBe(true)
    expect(needsAttention('not_handled')).toBe(true)
    expect(needsAttention('done')).toBe(false)
    expect(needsAttention('model_generated')).toBe(false)
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
