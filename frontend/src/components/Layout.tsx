import { useTranslation } from 'react-i18next'
import { NavLink, Outlet } from 'react-router'
import { LANGUAGES } from '../i18n'
import styles from './Layout.module.css'

export default function Layout() {
  const { t, i18n } = useTranslation()

  const links = [
    { to: '/', label: t('nav.home') },
    { to: '/cameras', label: t('nav.cameras') },
  ]

  return (
    <div className={styles.shell}>
      <header className={styles.header}>
        <span className={styles.brand}>dartscore</span>
        <nav className={styles.nav}>
          {links.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              end
              className={({ isActive }) => (isActive ? `${styles.link} ${styles.active}` : styles.link)}
            >
              {link.label}
            </NavLink>
          ))}
        </nav>
        <select
          className={styles.language}
          aria-label={t('language.label')}
          value={i18n.resolvedLanguage}
          onChange={(e) => void i18n.changeLanguage(e.target.value)}
        >
          {LANGUAGES.map((lang) => (
            <option key={lang.code} value={lang.code}>
              {lang.label}
            </option>
          ))}
        </select>
      </header>
      <main className={styles.main}>
        <Outlet />
      </main>
    </div>
  )
}
