import { create } from 'zustand';

/** Global editor/viewport state (Zustand — per PRD §0 mandated stack). */
interface EditorState {
  scale: number;
  offsetX: number;
  offsetY: number;
  gridVisible: boolean;
  snapEnabled: boolean;
  setViewport: (v: { scale: number; offsetX: number; offsetY: number }) => void;
  setScale: (scale: number) => void;
  toggleGrid: () => void;
  toggleSnap: () => void;
}

export const MIN_SCALE = 0.1;
export const MAX_SCALE = 10;

export const useEditorStore = create<EditorState>((set) => ({
  scale: 1,
  offsetX: 0,
  offsetY: 0,
  gridVisible: true,
  snapEnabled: true,
  setViewport: (v) => set(v),
  setScale: (scale) => set({ scale: Math.max(MIN_SCALE, Math.min(MAX_SCALE, scale)) }),
  toggleGrid: () => set((s) => ({ gridVisible: !s.gridVisible })),
  toggleSnap: () => set((s) => ({ snapEnabled: !s.snapEnabled })),
}));
