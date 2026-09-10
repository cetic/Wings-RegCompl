import { FileQuestion } from 'lucide-react';

export default function PlaceholderView() {
  return (
    <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
      <FileQuestion size={48} style={{ margin: '0 auto 1rem', opacity: 0.5 }} />
      <h2>Module Under Construction</h2>
      <p style={{ maxWidth: '400px', margin: '1rem auto' }}>
        This module is part of the broader RegComply platform and will be available in a future update.
      </p>
    </div>
  );
}
