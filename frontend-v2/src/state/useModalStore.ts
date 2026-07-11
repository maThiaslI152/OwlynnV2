import { create } from 'zustand'
import React from 'react'

export interface ModalConfig {
  id: string;
  component: React.ReactNode;
  closeOnBackdrop?: boolean;
}

interface ModalState {
  modals: ModalConfig[];
  openModal: (modal: ModalConfig) => void;
  closeModal: (id: string) => void;
  closeAll: () => void;
}

export const useModalStore = create<ModalState>((set) => ({
  modals: [],
  openModal: (modal) => set((state) => ({ modals: [...state.modals, modal] })),
  closeModal: (id) => set((state) => ({ modals: state.modals.filter((m) => m.id !== id) })),
  closeAll: () => set({ modals: [] }),
}))
