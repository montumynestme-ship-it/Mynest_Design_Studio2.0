import { create } from 'zustand';
import { persist } from 'zustand/middleware';

/** The eight compass directions the plan's north can be set to. */
export type NorthDir = 'N' | 'NE' | 'E' | 'SE' | 'S' | 'SW' | 'W' | 'NW';

/** Clockwise angle (degrees) of each direction, 0 = up. */
export const NORTH_DEG: Record<NorthDir, number> = {
  N: 0,
  NE: 45,
  E: 90,
  SE: 135,
  S: 180,
  SW: 225,
  W: 270,
  NW: 315,
};

/** Global editor/viewport state (Zustand — per PRD §0 mandated stack). */
interface EditorState {
  scale: number;
  offsetX: number;
  offsetY: number;
  gridVisible: boolean;
  snapEnabled: boolean;
  /** Direction the plan's north arrow points (8-way compass). */
  north: NorthDir;
  /** Collapsible main sidebar rail state */
  sidebarCollapsed: boolean;
  /** Zen / Full-screen distraction-free workspace mode */
  zenMode: boolean;
  setViewport: (v: { scale: number; offsetX: number; offsetY: number }) => void;
  setScale: (scale: number) => void;
  toggleGrid: () => void;
  toggleSnap: () => void;
  setNorth: (north: NorthDir) => void;
  toggleSidebar: () => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
  toggleZenMode: () => void;
  setZenMode: (zen: boolean) => void;
}

export const MIN_SCALE = 0.1;
export const MAX_SCALE = 10;

export const useEditorStore = create<EditorState>()(
  persist(
    (set) => ({
      scale: 1,
      offsetX: 0,
      offsetY: 0,
      gridVisible: true,
      snapEnabled: true,
      north: 'N',
      sidebarCollapsed: false,
      zenMode: false,
      setViewport: (v) => set(v),
      setScale: (scale) => set({ scale: Math.max(MIN_SCALE, Math.min(MAX_SCALE, scale)) }),
      toggleGrid: () => set((s) => ({ gridVisible: !s.gridVisible })),
      toggleSnap: () => set((s) => ({ snapEnabled: !s.snapEnabled })),
      setNorth: (north) => set({ north }),
      toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
      setSidebarCollapsed: (sidebarCollapsed) => set({ sidebarCollapsed }),
      toggleZenMode: () => set((s) => ({ zenMode: !s.zenMode })),
      setZenMode: (zenMode) => set({ zenMode }),
    }),
    {
      name: 'mynest-editor-state',
      partialize: (state) => ({
        gridVisible: state.gridVisible,
        snapEnabled: state.snapEnabled,
        north: state.north,
        sidebarCollapsed: state.sidebarCollapsed,
        zenMode: state.zenMode,
      }),
    },
  ),
);
