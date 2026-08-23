import { useState, useRef, useEffect } from 'react'
import { Maximize2, Minimize2, Sparkles, GraduationCap, Shield } from 'lucide-react'
import toast from 'react-hot-toast'
import { SafeModePanel } from '../shared/SafeModePanel'
import { SettingsPanel } from '../shared/SettingsPanel'
import { CloudSettingsPanel } from '../shared/CloudSettingsPanel'
import { MemoryPanel } from '../shared/MemoryPanel'
import { electronBridge } from '../../lib/electronBridge'

const IconFolder = () => <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.93a2 2 0 0 1-1.66-.9l-.82-1.2A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13c0 1.1.9 2 2 2Z"/></svg>
const IconDatabase = () => <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5V19A9 3 0 0 0 21 19V5"/><path d="M3 12A9 3 0 0 0 21 12"/></svg>
const IconSettings = () => <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1Z"/></svg>
const IconCloud = () => <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M17.5 19H9a7 7 0 1 1 6.71-9h1.79a4.5 4.5 0 1 1 0 9Z"/></svg>

interface MacMenuBarProps {
  isCompact?: boolean
  onToggleMode?: () => void
  activeMode?: 'normal' | 'study' | 'pentest'
  onModeChange?: (mode: 'normal' | 'study' | 'pentest') => void
}

