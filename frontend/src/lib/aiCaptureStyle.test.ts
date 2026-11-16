import { describe, it, expect } from 'vitest';
import {
  windowCaptureStyle,
  WINDOW_PANE_OPACITY_INTERACTIVE,
  WINDOW_PANE_OPACITY_AI_CAPTURE,
  AI_WINDOW_FRAME_THICKNESS_M,
  AI_WINDOW_FRAME_COLOR,
} from './aiCaptureStyle';

describe('windowCaptureStyle — AI-capture-only window legibility', () => {
  it('leaves the interactive/deterministic viewer unchanged (no frame, original opacity)', () => {
    const s = windowCaptureStyle(false);
    expect(s.frame).toBe(false);
    expect(s.paneOpacity).toBe(WINDOW_PANE_OPACITY_INTERACTIVE);
    expect(s.paneOpacity).toBe(0.45); // the pre-existing interactive glazing opacity
  });

  it('makes the window more legible in the AI capture (crisper pane + frame)', () => {
    const s = windowCaptureStyle(true);
    expect(s.frame).toBe(true);
    expect(s.paneOpacity).toBe(WINDOW_PANE_OPACITY_AI_CAPTURE);
  });

  it('the AI-capture pane is strictly MORE opaque than the interactive pane', () => {
    expect(WINDOW_PANE_OPACITY_AI_CAPTURE).toBeGreaterThan(WINDOW_PANE_OPACITY_INTERACTIVE);
    // still translucent glazing, not a solid wall
    expect(WINDOW_PANE_OPACITY_AI_CAPTURE).toBeLessThan(1);
  });

  it('exposes a positive, thin frame thickness and a dark frame colour', () => {
    expect(AI_WINDOW_FRAME_THICKNESS_M).toBeGreaterThan(0);
    expect(AI_WINDOW_FRAME_THICKNESS_M).toBeLessThan(0.15); // a thin cue, not a structural member
    expect(AI_WINDOW_FRAME_COLOR).toMatch(/^#[0-9a-fA-F]{6}$/);
  });

  it('is pure (stable across calls) and frame appears only in AI capture', () => {
    expect(windowCaptureStyle(true)).toEqual(windowCaptureStyle(true));
    expect(windowCaptureStyle(false)).toEqual(windowCaptureStyle(false));
    expect(windowCaptureStyle(true).frame).toBe(true);
    expect(windowCaptureStyle(false).frame).toBe(false);
  });
});
