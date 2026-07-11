import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    fallbackLng: 'en',
    debug: false,
    interpolation: {
      escapeValue: false, // React already safe from xss
    },
    resources: {
      en: {
        translation: {
          'app.title': 'Owlynn',
          'chat.placeholder': 'Ask Owlynn...',
        }
      }
    }
  });

export default i18n;
