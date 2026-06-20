import { useState, useCallback, useEffect } from 'react'
import { useACE } from './useACE.js'
import DeviceCard from './components/DeviceCard.jsx'
import Header from './components/Header.jsx'
import SettingsPanel from './components/SettingsPanel.jsx'
import DiagnosticsPanel from './components/DiagnosticsPanel.jsx'
import styles from './App.module.css'

export default function App() {
  const { devices, connected, logs, config, api, addLog } = useACE()
  const [activeTab, setActiveTab] = useState('devices')
  const [theme, setTheme] = useState(() => localStorage.getItem('acelink-theme') || 'dark')
  const [busy, setBusy] = useState(false)

  const [probeResult, setProbeResult] = useState(null)

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    localStorage.setItem('acelink-theme', theme)
  }, [theme])

  const [ready, setReady] = useState(false)

  useEffect(() => {
    (async () => {
      const res = await handleAction(() => api.probeHardware(), 'Probe ACE')
      if (!res?.error) setProbeResult(res)
      setReady(true)
    })()
  }, [])

  const toggleTheme = useCallback(() => {
    setTheme(prev => prev === 'dark' ? 'light' : 'dark')
  }, [])

  const handleAction = useCallback(async (fn, description) => {
    if (busy) return { error: 'Another action is in progress' }
    setBusy(true)
    try {
      addLog('info', `Start: ${description}`)
      const result = await fn()
      addLog('info', `Done: ${description}: ${JSON.stringify(result)}`)
      return result
    } catch (err) {
      addLog('error', `Failed: ${description}: ${err.message}`)
      return { error: err.message }
    } finally {
      setBusy(false)
    }
  }, [addLog, busy])

  const deviceList = Object.entries(devices)
  const aceDetected = deviceList.length > 0
  const aceReady = aceDetected && deviceList.some(([, d]) => d?.connected && d?.model)

  const aceSummary = aceReady
    ? `${deviceList[0]?.[1]?.model || 'ACE'} on ${deviceList[0]?.[1]?.port || '?'}`
    : connected
      ? aceDetected
        ? 'ACE port configured but not responding. Check Settings > Hardware Probe.'
        : 'No ACE device found. Configure the serial port in Settings.'
      : null

  return (
    <div className={styles.app}>
      {!ready ? (
        <div className={styles.loading}>
          <div className={styles.loadingMark}>
            <span />
            <span />
            <span />
          </div>
          <div className={styles.loadingTitle}>ACELink</div>
          <div className={styles.loadingText}>Connecting to ACE...</div>
        </div>
      ) : (
        <>
      <Header
        mockMode={Boolean(config?.mock_mode)}
        theme={theme}
        onToggleTheme={toggleTheme}
      />

          {!aceReady && connected && (
            <div className={`${styles.banner} ${aceDetected ? styles.bannerWarn : styles.bannerInfo}`}>
              {aceSummary}
            </div>
          )}

      <nav className={styles.tabs} aria-label="Main views">
        <button
          className={activeTab === 'devices' ? styles.tabActive : styles.tab}
          onClick={() => setActiveTab('devices')}
        >
          Device
          {aceReady && <span className={styles.aceDot} />}
        </button>
        <button
          className={activeTab === 'settings' ? styles.tabActive : styles.tab}
          onClick={() => setActiveTab('settings')}
        >
          Settings
        </button>
        <button
          className={activeTab === 'diagnostics' ? styles.tabActive : styles.tab}
          onClick={() => setActiveTab('diagnostics')}
        >
          Diagnostics
          {logs.length > 0 && <span className={styles.badge}>{Math.min(logs.length, 99)}</span>}
        </button>
      </nav>

      <main className={styles.main}>
        {activeTab === 'devices' && (
          <div className={styles.devices}>
            {deviceList.length === 0 && (
              <div className={styles.empty}>
                <div className={styles.emptyMark}>
                  <span />
                  <span />
                  <span />
                </div>
                <div className={styles.emptyTitle}>No ACE detected</div>
                <div className={styles.emptyText}>
                  {ready && connected
                    ? 'Configure the serial port and ACE model in Settings, then run the Hardware Probe.'
                    : 'Connecting to the controller...'}
                </div>
              </div>
            )}
            {ready && deviceList.map(([idx, device]) => (
              <DeviceCard
                key={idx}
                deviceIndex={parseInt(idx)}
                device={device}
                api={api}
                onAction={handleAction}
                addLog={addLog}
                busy={busy}
                maxDryerTemp={config?.max_dryer_temp ?? 55}
                minDryerTemp={config?.min_dryer_temp ?? 35}
              />
            ))}
          </div>
        )}
        {activeTab === 'settings' && (
          <SettingsPanel
            config={config}
            api={api}
            onAction={handleAction}
          />
        )}
        {activeTab === 'diagnostics' && (
          <DiagnosticsPanel
            config={config}
            api={api}
            onAction={handleAction}
            logs={logs}
            probeResult={probeResult}
            onRefreshProbe={async () => {
              const res = await handleAction(() => api.probeHardware(), 'Probe ACE')
              if (!res?.error) setProbeResult(res)
            }}
          />
        )}
      </main>
        </>
      )}
    </div>
  )
}
