import { createRoot } from 'react-dom/client'
import App from './App'
import './styles/tokens.css'
import './styles/fonts.css'
import './styles/base.css'
import './styles/components.css'
import './styles/views.css'

createRoot(document.getElementById('root')!).render(<App />)
