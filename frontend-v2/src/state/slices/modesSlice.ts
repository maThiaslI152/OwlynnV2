import type { StateCreator } from 'zustand'
import type {
  SafeModeLevel,
  ExecutionPolicy,
  WindowMode,
  PentestVmStatus,
  ActivityFeedItem
} from '../types'
import type { BrowserPageContext } from '../../lib/browserPageContext'

export interface EngagementTab {
  id: string
  name: string
  phase: string
  findingCounts: { critical: number; high: number; medium: number; low: number }
  lastActivity: number
}

export interface ModesSlice {
  safeMode: SafeModeLevel
  executionPolicy: ExecutionPolicy
  windowMode: WindowMode
  activeMode: 'normal' | 'study' | 'pentest'
  studyView: 'dashboard' | 'notebook'
  activeEngagementId: string | null
  engagementTabs: EngagementTab[]
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
  addEngagementTab: (tab: EngagementTab) => void
  removeEngagementTab: (id: string) => void
  updateEngagementTab: (id: string, update: Partial<EngagementTab>) => void
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
  engagementTabs: [],
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
  addEngagementTab: (tab) =>
    set((state) => {
      if (state.engagementTabs.some((t) => t.id === tab.id)) return state
      return { engagementTabs: [...state.engagementTabs, tab] }
    }),
  removeEngagementTab: (id) =>
    set((state) => ({
      engagementTabs: state.engagementTabs.filter((t) => t.id !== id),
      activeEngagementId: state.activeEngagementId === id ? null : state.activeEngagementId,
    })),
  updateEngagementTab: (id, update) =>
    set((state) => ({
      engagementTabs: state.engagementTabs.map((t) =>
        t.id === id ? { ...t, ...update } : t
      ),
    })),
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
