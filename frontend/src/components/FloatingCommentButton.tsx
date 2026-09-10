import { useEffect, useRef, useState } from 'react';
import { MessageSquarePlus, Send, X, Brain, ExternalLink } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { api, type ProductRule } from '../api';
import './FloatingCommentButton.css';

interface Props {
  productId: string;
  /** Optional — shown in the modal header so the user knows what they're commenting on. */
  contextLabel?: string;
}

/**
 * Floating action button that lets the assessor add a comment (and trigger
 * reflection memory) from any assessment page without navigating back to the
 * product detail.
 */
export default function FloatingCommentButton({ productId, contextLabel }: Props) {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [added, setAdded] = useState<ProductRule[] | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  // Autofocus the textarea when the modal opens.
  useEffect(() => {
    if (open) {
      setError('');
      setAdded(null);
      setTimeout(() => textareaRef.current?.focus(), 30);
    }
  }, [open]);

  // Close on Escape.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);

  const submit = async (e?: React.FormEvent) => {
    e?.preventDefault();
    const text = draft.trim();
    if (!text || busy) return;
    setBusy(true);
    setError('');
    try {
      const result = await api.createProductComment(productId, text);
      setAdded(result.added);
      setDraft('');
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <button
        type="button"
        className="fab-comment"
        onClick={() => setOpen(true)}
        title="Add an assessor note (will be distilled into product memory)"
        aria-label="Add note"
      >
        <MessageSquarePlus size={22} />
      </button>

      {open && (
        <div className="fab-overlay" onClick={() => !busy && setOpen(false)}>
          <div className="fab-modal" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
            <div className="fab-modal-header">
              <div>
                <h3><MessageSquarePlus size={18} /> Add assessor note</h3>
                {contextLabel && <p className="muted small">on “{contextLabel}”</p>}
              </div>
              <button className="btn-icon" onClick={() => setOpen(false)} disabled={busy} aria-label="Close">
                <X size={18} />
              </button>
            </div>

            {added === null ? (
              <form onSubmit={submit} className="fab-modal-body">
                <p className="muted small">
                  Your note will be distilled into <strong>rules</strong> that
                  steer every future classification / obligation selection for
                  this product.
                </p>
                {error && <div className="fab-error">{error}</div>}
                <textarea
                  ref={textareaRef}
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  placeholder="e.g. This obligation does not apply — device is offline-only and EEA-only."
                  rows={5}
                  disabled={busy}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                      e.preventDefault();
                      submit();
                    }
                  }}
                />
                <div className="fab-modal-actions">
                  <span className="muted small">Cmd/Ctrl+Enter to submit</span>
                  <div className="fab-modal-actions-right">
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm"
                      onClick={() => setOpen(false)}
                      disabled={busy}
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      className="btn btn-primary btn-sm"
                      disabled={busy || !draft.trim()}
                    >
                      <Send size={14} /> {busy ? 'Reflecting…' : 'Add & reflect'}
                    </button>
                  </div>
                </div>
              </form>
            ) : (
              <div className="fab-modal-body">
                {added.length === 0 ? (
                  <div className="fab-result">
                    <p>
                      Note saved — no new rule was distilled (already covered by
                      existing memory or judged out of scope).
                    </p>
                  </div>
                ) : (
                  <div className="fab-result">
                    <p>
                      <Brain size={16} /> Added <strong>{added.length}</strong> new
                      rule{added.length === 1 ? '' : 's'} to product memory:
                    </p>
                    <ul className="fab-rule-list">
                      {added.map((r) => (
                        <li key={r.id}>
                          <span className={`fab-rule-cat cat-${r.category || 'scope'}`}>{r.category || 'scope'}</span>
                          <span>{r.text}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                <div className="fab-modal-actions">
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    onClick={() => navigate(`/products/${productId}?tab=comments`)}
                  >
                    <ExternalLink size={14} /> Open product memory
                  </button>
                  <div className="fab-modal-actions-right">
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm"
                      onClick={() => setAdded(null)}
                    >
                      Add another
                    </button>
                    <button
                      type="button"
                      className="btn btn-primary btn-sm"
                      onClick={() => setOpen(false)}
                    >
                      Done
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}
