import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App.jsx'
import { registerServiceWorker, serviceWorkerSupported } from './pwa/serviceWorker.js'
// Side effect: catches the one-shot `beforeinstallprompt` before Paramètres is ever opened.
import './pwa/installPrompt.js'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
)

// After load, so registering (and the worker's precache) never competes with the first render.
// A failure only costs installability and the offline page; the app itself is unaffected.
if (serviceWorkerSupported()) {
  window.addEventListener('load', () => { registerServiceWorker().catch(() => {}) })
}
