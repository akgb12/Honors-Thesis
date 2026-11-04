import type { Anchor, Bbox } from './types'

export interface PageSize {
  widthPt: number
  heightPt: number
}

export interface ImageSize {
  width: number
  height: number
}

export interface Rect {
  x: number
  y: number
  width: number
  height: number
}

// PDF points have their origin bottom-left; image pixels have it top-left
export function pointToPixel(
  x: number,
  y: number,
  page: PageSize,
  image: ImageSize,
): { x: number; y: number } {
  return {
    x: (x * image.width) / page.widthPt,
    y: image.height - (y * image.height) / page.heightPt,
  }
}

export function bboxToRect(bbox: Bbox, page: PageSize, image: ImageSize): Rect {
  const topLeft = pointToPixel(bbox[0], bbox[3], page, image)
  const bottomRight = pointToPixel(bbox[2], bbox[1], page, image)
  return {
    x: topLeft.x,
    y: topLeft.y,
    width: bottomRight.x - topLeft.x,
    height: bottomRight.y - topLeft.y,
  }
}

export function anchorToPin(anchor: Anchor, page: PageSize, image: ImageSize) {
  return pointToPixel(anchor[0], anchor[1], page, image)
}
