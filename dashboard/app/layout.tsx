import './globals.css';
import type { Metadata, Viewport } from 'next';

export const metadata: Metadata = {
  title: 'Client Intelligence',
  description: 'Private competitive-intel reports',
  robots: { index: false, follow: false },
  // Versioned URL forces browsers to refetch the tab icon instead of reusing a
  // stale cached "no favicon" entry from when /favicon.ico was still auth-gated.
  icons: { icon: [{ url: '/favicon.ico?v=2', sizes: 'any' }] },
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
};

const themeScript = `(function(){try{var t=localStorage.getItem('theme');if(t==='dark'||t==='light'){document.documentElement.classList.add(t);}}catch(e){}})();`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
