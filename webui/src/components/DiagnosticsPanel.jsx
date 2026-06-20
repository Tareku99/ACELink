import { useState } from 'react'
import styles from './DiagnosticsPanel.module.css'

export default function DiagnosticsPanel({ api, onAction, logs = [], probeResult, onRefreshProbe }) {
  const [busy, setBusy] = useState(false)

  const refresh = async () => {
    if (!onRefreshProbe) return
    setBusy(true)
    await onRefreshProbe()
    setBusy(false)
  }

  return (
    <div className={styles.panel}>
      <div className={styles.header}>
        <div>
          <div className={styles.title}>Diagnostics</div>
          <div className={styles.subtitle}>Connection probe and event log</div>
        </div>
        <div className={styles.actions}>
          <button className={styles.btnPrimary} disabled={busy} onClick={refresh}>
            {busy ? 'Probing...' : 'Probe ACE'}
          </button>
        </div>
      </div>

      {probeResult && (
        <section className={styles.section}>
          <div className={styles.sectionTitle}>Probe Result</div>
          {probeResult.error && <div className={styles.error}>{probeResult.error}</div>}
          {probeResult.ok && (
            <div className={styles.summaryGrid}>
              <Summary label="Model" value={probeResult.model || '?'} />
              <Summary label="Protocol" value={probeResult.protocol || '?'} />
              <Summary label="UID" value={probeResult.uid ? probeResult.uid.join(' / ') : 'None'} />
              <Summary label="Temp" value={probeResult.temp?.env_temp != null ? `${probeResult.temp.env_temp.toFixed(1)}°C` : '?'} />
              <Summary label="Humidity" value={probeResult.temp?.env_humidity != null ? `${probeResult.temp.env_humidity.toFixed(1)}%` : '?'} />
            </div>
          )}
        </section>
      )}

      <section className={styles.section}>
        <div className={styles.sectionTitle}>Event Log</div>
        {logs.length === 0 ? (
          <div className={styles.empty}>No events yet.</div>
        ) : (
          <div className={styles.logList}>
            {logs.slice(0, 200).map(log => (
              <div className={styles.logRow} key={log.id}>
                <span className={styles.logTime}>{log.time}</span>
                <span className={`${styles.logLevel} ${styles[`level_${log.level}`] || ''}`}>
                  {log.level}
                </span>
                <span className={styles.logMsg}>{log.msg}</span>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}

function Summary({ label, value }) {
  return (
    <div className={styles.summary}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  )
}
