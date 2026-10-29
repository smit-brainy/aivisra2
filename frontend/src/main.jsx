import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';

// Styles: legacy app shell first (so i-Netra tokens/fonts win), then the
// verbatim i-Netra design system extracted from the prototype, then the
// shared interaction layer (hover/focus helpers).
import './styles/theme.css';
import './styles/fonts.css';
import './styles/foundations.css';
import './styles/buttons.css';
import './styles/interactions.css';

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
