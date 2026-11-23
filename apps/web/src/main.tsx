import { createRoot } from 'react-dom/client'
import App from './App.tsx'
import './index.css'
import { RELEASE, SENTRY_DSN } from './lib/config'

if (SENTRY_DSN) void import('./lib/errorReports').then((m) => m.startErrorReports(SENTRY_DSN, RELEASE));

createRoot(document.getElementById("root")!).render(<App />);
