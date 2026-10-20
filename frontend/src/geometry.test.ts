import { describe, expect, it } from 'vitest'
import { anchorToPin, bboxToRect, pointToPixel } from './geometry'

const page = { widthPt: 360, heightPt: 270 }
const image = { width: 720, height: 540 }

describe('pointToPixel', () => {
  it('flips the vertical axis and scales by image size', () => {
    expect(pointToPixel(0, 0, page, image)).toEqual({ x: 0, y: 540 })
    expect(pointToPixel(360, 270, page, image)).toEqual({ x: 720, y: 0 })
    expect(pointToPixel(180, 135, page, image)).toEqual({ x: 360, y: 270 })
  })

  it('handles non-uniform scales', () => {
    const wide = { width: 360, height: 1080 }
    expect(pointToPixel(90, 67.5, page, wide)).toEqual({ x: 90, y: 810 })
  })
})

describe('bboxToRect', () => {
  it('returns a top-left rectangle in pixels', () => {
    const rect = bboxToRect([36, 27, 180, 135], page, image)
    expect(rect).toEqual({ x: 72, y: 270, width: 288, height: 216 })
  })
})

describe('anchorToPin', () => {
  it('converts an anchor to a pixel position', () => {
    expect(anchorToPin([90, 135], page, image)).toEqual({ x: 180, y: 270 })
  })
})
