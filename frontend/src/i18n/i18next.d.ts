import 'i18next'
import type en from './locales/en'

// Type-checked translation keys: t('cameras.title') is valid, t('cameras.typo') is a compile error.
declare module 'i18next' {
  interface CustomTypeOptions {
    defaultNS: 'translation'
    resources: { translation: typeof en }
  }
}
