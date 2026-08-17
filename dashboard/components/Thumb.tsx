'use client';

import { useState } from 'react';

export default function Thumb({ id, alt = '' }: { id?: string | null; alt?: string }) {
  const [err, setErr] = useState(false);
  if (!id || err) {
    return (
      <span className="thumb fallback" aria-hidden="true">
        ▶
      </span>
    );
  }
  return (
    <img
      className="thumb"
      src={`https://i.ytimg.com/vi/${id}/hqdefault.jpg`}
      alt={alt}
      loading="lazy"
      referrerPolicy="no-referrer"
      onError={() => setErr(true)}
    />
  );
}
