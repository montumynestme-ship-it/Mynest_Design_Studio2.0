/**
 * AI-capture-only presentation styling for architectural openings.
 *
 * Deterministic/interactive rendering is the authoritative reference and must stay
 * byte-identical: when `aiRenderMode` is false these return the original values, so the
 * normal 3D viewer is unchanged. Only the AI base-capture / structural pass (aiRenderMode
 * true) gets a more legible window — a crisper, less-translucent glazed pane plus a thin
 * opaque frame ring — so the image-conditioned model can see and preserve the opening
 * instead of a near-invisible translucent sheet.
 *
 * This is a VISUAL/MATERIAL treatment ONLY. It never changes a window's geometry, position,
 * size, rotation, or supporting-wall relationship — the frame is drawn at the window's exact
 * existing location. It does not touch canonical geometry or the deterministic scene.
 */

/** The window's original interactive glazing opacity (kept for the non-AI viewer). */
export const WINDOW_PANE_OPACITY_INTERACTIVE = 0.45;
/** A crisper pane for the AI capture so the opening is not near-invisible against the wall. */
export const WINDOW_PANE_OPACITY_AI_CAPTURE = 0.82;
/** Thin opaque frame ring drawn around the window in the AI capture (metres). Not a
 * structural member — purely a visibility cue the image-conditioned model can lock onto. */
export const AI_WINDOW_FRAME_THICKNESS_M = 0.06;
/** A dark, wall-contrasting frame colour so the rectangle reads clearly in the capture. */
export const AI_WINDOW_FRAME_COLOR = '#43484f';

export interface WindowCaptureStyle {
  /** Glazed-pane opacity to use for this render. */
  paneOpacity: number;
  /** Whether to draw the thin opaque frame ring (AI capture only). */
  frame: boolean;
}

/**
 * Decide how a window's glazed pane/frame should be presented.
 *
 * @param aiRenderMode true for the AI base capture AND the structural wireframe pass
 *   (both are AI-capture inputs); false for the normal deterministic/interactive viewer.
 */
export function windowCaptureStyle(aiRenderMode: boolean): WindowCaptureStyle {
  return aiRenderMode
    ? { paneOpacity: WINDOW_PANE_OPACITY_AI_CAPTURE, frame: true }
    : { paneOpacity: WINDOW_PANE_OPACITY_INTERACTIVE, frame: false };
}
