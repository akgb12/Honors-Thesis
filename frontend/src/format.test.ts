import { describe, expect, it } from 'vitest'
import {
  fileKind,
  formatBytes,
  formatCost,
  formatDuration,
  relativeTime,
  scoreTone,
  shortElementId,
} from './format'

describe('formatBytes', () => {
  it('scales units and trims digits', () => {
    expect(formatBytes(0)).toBe('0 B')
    expect(formatBytes(1536)).toBe('1.5 KB')
    expect(formatBytes(832851)).toBe('813 KB')
    expect(formatBytes(4377867)).toBe('4.2 MB')
  })

  it('rejects invalid input', () => {
    expect(formatBytes(-1)).toBe('–')
    expect(formatBytes(Number.NaN)).toBe('–')
  })
})

describe('relativeTime', () => {
  const now = Date.parse('2026-10-19T12:00:00Z')

  it('describes recent and older timestamps', () => {
    expect(relativeTime('2026-10-19T11:59:40Z', now)).toBe('just now')
    expect(relativeTime('2026-10-19T11:55:00Z', now)).toBe('5 minutes ago')
    expect(relativeTime('2026-10-19T09:00:00Z', now)).toBe('3 hours ago')
    expect(relativeTime('2026-10-17T12:00:00Z', now)).toBe('2 days ago')
  })

  it('handles invalid dates', () => {
    expect(relativeTime('not a date', now)).toBe('–')
  })
})

describe('formatDuration', () => {
  it('formats seconds and minutes', () => {
    expect(formatDuration(5_000)).toBe('5s')
    expect(formatDuration(72_000)).toBe('1m 12s')
    expect(formatDuration(-5)).toBe('0s')
  })
})

describe('formatCost', () => {
  it('formats zero, tiny and normal amounts', () => {
    expect(formatCost('0.000000')).toBe('$0.00')
    expect(formatCost('0.00421')).toBe('$0.0042')
    expect(formatCost(1.5)).toBe('$1.50')
    expect(formatCost('abc')).toBe('–')
  })
})

describe('scoreTone', () => {
  it('maps scores to tones', () => {
    expect(scoreTone(96.7)).toBe('success')
    expect(scoreTone(72)).toBe('warning')
    expect(scoreTone(43.3)).toBe('danger')
    expect(scoreTone(null)).toBe('warning')
  })
})

describe('fileKind and shortElementId', () => {
  it('classifies files', () => {
    expect(fileKind('Lecture1-Intro.tex')).toBe('tex')
    expect(fileKind('Figures/takejob.PDF')).toBe('pdf')
    expect(fileKind('Figures/cnn.png')).toBe('image')
    expect(fileKind('comment.sty')).toBe('style')
    expect(fileKind('README')).toBe('other')
  })

  it('shortens element ids', () => {
    expect(shortElementId('slide_04/figure_01')).toBe('figure_01')
    expect(shortElementId('slide_01')).toBe('slide_01')
  })
})
