import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { initI18n } from './i18n'
import { initPrinting } from '@ury/core'
import { getQzCertificate, signQzPayload } from './lib/invoice-api'

initPrinting({ sign: signQzPayload, certificate: getQzCertificate })

initI18n().then(() => {
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <App />
    </StrictMode>,
  )
})

  