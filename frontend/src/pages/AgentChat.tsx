import { useEffect, useRef, useState } from 'react';
import { Send, Bot, User, Wrench, RotateCcw, ChevronRight } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { api } from '../api';
import type { AgentChatEvent } from '../api';
import './AgentChat.css';

interface ProgressInfo {
  current?: number;
  total?: number;
  text: string;
  author?: string | null;
  updatedAt: number;
}

interface ChatTurn {
  role: 'user' | 'assistant' | 'system';
  text: string;
  events?: AgentChatEvent[];
  streaming?: boolean;
  progress?: ProgressInfo | null;
}

const SUGGESTIONS = [
  'List all CRA articles',
  'What are the obligations of Article 13?',
  'Show graph stats',
  'List actors in the knowledge graph',
  'Read recital 12 of the CRA',
  'What deadlines does the CRA impose?',
];

export default function AgentChat() {
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [turns, busy]);

  async function send(message: string) {
    const text = message.trim();
    if (!text || busy) return;
    setError(null);
    setBusy(true);
    setTurns((t) => [
      ...t,
      { role: 'user', text },
      // Placeholder assistant turn we will progressively update.
      { role: 'assistant', text: '', events: [], streaming: true },
    ]);
    setInput('');

    // Index of the assistant placeholder we just pushed.
    const updateAssistant = (mut: (turn: ChatTurn) => ChatTurn) => {
      setTurns((t) => {
        const copy = [...t];
        for (let i = copy.length - 1; i >= 0; i--) {
          if (copy[i].role === 'assistant' && copy[i].streaming) {
            copy[i] = mut(copy[i]);
            break;
          }
        }
        return copy;
      });
    };

    try {
      const res = await api.agentChatStream(text, sessionId, (evt) => {
        if (evt.kind === 'session') {
          setSessionId(evt.session_id);
          return;
        }
        if (evt.kind === 'final') {
          updateAssistant((turn) => ({
            ...turn,
            text: evt.reply || turn.text || '(no reply)',
            streaming: false,
            progress: null,
          }));
          return;
        }
        if (evt.kind === 'progress') {
          updateAssistant((turn) => ({
            ...turn,
            progress: {
              current: evt.current,
              total: evt.total,
              text: evt.text || '',
              author: evt.author,
              updatedAt: Date.now(),
            },
          }));
          return;
        }
        // Progressive tool / text / error events.
        updateAssistant((turn) => {
          const next: ChatTurn = {
            ...turn,
            events: [...(turn.events || []), evt],
          };
          if (evt.kind === 'text' && evt.text) {
            // Gemini may emit either cumulative or delta partials; keep the
            // longest so far to be safe.
            next.text = evt.text.length >= (turn.text?.length || 0) ? evt.text : turn.text;
          } else if (evt.kind === 'error' && evt.text) {
            next.text = (turn.text ? turn.text + '\n' : '') + `⚠ ${evt.text}`;
          } else if (evt.kind === 'tool_result') {
            // A tool finished — clear its progress indicator.
            next.progress = null;
          }
          return next;
        });
      });
      setSessionId(res.session_id);
      updateAssistant((turn) => ({
        ...turn,
        text: res.reply || turn.text || '(no reply)',
        streaming: false,
        progress: null,
      }));
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
      updateAssistant((turn) => ({ ...turn, streaming: false }));
      setTurns((t) => [...t, { role: 'system', text: `Error: ${msg}` }]);
    } finally {
      setBusy(false);
    }
  }

  async function reset() {
    try {
      await api.agentReset(sessionId);
    } catch {
      /* ignore */
    }
    setSessionId(null);
    setTurns([]);
    setError(null);
  }

  return (
    <div className="agent-chat">
      <header className="agent-header">
        <div>
          <h1>AI Assistant</h1>
          <p className="muted">
            Chat with the CRA / Part-IS knowledge graph orchestrator. It can ingest
            articles, query Neo4j, classify products, and run any tool the ADK
            agent exposes.
          </p>
        </div>
        <button className="btn-secondary" onClick={reset} disabled={busy || turns.length === 0}>
          <RotateCcw size={16} />
          New conversation
        </button>
      </header>

      <div className="agent-messages" ref={scrollRef}>
        {turns.length === 0 && (
          <div className="agent-welcome">
            <Bot size={32} />
            <h2>How can I help?</h2>
            <p className="muted">Try one of these:</p>
            <div className="suggestions">
              {SUGGESTIONS.map((s) => (
                <button key={s} className="suggestion" onClick={() => send(s)}>
                  <ChevronRight size={14} />
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {turns.map((t, i) => (
          <Message key={i} turn={t} />
        ))}

        {busy && !turns.some((t) => t.role === 'assistant' && t.streaming) && (
          <div className="message assistant">
            <div className="avatar"><Bot size={18} /></div>
            <div className="bubble thinking">
              <span className="dot" />
              <span className="dot" />
              <span className="dot" />
            </div>
          </div>
        )}
      </div>

      {error && <div className="agent-error">{error}</div>}

      <form
        className="agent-input"
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
      >
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              send(input);
            }
          }}
          placeholder="Ask the agent…  (Shift+Enter for newline)"
          rows={1}
          disabled={busy}
        />
        <button type="submit" disabled={busy || !input.trim()}>
          <Send size={18} />
        </button>
      </form>
    </div>
  );
}

function Message({ turn }: { turn: ChatTurn }) {
  const [showTools, setShowTools] = useState(false);
  const tools = (turn.events || []).filter(
    (e) => e.kind === 'tool_call' || e.kind === 'tool_result' || e.kind === 'transfer',
  );
  const Icon = turn.role === 'user' ? User : Bot;
  // While streaming, auto-show the tool feed so the user sees live progress.
  const toolsVisible = showTools || !!turn.streaming;
  const lastTool = tools[tools.length - 1];

  return (
    <div className={`message ${turn.role}`}>
      <div className="avatar"><Icon size={18} /></div>
      <div className="content">
        <div className="bubble">
          {turn.streaming && !turn.text && (
            <div className="streaming-status">
              <span className="dot" />
              <span className="dot" />
              <span className="dot" />
              {lastTool && (
                <span className="streaming-step">
                  {labelFor(lastTool)} {lastTool.name || ''}
                </span>
              )}
            </div>
          )}
          {turn.text && (
            turn.role === 'assistant' ? (
              <div className="text markdown">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{turn.text}</ReactMarkdown>
              </div>
            ) : (
              <pre className="text">{turn.text}</pre>
            )
          )}
        </div>
        {turn.progress && (
          <ProgressBar info={turn.progress} />
        )}
        {tools.length > 0 && (
          <div className="tools">
            <button className="tools-toggle" onClick={() => setShowTools((s) => !s)}>
              <Wrench size={14} />
              {toolsVisible ? 'Hide' : 'Show'} {tools.length} tool action{tools.length === 1 ? '' : 's'}
              {turn.streaming ? ' (live)' : ''}
            </button>
            {toolsVisible && (
              <div className="tools-list">
                {tools.map((ev, idx) => (
                  <div key={idx} className={`tool-row ${ev.kind}`}>
                    <span className="tool-kind">{labelFor(ev)}</span>
                    <span className="tool-name">{ev.name || '—'}</span>
                    {ev.kind === 'tool_call' && ev.args !== undefined && ev.args !== null && (
                      <pre className="tool-args">{prettyJson(ev.args)}</pre>
                    )}
                    {ev.kind === 'tool_result' && ev.result !== undefined && ev.result !== null && (
                      <pre className="tool-args">{prettyJson(ev.result)}</pre>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function labelFor(ev: AgentChatEvent): string {
  if (ev.kind === 'tool_call') return '⚙ call';
  if (ev.kind === 'tool_result') return '↩ result';
  if (ev.kind === 'transfer') return '➜ transfer';
  return ev.kind;
}

function prettyJson(value: unknown): string {
  try {
    if (typeof value === 'string') return value;
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function ProgressBar({ info }: { info: ProgressInfo }) {
  const hasNumeric =
    typeof info.current === 'number' && typeof info.total === 'number' && info.total > 0;
  const pct = hasNumeric
    ? Math.min(100, Math.round(((info.current as number) / (info.total as number)) * 100))
    : null;
  return (
    <div className="progress-block">
      <div className="progress-meta">
        <span className="progress-label">
          {hasNumeric
            ? `Step ${info.current}/${info.total}`
            : info.author || 'In progress'}
        </span>
        {pct !== null && <span className="progress-pct">{pct}%</span>}
      </div>
      <div className={`progress-bar ${pct === null ? 'indeterminate' : ''}`}>
        <div
          className="progress-fill"
          style={pct !== null ? { width: `${pct}%` } : undefined}
        />
      </div>
      {info.text && <div className="progress-text">{info.text}</div>}
    </div>
  );
}