export function MacMenuBar({ isCompact, onToggleMode, activeMode = 'normal', onModeChange }: MacMenuBarProps) {
  const [activeMenu, setActiveMenu] = useState<string | null>(null)
  const [showSettings, setShowSettings] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setActiveMenu(null)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const toggleMenu = (menu: string) => {
    setActiveMenu(activeMenu === menu ? null : menu)
  }

  return (
    <div className={`macos-menu-bar ${isCompact ? 'compact' : ''}`} data-tauri-drag-region ref={menuRef}>
      <div className="menu-left">
        {/* Placeholder for traffic lights spacing in macOS hiddenInset mode */}
        <div className="mac-traffic-lights-spacer" />
        
        {onToggleMode && (
          <button 
            type="button" 
            className="topbar-btn mini-toggle-btn"
            onClick={onToggleMode}
            title={isCompact ? "Expand to Full Workspace" : "Minimize to Mini-Owlynn"}
            style={{ WebkitAppRegion: 'no-drag', background: 'transparent', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', marginRight: '8px', display: 'inline-flex', alignItems: 'center' } as any}
          >
            {isCompact ? <Maximize2 size={14} /> : <Minimize2 size={14} />}
          </button>
        )}
        
        <div className="menu-item-container">
          <button className={`menu-button ${activeMenu === 'owlynn' ? 'active' : ''}`} onClick={() => toggleMenu('owlynn')}>
            <strong>Owlynn</strong>
          </button>
          {activeMenu === 'owlynn' && (
            <div className="menu-dropdown">
              <div className="menu-dropdown-item" onClick={() => {
                toast(`Owlynn v${__APP_VERSION__}`, { duration: 3000 })
                setActiveMenu(null)
              }}>About Owlynn</div>
              <div className="menu-dropdown-divider" />
              <div className="menu-dropdown-item" onClick={() => {
                setActiveMenu(null)
                setShowSettings(true)
              }}>Settings...</div>
              <div className="menu-dropdown-divider" />
              <div className="menu-dropdown-item" onClick={() => {
                electronBridge.hideToTray()
                setActiveMenu(null)
              }}>Hide Owlynn</div>
              <div className="menu-dropdown-item" onClick={() => {
                setActiveMenu(null)
                void electronBridge.quitApp().catch(() => {
                  window.close()
                })
              }}>Quit Owlynn</div>
            </div>
          )}
        </div>

        <div className="menu-item-container">
          <button className={`menu-button ${activeMenu === 'workspace' ? 'active' : ''}`} onClick={() => toggleMenu('workspace')} title={isCompact ? 'Workspace' : undefined}>
            {isCompact ? <IconFolder /> : 'Workspace'}
          </button>
          {activeMenu === 'workspace' && (
            <div className="menu-dropdown">
              <div className="menu-dropdown-item">New Workspace</div>
              <div className="menu-dropdown-item">Switch Workspace...</div>
            </div>
          )}
        </div>

        <div className="menu-item-container">
          <button className={`menu-button ${activeMenu === 'memory' ? 'active' : ''}`} onClick={() => toggleMenu('memory')} title={isCompact ? 'Memory' : undefined}>
            {isCompact ? <IconDatabase /> : 'Memory'}
          </button>
          {activeMenu === 'memory' && (
            <div className="menu-dropdown large-dropdown">
              <MemoryPanel />
            </div>
          )}
        </div>

        <div className="menu-item-container">
          <button className={`menu-button ${activeMenu === 'system' ? 'active' : ''}`} onClick={() => toggleMenu('system')} title={isCompact ? 'Settings' : undefined}>
            {isCompact ? <IconSettings /> : 'Settings'}
          </button>
          {activeMenu === 'system' && (
            <div className="menu-dropdown">
              <div className="menu-dropdown-content">
                <h4>System Toggles</h4>
                <SafeModePanel />
              </div>
            </div>
          )}
        </div>

        <div className="menu-item-container">
          <button className={`menu-button ${activeMenu === 'cloud' ? 'active' : ''}`} onClick={() => toggleMenu('cloud')} title={isCompact ? 'Cloud' : undefined}>
            {isCompact ? <IconCloud /> : 'Cloud'}
          </button>
          {activeMenu === 'cloud' && (
            <div className="menu-dropdown large-dropdown">
              <div className="menu-dropdown-content">
                <h4>Cloud Settings</h4>
                <CloudSettingsPanel />
              </div>
            </div>
          )}
        </div>
      </div>
      {/* Center - Mode Switcher */}
      <div className="menu-center">
        {onModeChange && (
          <div
            style={
              {
                display: 'flex',
                alignItems: 'center',
                gap: 4,
                background: 'rgba(0,0,0,0.3)',
                padding: '2px 4px',
                borderRadius: 8,
                border: '1px solid rgba(255,255,255,0.08)',
                WebkitAppRegion: 'no-drag',
              } as any
            }
          >
            <button
              type="button"
              onClick={() => onModeChange('normal')}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 4,
                padding: '2px 10px',
                fontSize: 11,
                fontWeight: activeMode === 'normal' ? 600 : 400,
                borderRadius: 6,
                background:
                  activeMode === 'normal' ? 'rgba(56, 189, 248, 0.25)' : 'transparent',
                color: activeMode === 'normal' ? '#38bdf8' : '#94a3b8',
                border:
                  activeMode === 'normal'
                    ? '1px solid rgba(56, 189, 248, 0.4)'
                    : '1px solid transparent',
                cursor: 'pointer',
              }}
            >
              <Sparkles size={11} /> Normal
            </button>
            <button
              type="button"
              onClick={() => onModeChange('study')}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 4,
                padding: '2px 10px',
                fontSize: 11,
                fontWeight: activeMode === 'study' ? 600 : 400,
                borderRadius: 6,
                background:
                  activeMode === 'study' ? 'rgba(192, 132, 252, 0.25)' : 'transparent',
                color: activeMode === 'study' ? '#c084fc' : '#94a3b8',
                border:
                  activeMode === 'study'
                    ? '1px solid rgba(192, 132, 252, 0.4)'
                    : '1px solid transparent',
                cursor: 'pointer',
              }}
            >
              <GraduationCap size={11} /> Study
            </button>
            <button
              type="button"
              onClick={() => onModeChange('pentest')}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 4,
                padding: '2px 10px',
                fontSize: 11,
                fontWeight: activeMode === 'pentest' ? 600 : 400,
                borderRadius: 6,
                background:
                  activeMode === 'pentest' ? 'rgba(244, 63, 94, 0.25)' : 'transparent',
                color: activeMode === 'pentest' ? '#f43f5e' : '#94a3b8',
                border:
                  activeMode === 'pentest'
                    ? '1px solid rgba(244, 63, 94, 0.4)'
                    : '1px solid transparent',
                cursor: 'pointer',
              }}
            >
              <Shield size={11} /> Pentest
            </button>
          </div>
        )}
      </div>

      <div className="menu-right">
        {/* Status info moved to bottom StatusBar */}
      </div>
      {/* ── Full Settings Modal ── */}
      {showSettings && (
        <SettingsPanel onClose={() => setShowSettings(false)} />
      )}
    </div>
  )
}
