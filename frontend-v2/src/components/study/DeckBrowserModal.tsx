import { useState, useEffect } from 'react'
import toast from 'react-hot-toast'
import { fetchWithAuth } from '../../lib/localRunToken'

interface Card {
  card_id: string
  front: string
  back: string
  interval: number
  ease: number
  due: string
}

interface Deck {
  deck_id: string
  name: string
  course_id: string | null
  cards: Card[]
  created_at: string
}

interface DeckBrowserModalProps {
  deckId: string
  onClose: () => void
}

export function DeckBrowserModal({ deckId, onClose }: DeckBrowserModalProps) {
  const [deck, setDeck] = useState<Deck | null>(null)
  const [loading, setLoading] = useState(true)
  const [editingCard, setEditingCard] = useState<string | null>(null)
  const [editFront, setEditFront] = useState('')
  const [editBack, setEditBack] = useState('')

  useEffect(() => {
    fetchWithAuth(`/api/flashcards/${deckId}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (d?.status === 'ok') setDeck(d.deck)
      })
      .catch((err) => {
        toast.error('Failed to load deck')
        console.error('[DeckBrowser]', err)
      })
      .finally(() => setLoading(false))
  }, [deckId])

  const handleSaveCard = async (cardId: string) => {
    if (!deck) return
    try {
      const r = await fetchWithAuth(`/api/flashcards/${deckId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'update_card',
          card_id: cardId,
          front: editFront,
          back: editBack,
        }),
      })
      if (r.ok) {
        setDeck({
          ...deck,
          cards: deck.cards.map((c) =>
            c.card_id === cardId ? { ...c, front: editFront, back: editBack } : c
          ),
        })
        setEditingCard(null)
        toast.success('Card updated')
      }
    } catch {
      toast.error('Failed to update card')
    }
  }

  const handleDeleteCard = async (cardId: string) => {
    if (!deck) return
    try {
      const r = await fetchWithAuth(`/api/flashcards/${deckId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'delete_card', card_id: cardId }),
      })
      if (r.ok) {
        setDeck({ ...deck, cards: deck.cards.filter((c) => c.card_id !== cardId) })
        toast.success('Card deleted')
      }
    } catch {
      toast.error('Failed to delete card')
    }
  }

  if (loading) {
    return (
      <div className="modal-overlay" onClick={onClose}>
        <div className="modal-content" onClick={(e) => e.stopPropagation()}>
          <div style={{ padding: 20, textAlign: 'center' }}>Loading...</div>
        </div>
      </div>
    )
  }

  if (!deck) {
    return (
      <div className="modal-overlay" onClick={onClose}>
        <div className="modal-content" onClick={(e) => e.stopPropagation()}>
          <div style={{ padding: 20 }}>Deck not found</div>
        </div>
      </div>
    )
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal-content"
        onClick={(e) => e.stopPropagation()}
        style={{ maxWidth: 600, maxHeight: '80vh', overflow: 'auto' }}
      >
        <div style={{ padding: 16 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
            <div>
              <div style={{ fontWeight: 700, fontSize: 16 }}>{deck.name}</div>
              <div style={{ opacity: 0.6, fontSize: 12 }}>
                {deck.course_id && `${deck.course_id} • `}
                {deck.cards.length} cards
              </div>
            </div>
            <button
              type="button"
              onClick={onClose}
              style={{
                background: 'none',
                border: 'none',
                color: 'inherit',
                cursor: 'pointer',
                fontSize: 18,
                padding: '4px 8px',
              }}
            >
              ✕
            </button>
          </div>

          {/* Cards list */}
          {deck.cards.map((card) => (
            <div
              key={card.card_id}
              style={{
                padding: 12,
                marginBottom: 8,
                borderRadius: 8,
                background: 'rgba(255,255,255,0.03)',
                border: '1px solid rgba(255,255,255,0.08)',
              }}
            >
              {editingCard === card.card_id ? (
                // Edit mode
                <div>
                  <input
                    value={editFront}
                    onChange={(e) => setEditFront(e.target.value)}
                    placeholder="Front"
                    style={{
                      width: '100%',
                      padding: 6,
                      marginBottom: 6,
                      fontSize: 12,
                      background: 'rgba(255,255,255,0.05)',
                      border: '1px solid rgba(255,255,255,0.1)',
                      borderRadius: 4,
                      color: 'inherit',
                    }}
                  />
                  <input
                    value={editBack}
                    onChange={(e) => setEditBack(e.target.value)}
                    placeholder="Back"
                    style={{
                      width: '100%',
                      padding: 6,
                      marginBottom: 6,
                      fontSize: 12,
                      background: 'rgba(255,255,255,0.05)',
                      border: '1px solid rgba(255,255,255,0.1)',
                      borderRadius: 4,
                      color: 'inherit',
                    }}
                  />
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button
                      type="button"
                      onClick={() => handleSaveCard(card.card_id)}
                      style={{ fontSize: 11, padding: '4px 12px', cursor: 'pointer' }}
                    >
                      Save
                    </button>
                    <button
                      type="button"
                      onClick={() => setEditingCard(null)}
                      style={{ fontSize: 11, padding: '4px 12px', cursor: 'pointer' }}
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                // View mode
                <div>
                  <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 4 }}>
                    {card.front}
                  </div>
                  <div style={{ opacity: 0.7, fontSize: 12, marginBottom: 8 }}>
                    {card.back}
                  </div>
                  <div style={{ display: 'flex', gap: 8, fontSize: 11 }}>
                    <button
                      type="button"
                      onClick={() => {
                        setEditingCard(card.card_id)
                        setEditFront(card.front)
                        setEditBack(card.back)
                      }}
                      style={{ padding: '2px 8px', cursor: 'pointer' }}
                    >
                      Edit
                    </button>
                    <button
                      type="button"
                      onClick={() => handleDeleteCard(card.card_id)}
                      style={{ padding: '2px 8px', cursor: 'pointer', color: '#ff6b6b' }}
                    >
                      Delete
                    </button>
                    <span style={{ opacity: 0.4, marginLeft: 'auto' }}>
                      Due: {new Date(card.due).toLocaleDateString()}
                    </span>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
