import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import './hitl-cards.css'
import App from './App.tsx'
import './i18n'

// Apply Tauri-specific glass mode for native frosted effects.
const hasTauriInternals = typeof window !== 'undefined' && Boolean((window as any).__TAURI_INTERNALS__);

if (hasTauriInternals) {
  document.body.classList.add('tauri-glass')
}

import { Toaster } from 'react-hot-toast'
import { ErrorBoundary } from './components/shared/ErrorBoundary'

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: false,
    },
  },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ErrorBoundary>
        <App />
        <Toaster position="bottom-right" toastOptions={{ style: { background: '#333', color: '#fff' } }} />
      </ErrorBoundary>
    </QueryClientProvider>
  </StrictMode>,
)
