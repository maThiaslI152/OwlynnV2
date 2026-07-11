import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'

interface SidebarAccordionProps {
  title: React.ReactNode
  actions?: React.ReactNode
  children: React.ReactNode
  defaultOpen?: boolean
}

export function SidebarAccordion({ title, actions, children, defaultOpen = true }: SidebarAccordionProps) {
  const [open, setOpen] = useState(defaultOpen)

  return (
    <div className="sidebar-accordion-custom" style={{ marginBottom: 8 }}>
      <div 
        className="sidebar-accordion-summary" 
        onClick={() => setOpen(!open)}
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          cursor: 'pointer',
          padding: '8px 14px',
          fontSize: '11px',
          fontWeight: 600,
          textTransform: 'uppercase',
          letterSpacing: '0.05em',
          color: 'var(--text-muted)',
          userSelect: 'none'
        }}
      >
        <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <motion.span 
            animate={{ rotate: open ? 90 : 0 }}
            transition={{ duration: 0.2 }}
            style={{ display: 'inline-block', fontSize: '9px' }}
          >
            ▶
          </motion.span>
          {title}
        </span>
        {actions && (
          <div className="workspace-header-actions" onClick={(e) => e.stopPropagation()}>
            {actions}
          </div>
        )}
      </div>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: "easeInOut" }}
            style={{ overflow: 'hidden' }}
          >
            <div className="sidebar-accordion-content" style={{ padding: '4px 14px 12px' }}>
              {children}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
