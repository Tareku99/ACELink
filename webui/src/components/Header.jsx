import styles from './Header.module.css'

export default function Header({ mockMode, theme, onToggleTheme }) {
  return (
    <header className={styles.header}>
      <div className={styles.brandBlock}>
        <div className={styles.mark} aria-hidden="true">
          <span />
          <span />
          <span />
        </div>
        <div>
          <div className={styles.logoText}>ACELink</div>
          <div className={styles.subtitle}>Local ACE controller</div>
        </div>
      </div>

      <div className={styles.actions}>
        {mockMode && <span className={styles.mockBadge}>Mock</span>}
      </div>

      <button
        className={styles.themeToggle}
        type="button"
        onClick={onToggleTheme}
        aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
        title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
      >
        <span className={theme === 'dark' ? styles.toggleKnobDark : styles.toggleKnobLight} />
        <span>{theme === 'dark' ? 'Dark' : 'Light'}</span>
      </button>
    </header>
  )
}
