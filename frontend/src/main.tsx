import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import dayjs from 'dayjs';
import 'dayjs/locale/ru';
import weekday from 'dayjs/plugin/weekday';
import localeData from 'dayjs/plugin/localeData';

dayjs.extend(weekday);
dayjs.extend(localeData);
dayjs.locale('ru');

import ThemedApp from './ThemedApp';
import { ThemeProvider } from './contexts/ThemeContext';
import { installConsoleCapture } from './utils/consoleCapture';
import './index.css';
import './styles/print.css';
import './aurora/styles/aurora.css';

installConsoleCapture();

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider>
      <ThemedApp />
    </ThemeProvider>
  </StrictMode>,
);
