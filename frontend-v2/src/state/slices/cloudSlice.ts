import type { StateCreator } from 'zustand'
import type { CloudUsageState, ContextBreakdown } from '../types'

export interface CloudSlice {
  routerMetadata: Record<string, unknown> | null
  modelInfo: string | null
  cloudStatus: { available: boolean; key_valid: boolean; model: string; error: string } | null
  cloudUsage: CloudUsageState | null
  contextBreakdown: ContextBreakdown | null
  coherenceRetryActive: boolean
  coherenceRetryAttempt: number
  coherenceRetryOriginalConfidence: number | null
  cloudFallback: { reason: string; fallback_model: string; can_retry: boolean } | null

  setRouterMetadata: (meta: Record<string, unknown>) => void
  setModelInfo: (model: string | null) => void
  setCloudStatus: (status: { available: boolean; key_valid: boolean; model: string; error: string } | null) => void
  setCloudUsage: (usage: CloudUsageState | null) => void
  setContextBreakdown: (breakdown: ContextBreakdown | null) => void
  setCoherenceRetryActive: (active: boolean, attempt?: number, confidence?: number | null) => void
  setCloudFallback: (fallback: { reason: string; fallback_model: string; can_retry: boolean } | null) => void
  clearCloudSession: () => void
}

export const createCloudSlice: StateCreator<CloudSlice, [], [], CloudSlice> = (set) => ({
  routerMetadata: null,
  modelInfo: null,
  cloudStatus: null,
  cloudUsage: null,
  contextBreakdown: null,
  coherenceRetryActive: false,
  coherenceRetryAttempt: 0,
  coherenceRetryOriginalConfidence: null,
  cloudFallback: null,

  setRouterMetadata: (routerMetadata) => set({ routerMetadata }),
  setModelInfo: (modelInfo) => set({ modelInfo }),
  setCloudStatus: (cloudStatus) => set({ cloudStatus }),
  setCloudUsage: (cloudUsage) => set({ cloudUsage }),
  setContextBreakdown: (contextBreakdown) => set({ contextBreakdown }),
  setCoherenceRetryActive: (active, attempt = 1, confidence = null) =>
    set({
      coherenceRetryActive: active,
      coherenceRetryAttempt: active ? attempt : 0,
      coherenceRetryOriginalConfidence: active ? confidence : null,
    }),
  setCloudFallback: (cloudFallback) => set({ cloudFallback }),
  clearCloudSession: () =>
    set({
      routerMetadata: null,
      modelInfo: null,
      contextBreakdown: null,
      coherenceRetryActive: false,
      coherenceRetryAttempt: 0,
      coherenceRetryOriginalConfidence: null,
      cloudFallback: null,
    }),
})
