import { createRoot } from 'react-dom/client';
import { DeepMeApp } from './DeepMeApp';
import './deepme.css';

createRoot(document.getElementById('root') as HTMLElement).render(
  <DeepMeApp />,
);
