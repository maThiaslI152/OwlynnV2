import type { StateCreator } from 'zustand'
import type {
  SafeModeLevel,
  ExecutionPolicy,
  WindowMode,
  PentestVmStatus,
  ActivityFeedItem
} from '../types'
import type { BrowserPageContext } from '../../lib/browserPageContext'

export interface ModesSlice {
  safeMode: SafeModeLevel
  executionPolicy: ExecutionPolicy
  windowMode: WindowMode
  activeMode: 'normal' | 'study' | 'pentest'
  studyView: 'dashboard' | 'notebook'
  activeEngagementId: string | null
  pentestVmStatus: PentestVmStatus | null
  activityFeedItems: ActivityFeedItem[]
  browserPageContext: BrowserPageContext | null
  browserPageContextNonce: number

  setSafeMode: (mode: SafeModeLevel) => void
  setExecutionPolicy: (policy: ExecutionPolicy) => void
  setWindowMode: (mode: WindowMode) => void
  setActiveMode: (mode: 'normal' | 'study' | 'pentest') => void
  setStudyView: (view: 'dashboard' | 'notebook') => void
  setActiveEngagementId: (id: string | null) => void
  setPentestVmStatus: (status: PentestVmStatus | null) => void
  appendActivityFeedItem: (item: ActivityFeedItem) => void
  updateActivityFeedItem: (id: string, update: Partial<ActivityFeedItem>) => void
  clearActivityFeed: () => void
  applyBrowserPageContext: (ctx: BrowserPageContext) => void
}

export const createModesSlice: StateCreator<ModesSlice, [], [], ModesSlice> = (set) => ({
  safeMode: 'normal',
  executionPolicy: 'auto_approve',
  windowMode: 'full',
  activeMode: 'normal',
  studyView: 'dashboard',
  activeEngagementId: null,
  pentestVmStatus: null,
  activityFeedItems: [],
  browserPageContext: null,
  browserPageContextNonce: 0,

  setSafeMode: (safeMode) => set({ safeMode }),
  setExecutionPolicy: (executionPolicy) => set({ executionPolicy }),
  setWindowMode: (windowMode) => set({ windowMode }),
  setActiveMode: (activeMode) => set({ activeMode }),
  setStudyView: (studyView) => set({ studyView }),
  setActiveEngagementId: (activeEngagementId) => set({ activeEngagementId }),
  setPentestVmStatus: (pentestVmStatus) => set({ pentestVmStatus }),
  appendActivityFeedItem: (item) =>
    set((state) => ({
      activityFeedItems: [...state.activityFeedItems.slice(-199), item],
    })),
  updateActivityFeedItem: (id, update) =>
    set((state) => ({
      activityFeedItems: state.activityFeedItems.map((item) =>
        item.id === id ? { ...item, ...update } : item
      ),
    })),
  clearActivityFeed: () => set({ activityFeedItems: [] }),
  applyBrowserPageContext: (ctx) =>
    set((state) => ({
      browserPageContext: ctx,
      browserPageContextNonce: state.browserPageContextNonce + 1,
      operatorNote: 'Page received from Brave.',
    })),
})
