const API_BASE = '/api';

// ── Token management ────────────────────────────────────────────────
let _token: string | null = localStorage.getItem('auth_token');

export function setToken(token: string | null) {
  _token = token;
  if (token) localStorage.setItem('auth_token', token);
  else localStorage.removeItem('auth_token');
}

export function getToken(): string | null {
  return _token;
}

async function authFetch(input: RequestInfo, init?: RequestInit): Promise<Response> {
  const headers = new Headers(init?.headers);
  if (_token && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${_token}`);
  }
  const res = await fetch(input, { ...init, headers });
  if (res.status === 401) {
    setToken(null);
  }
  return res;
}

function filenameFromDisposition(disposition: string | null, fallback: string): string {
  if (!disposition) return fallback;
  const utf8Match = disposition.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8Match?.[1]) return decodeURIComponent(utf8Match[1]);
  const plainMatch = disposition.match(/filename="?([^";]+)"?/i);
  return plainMatch?.[1] || fallback;
}

export interface AssessmentResponse {
  id: string;
  product_id: string;
  product_version_id: string;
  version_number: number;
  product_name: string;
  description: string;
  regulation?: string;
  obligation_ids: string[];
  product_class?: string;
  confidence?: string;
  reasoning?: string;
  matched_categories?: string[];
  key_features?: string[];
  actor_roles?: string[];
  conformity_route?: string;
  quiz_page?: number;
  locked?: boolean;
  created_at?: string;
  progress_percent?: number;
}

export interface ProductEvidenceItem {
  assessment_id: string;
  assessment_name: string;
  regulation: string;
  version_number: number;
  verification_id: string;
  verification_text: string;
  evidence: string;
  status: string;
  notes: string;
}

// ── Product domain ─────────────────────────────────────────────────
export type ProductRole = 'owner' | 'collaborator' | 'admin';

export interface ProductSummary {
  id: string;
  name: string;
  owner_username?: string;
  role?: ProductRole;
  created_at: string;
  versions_count: number;
  assessments_count: number;
  latest_version_number?: number | null;
}

export interface ProductVersion {
  id: string;
  version_number: number;
  description: string;
  technical_file_name?: string;
  key_features: string[];
  actor_roles: string[];
  created_at: string;
  has_locked_assessment: boolean;
  assessments_count: number;
}

export interface ProductDetail {
  id: string;
  name: string;
  owner_username?: string;
  role?: ProductRole;
  created_at: string;
  versions: ProductVersion[];
}

export interface ProductShare {
  product_id: string;
  username: string;
  granted_by: string;
  created_at: string;
}

export interface ProductComment {
  id: string;
  product_id: string;
  author: string;
  text: string;
  created_at: string;
}

export interface ProductRule {
  id: string;
  product_id: string;
  text: string;
  category: string;
  status: string;
  source_comment_id?: string | null;
  source_assessment_id?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ReflectionResult {
  added: ProductRule[];
  rules: ProductRule[];
}

export interface AssessmentListItem {
  id: string;
  product_id: string;
  product_version_id: string;
  version_number: number;
  product_name: string;
  description: string;
  regulation: string;
  locked: boolean;
  progress_percent: number;
  created_at: string;
}

export interface Obligation {
  id: string;
  action: string | null;
  article_id: string | null;
  paragraph_ref: string | null;
  trigger: string | null;
  deadline: string | null;
  article_title: string | null;
  justification: string | null;
}

export interface Verification {
  id: string;
  type: string | null;
  description: string | null;
  evidence: string | null;
}

export interface Question {
  verification_id: string;
  verification_type: string;
  verification_text: string;
  associated_obligations: any[];
}

export interface Answer {
  verification_id: string;
  status: string;
  evidence: string;
  notes: string;
  verification_text?: string;
  associated_obligations?: any[];
}

export interface Regulation {
  id: string;
  name: string;
  short: string;
  full_ref: string;
  domain: string;
}

export const api = {
  // ── Auth ──
  login: async (username: string, password: string): Promise<{ access_token: string; username: string; full_name: string }> => {
    const body = new URLSearchParams({ username, password });
    const res = await fetch(`${API_BASE}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Login failed' }));
      throw new Error(err.detail || 'Login failed');
    }
    return res.json();
  },

  getMe: async (): Promise<{ username: string; full_name: string }> => {
    const res = await fetch(`${API_BASE}/auth/me`, {
      headers: _token ? { 'Authorization': `Bearer ${_token}` } : {},
    });
    if (!res.ok) throw new Error('Not authenticated');
    return res.json();
  },

  listShareableUsers: async (): Promise<{ username: string; full_name: string; is_admin: boolean }[]> => {
    const res = await authFetch(`${API_BASE}/auth/users/shareable`);
    if (!res.ok) throw new Error('Failed to fetch users');
    return res.json();
  },

  changePassword: async (currentPassword: string, newPassword: string): Promise<void> => {
    const res = await authFetch(`${API_BASE}/auth/change-password`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Failed to change password' }));
      throw new Error(err.detail || 'Failed to change password');
    }
  },

  adminResetPassword: async (username: string, newPassword: string): Promise<void> => {
    const res = await authFetch(
      `${API_BASE}/auth/users/${encodeURIComponent(username)}/password`,
      {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ new_password: newPassword }),
      },
    );
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Failed to reset password' }));
      throw new Error(err.detail || 'Failed to reset password');
    }
  },

  // ── Regulations ──
  getRegulations: async (): Promise<Regulation[]> => {
    const res = await fetch(`${API_BASE}/regulations`);
    if (!res.ok) throw new Error('Failed to fetch regulations');
    return res.json();
  },

  // ── Products ───────────────────────────────────────────────────
  listProducts: async (): Promise<ProductSummary[]> => {
    const res = await authFetch(`${API_BASE}/products`);
    if (!res.ok) throw new Error('Failed to fetch products');
    return res.json();
  },

  getProduct: async (productId: string): Promise<ProductDetail> => {
    const res = await authFetch(`${API_BASE}/products/${productId}`);
    if (!res.ok) throw new Error('Failed to fetch product');
    return res.json();
  },

  renameProduct: async (productId: string, name: string): Promise<ProductDetail> => {
    const res = await authFetch(`${API_BASE}/products/${productId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Failed to rename product' }));
      throw new Error(err.detail || 'Failed to rename product');
    }
    return res.json();
  },

  deleteProduct: async (productId: string): Promise<void> => {
    const res = await authFetch(`${API_BASE}/products/${productId}`, { method: 'DELETE' });
    if (!res.ok) throw new Error('Failed to delete product');
  },

  listProductAssessments: async (productId: string): Promise<AssessmentResponse[]> => {
    const res = await authFetch(`${API_BASE}/products/${productId}/assessments`);
    if (!res.ok) throw new Error('Failed to fetch product assessments');
    return res.json();
  },

  createAssessmentForProduct: async (
    productId: string,
    regulation: string,
    description: string,
    file?: File,
  ): Promise<AssessmentResponse> => {
    const formData = new FormData();
    formData.append('regulation', regulation);
    formData.append('description', description);
    if (file) formData.append('file', file);
    const res = await authFetch(`${API_BASE}/products/${productId}/assessments`, {
      method: 'POST',
      body: formData,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Failed to create assessment' }));
      throw new Error(err.detail || 'Failed to create assessment');
    }
    return res.json();
  },

  updateProductVersion: async (
    productId: string,
    versionId: string,
    data: { description?: string; key_features?: string[]; actor_roles?: string[] },
  ): Promise<ProductVersion> => {
    const res = await authFetch(`${API_BASE}/products/${productId}/versions/${versionId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Failed to update version' }));
      throw new Error(err.detail || 'Failed to update version');
    }
    return res.json();
  },

  deleteProductVersion: async (productId: string, versionId: string): Promise<void> => {
    const res = await authFetch(`${API_BASE}/products/${productId}/versions/${versionId}`, {
      method: 'DELETE',
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Failed to delete version' }));
      throw new Error(err.detail || 'Failed to delete version');
    }
  },

  getProductEvidence: async (productId: string): Promise<ProductEvidenceItem[]> => {
    const res = await authFetch(`${API_BASE}/products/${productId}/evidence`);
    if (!res.ok) throw new Error('Failed to fetch product evidence');
    return res.json();
  },

  // ── Product sharing (collaborators) ─────────────────────────────
  listProductShares: async (productId: string): Promise<ProductShare[]> => {
    const res = await authFetch(`${API_BASE}/products/${productId}/shares`);
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Failed to fetch shares' }));
      throw new Error(err.detail || 'Failed to fetch shares');
    }
    return res.json();
  },

  createProductShare: async (productId: string, username: string): Promise<ProductShare> => {
    const res = await authFetch(`${API_BASE}/products/${productId}/shares`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Failed to share product' }));
      throw new Error(err.detail || 'Failed to share product');
    }
    return res.json();
  },

  deleteProductShare: async (productId: string, username: string): Promise<void> => {
    const res = await authFetch(
      `${API_BASE}/products/${productId}/shares/${encodeURIComponent(username)}`,
      { method: 'DELETE' },
    );
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Failed to revoke share' }));
      throw new Error(err.detail || 'Failed to revoke share');
    }
  },

  // ── Product comments ────────────────────────────────────────────
  listProductComments: async (productId: string): Promise<ProductComment[]> => {
    const res = await authFetch(`${API_BASE}/products/${productId}/comments`);
    if (!res.ok) throw new Error('Failed to fetch product comments');
    return res.json();
  },

  createProductComment: async (
    productId: string,
    text: string,
    author?: string,
  ): Promise<ReflectionResult> => {
    const res = await authFetch(`${API_BASE}/products/${productId}/comments`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, author: author || '' }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Failed to add comment' }));
      throw new Error(err.detail || 'Failed to add comment');
    }
    return res.json();
  },

  deleteProductComment: async (productId: string, commentId: string): Promise<void> => {
    const res = await authFetch(
      `${API_BASE}/products/${productId}/comments/${commentId}`,
      { method: 'DELETE' },
    );
    if (!res.ok) throw new Error('Failed to delete comment');
  },

  // ── Product rules (reflection memory) ───────────────────────────
  listProductRules: async (productId: string): Promise<ProductRule[]> => {
    const res = await authFetch(`${API_BASE}/products/${productId}/rules`);
    if (!res.ok) throw new Error('Failed to fetch product rules');
    return res.json();
  },

  createProductRule: async (
    productId: string,
    text: string,
    category?: string,
  ): Promise<ProductRule> => {
    const res = await authFetch(`${API_BASE}/products/${productId}/rules`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, category: category || 'scope' }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Failed to add rule' }));
      throw new Error(err.detail || 'Failed to add rule');
    }
    return res.json();
  },

  updateProductRule: async (
    productId: string,
    ruleId: string,
    patch: { text?: string; category?: string; status?: string },
  ): Promise<ProductRule> => {
    const res = await authFetch(`${API_BASE}/products/${productId}/rules/${ruleId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(patch),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Failed to update rule' }));
      throw new Error(err.detail || 'Failed to update rule');
    }
    return res.json();
  },

  deleteProductRule: async (productId: string, ruleId: string): Promise<void> => {
    const res = await authFetch(
      `${API_BASE}/products/${productId}/rules/${ruleId}`,
      { method: 'DELETE' },
    );
    if (!res.ok) throw new Error('Failed to delete rule');
  },

  reflectProduct: async (productId: string): Promise<ReflectionResult> => {
    const res = await authFetch(`${API_BASE}/products/${productId}/reflect`, {
      method: 'POST',
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Reflection failed' }));
      throw new Error(err.detail || 'Reflection failed');
    }
    return res.json();
  },

  createAssessment: async (product_name: string, description: string, file?: File, regulation?: string): Promise<AssessmentResponse> => {
    const formData = new FormData();
    formData.append('product_name', product_name);
    formData.append('description', description);
    formData.append('regulation', regulation || 'CRA');
    if (file) formData.append('file', file);
    const res = await authFetch(`${API_BASE}/assessments`, {
      method: 'POST',
      body: formData
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Failed to create assessment' }));
      throw new Error(err.detail || 'Failed to create assessment');
    }
    return res.json();
  },

  getObligations: async (id: string): Promise<Obligation[]> => {
    const res = await authFetch(`${API_BASE}/assessments/${id}/obligations`);
    if (!res.ok) throw new Error('Failed to fetch obligations');
    return res.json();
  },

  getQuestions: async (id: string): Promise<Question[]> => {
    const res = await authFetch(`${API_BASE}/assessments/${id}/questions`);
    if (!res.ok) throw new Error('Failed to fetch questions');
    return res.json();
  },

  getAnswers: async (id: string): Promise<Answer[]> => {
    const res = await authFetch(`${API_BASE}/assessments/${id}/answers`);
    if (!res.ok) return [];
    return res.json();
  },

  saveAnswers: async (id: string, answers: Answer[]): Promise<void> => {
    const res = await authFetch(`${API_BASE}/assessments/${id}/answers`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ answers })
    });
    if (!res.ok) throw new Error('Failed to save answers');
  },

  getReport: async (id: string): Promise<any> => {
    const res = await authFetch(`${API_BASE}/assessments/${id}/compliance-report`);
    if (!res.ok) throw new Error('Failed to get report');
    return res.json();
  },

  downloadAssessmentPdf: async (id: string): Promise<{ blob: Blob; filename: string }> => {
    const res = await authFetch(`${API_BASE}/assessments/${id}/compliance-report/pdf`);
    if (!res.ok) throw new Error('Failed to generate PDF');
    const blob = await res.blob();
    const filename = filenameFromDisposition(
      res.headers.get('content-disposition'),
      'compliance_report.pdf',
    );
    return { blob, filename };
  },

  downloadAssessmentExcel: async (
    id: string,
    includeAnswers = true,
  ): Promise<{ blob: Blob; filename: string }> => {
    const params = new URLSearchParams({ include_answers: String(includeAnswers) });
    const res = await authFetch(`${API_BASE}/assessments/${id}/export-excel?${params.toString()}`);
    if (!res.ok) throw new Error('Failed to export Excel');
    const blob = await res.blob();
    const filename = filenameFromDisposition(
      res.headers.get('content-disposition'),
      'assessment_export.xlsx',
    );
    return { blob, filename };
  },

  getAssessments: async (regulation?: string): Promise<AssessmentListItem[]> => {
    const params = regulation ? `?regulation=${encodeURIComponent(regulation)}` : '';
    const res = await authFetch(`${API_BASE}/assessments${params}`);
    if (!res.ok) throw new Error('Failed to fetch assessments');
    return res.json();
  },

  getEvidence: async (): Promise<any[]> => {
    const res = await authFetch(`${API_BASE}/evidence`);
    if (!res.ok) throw new Error('Failed to fetch evidence');
    return res.json();
  },

  uploadEvidence: async (file: File): Promise<{ filename: string, stored_as: string }> => {
    const formData = new FormData();
    formData.append('file', file);
    const res = await authFetch(`${API_BASE}/evidence/upload`, {
      method: 'POST',
      body: formData
    });
    if (!res.ok) throw new Error('Failed to upload evidence');
    return res.json();
  },

  getVerifications: async (oblId: string): Promise<Verification[]> => {
    const res = await authFetch(`${API_BASE}/obligations/${oblId}/verifications`);
    if (!res.ok) throw new Error('Failed to fetch verifications');
    return res.json();
  },

  updateObligation: async (oblId: string, data: Partial<Pick<Obligation, 'action' | 'trigger' | 'deadline'>>): Promise<void> => {
    const res = await authFetch(`${API_BASE}/obligations/${oblId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    });
    if (!res.ok) throw new Error('Failed to update obligation');
  },

  updateVerification: async (verifId: string, data: Partial<Pick<Verification, 'type' | 'description' | 'evidence'>>): Promise<void> => {
    const res = await authFetch(`${API_BASE}/verifications/${verifId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    });
    if (!res.ok) throw new Error('Failed to update verification');
  },

  createVerification: async (oblId: string, data: { type: string; description: string; evidence: string }): Promise<Verification> => {
    const res = await authFetch(`${API_BASE}/obligations/${oblId}/verifications`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    });
    if (!res.ok) throw new Error('Failed to create verification');
    return res.json();
  },

  deleteVerification: async (verifId: string): Promise<void> => {
    const res = await authFetch(`${API_BASE}/verifications/${verifId}`, { method: 'DELETE' });
    if (!res.ok) throw new Error('Failed to delete verification');
  },

  deleteObligation: async (assessmentId: string, oblId: string): Promise<void> => {
    const res = await authFetch(`${API_BASE}/assessments/${assessmentId}/obligations/${oblId}`, { method: 'DELETE' });
    if (!res.ok) throw new Error('Failed to delete obligation');
  },

  getAssessment: async (id: string): Promise<AssessmentResponse> => {
    const res = await authFetch(`${API_BASE}/assessments/${id}`);
    if (!res.ok) throw new Error('Failed to fetch assessment');
    return res.json();
  },

  deleteAssessment: async (id: string): Promise<void> => {
    const res = await authFetch(`${API_BASE}/assessments/${id}`, { method: 'DELETE' });
    if (!res.ok) throw new Error('Failed to delete assessment');
  },

  updateAssessment: async (id: string, data: Partial<Omit<AssessmentResponse, 'id' | 'obligation_ids'>>): Promise<AssessmentResponse> => {
    const res = await authFetch(`${API_BASE}/assessments/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    });
    if (!res.ok) throw new Error('Failed to update assessment');
    return res.json();
  },

  lockAssessment: async (id: string): Promise<AssessmentResponse> => {
    const res = await authFetch(`${API_BASE}/assessments/${id}/lock`, {
      method: 'POST',
    });
    if (!res.ok) throw new Error('Failed to lock assessment');
    return res.json();
  },

  reclassifyAssessment: async (id: string): Promise<AssessmentResponse> => {
    const res = await authFetch(`${API_BASE}/assessments/${id}/reclassify`, {
      method: 'POST',
    });
    if (!res.ok) throw new Error('Failed to reclassify assessment');
    return res.json();
  },

  // ── Agent Chat ──────────────────────────────────────────────────
  agentChat: async (
    message: string,
    sessionId: string | null,
  ): Promise<AgentChatResponse> => {
    const res = await authFetch(`${API_BASE}/agent/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, session_id: sessionId }),
    });
    if (!res.ok) {
      const detail = await res.text();
      throw new Error(detail || 'Agent request failed');
    }
    return res.json();
  },

  agentReset: async (sessionId: string | null): Promise<void> => {
    await authFetch(`${API_BASE}/agent/reset`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: '', session_id: sessionId }),
    });
  },

  /**
   * Streaming variant of agentChat. Calls `onEvent` for each NDJSON line
   * received from the backend, and resolves with the final consolidated
   * response when the stream ends. Use this for long-running operations
   * (e.g. ingestion) to avoid gateway timeouts.
   */
  agentChatStream: async (
    message: string,
    sessionId: string | null,
    onEvent: (evt: AgentStreamEvent) => void,
  ): Promise<AgentChatResponse> => {
    const res = await authFetch(`${API_BASE}/agent/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/x-ndjson' },
      body: JSON.stringify({ message, session_id: sessionId }),
    });
    if (!res.ok || !res.body) {
      const detail = await res.text().catch(() => '');
      throw new Error(detail || `Agent stream failed (${res.status})`);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    const events: AgentChatEvent[] = [];
    let finalSession = sessionId || '';
    let finalReply = '';

    const handleLine = (line: string) => {
      const trimmed = line.trim();
      if (!trimmed) return;
      let evt: AgentStreamEvent;
      try {
        evt = JSON.parse(trimmed) as AgentStreamEvent;
      } catch {
        return;
      }
      if (evt.kind === 'session' && evt.session_id) {
        finalSession = evt.session_id;
      } else if (evt.kind === 'final') {
        finalSession = evt.session_id || finalSession;
        finalReply = evt.reply || '';
      } else if (evt.kind === 'progress') {
        // Progress events are transient UI hints — don't persist them in the
        // turn's event log.
      } else {
        events.push(evt as AgentChatEvent);
      }
      onEvent(evt);
    };

    // eslint-disable-next-line no-constant-condition
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let idx: number;
      while ((idx = buffer.indexOf('\n')) >= 0) {
        const line = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 1);
        handleLine(line);
      }
    }
    if (buffer.trim()) handleLine(buffer);

    return { session_id: finalSession, reply: finalReply, events };
  },
};

// ── Agent Chat types ────────────────────────────────────────────────
export interface AgentChatEvent {
  kind: 'tool_call' | 'tool_result' | 'transfer' | 'text' | 'error' | 'progress';
  author: string | null;
  name: string | null;
  args: unknown;
  result: unknown;
  text: string | null;
  current?: number;
  total?: number;
}

/** Discriminated union of everything the streaming endpoint may emit. */
export type AgentStreamEvent =
  | { kind: 'session'; session_id: string }
  | { kind: 'final'; session_id: string; reply: string }
  | { kind: 'progress'; author?: string | null; text?: string | null; current?: number; total?: number }
  | AgentChatEvent;

export interface AgentChatResponse {
  session_id: string;
  reply: string;
  events: AgentChatEvent[];
}
