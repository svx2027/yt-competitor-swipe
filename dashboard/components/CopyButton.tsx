'use client';

import { useState } from 'react';

// Small copy-to-clipboard button, styled to sit in the top-right corner of a
// code/raw block (the same affordance Claude's chat code blocks use). Copies
// the full `text` in one click; flips to a confirmed state for ~1.6s.
export default function CopyButton({ text, label = 'Copy' }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      // navigator.clipboard needs a secure context (https or localhost); prod
      // is https and dev is localhost, so this is the normal path.
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text);
      } else {
        // Fallback for any non-secure context: a hidden textarea + execCommand.
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
      }
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      // Clipboard blocked (permissions, unsupported): leave the label as-is
      // rather than showing a false success.
      setCopied(false);
    }
  }

  return (
    <button
      type="button"
      className={`copy-btn${copied ? ' copied' : ''}`}
      onClick={copy}
      aria-label={copied ? 'Copied to clipboard' : 'Copy to clipboard'}
      title={copied ? 'Copied' : 'Copy'}
    >
      <span className="copy-ico" aria-hidden="true">
        {copied ? (
          <svg viewBox="0 0 16 16" width="13" height="13" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <path d="M3.5 8.5l3 3 6-6.5" />
          </svg>
        ) : (
          <svg viewBox="0 0 16 16" width="13" height="13" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <rect x="5.5" y="5.5" width="8" height="8" rx="1.5" />
            <path d="M10.5 5.5V4A1.5 1.5 0 0 0 9 2.5H4A1.5 1.5 0 0 0 2.5 4v5A1.5 1.5 0 0 0 4 10.5h1.5" />
          </svg>
        )}
      </span>
      {copied ? 'Copied' : label}
    </button>
  );
}
