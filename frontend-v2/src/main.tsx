import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

// Apply Tauri-specific glass mode for native frosted effects.
if ((window as unknown as { __TAURI__?: unknown }).__TAURI__) {
  document.body.classList.add('tauri-glass')
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
