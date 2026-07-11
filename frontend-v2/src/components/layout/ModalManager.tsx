import React, { useEffect } from 'react';
import { useModalStore } from '../../state/useModalStore';
import { motion, AnimatePresence } from 'framer-motion';

export const ModalManager: React.FC = () => {
  const modals = useModalStore((state) => state.modals);
  const closeModal = useModalStore((state) => state.closeModal);

  // Handle escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && modals.length > 0) {
        // Close the top-most modal
        closeModal(modals[modals.length - 1].id);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [modals, closeModal]);

  return (
    <AnimatePresence>
      {modals.map((modal, index) => (
        <div key={modal.id} className="relative" style={{ zIndex: 100 + index }}>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="fixed inset-0 bg-black/50 backdrop-blur-sm"
            onClick={() => {
              if (modal.closeOnBackdrop !== false) {
                closeModal(modal.id);
              }
            }}
          />
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 10 }}
            transition={{ duration: 0.15 }}
            className="fixed inset-0 pointer-events-none flex items-center justify-center p-4"
          >
            <div className="pointer-events-auto w-full max-w-2xl max-h-full overflow-hidden flex flex-col">
              {modal.component}
            </div>
          </motion.div>
        </div>
      ))}
    </AnimatePresence>
  );
};
