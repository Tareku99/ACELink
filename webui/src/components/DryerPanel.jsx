import { useState } from 'react'
import styles from './DryerPanel.module.css'

export default function DryerPanel({
  deviceIndex,
  device,
  api,
  onAction,
  temp,
  setTemp,
  duration,
  setDuration,
  runForever,
  setRunForever,
  busy: globalBusy = false,
  maxTemp = 55,
  minTemp = 35,
}) {
  const [localBusy, setLocalBusy] = useState(false)
  const [durationUnit, setDurationUnit] = useState('min')

  const run = async (fn, desc) => {
    setLocalBusy(true)
    try { await onAction(fn, desc) }
    finally { setLocalBusy(false) }
  }

  const busy = globalBusy || localBusy

  const di = deviceIndex
  const active = device.dryer_active

  const displayDuration = durationUnit === 'h' ? duration / 60 : duration

  const setDisplayDuration = (value) => {
    setDuration(durationUnit === 'h' ? value * 60 : value)
  }

  const switchUnit = (unit) => {
    if (unit === durationUnit) return
    if (unit === 'h') {
      setDuration(Math.round(duration / 60))
    } else {
      setDuration(duration * 60)
    }
    setDurationUnit(unit)
  }

  const startDuration = runForever ? 0 : duration

  const activeDurationText = active
    ? device.dryer_duration_remaining > 0
      ? `${Math.round(device.dryer_duration_remaining / 60)}min remaining`
      : 'Until stopped'
    : ''

  return (
    <div className={styles.panel}>
      <div className={styles.statusBar}>
        <div className={styles.statusLeft}>
          <span className={`${styles.heatMark} ${active ? styles.heatMarkActive : ''}`} />
          <div className={styles.statusInfo}>
            <div className={styles.statusTitle}>
              <span>Status</span>
              <strong>{active ? 'Active' : 'Off'}</strong>
            </div>
            {active && (
              <div className={styles.statusDetail}>
                {device.dryer_temp}°C / target {device.dryer_target_temp}°C
                {activeDurationText && ` — ${activeDurationText}`}
              </div>
            )}
          </div>
        </div>
      </div>

      <div className={styles.controls}>
        <div className={styles.controlRow}>
          <div className={styles.inputGroup}>
            <label className={styles.fieldLabel}>Temperature</label>
            <div className={styles.inputWithRange}>
              <input
                type="number"
                min={minTemp}
                max={maxTemp}
                value={temp}
                className={styles.numberInput}
                disabled={active}
                onChange={e => setTemp(Number(e.target.value) || minTemp)}
                onBlur={e => {
                  let v = Number(e.target.value)
                  if (isNaN(v)) v = minTemp
                  setTemp(Math.min(maxTemp, Math.max(minTemp, v)))
                }}
              />
              <span className={styles.fieldHint}>{minTemp}–{maxTemp}°C</span>
            </div>
          </div>
        </div>

        <div className={styles.controlRow}>
          <div className={styles.inputGroup}>
            <label className={styles.fieldLabel}>Duration</label>
            <div className={styles.durationRow}>
              <input
                type="number"
                min={1}
                value={displayDuration}
                className={styles.numberInput}
                disabled={active || runForever}
                onChange={e => setDisplayDuration(Math.max(1, Number(e.target.value)))}
              />
              <select
                className={styles.unitSelect}
                value={durationUnit}
                onChange={e => switchUnit(e.target.value)}
                disabled={active || runForever}
              >
                <option value="min">min</option>
                <option value="h">h</option>
              </select>
            </div>
            <label className={styles.toggleRow}>
              <input
                type="checkbox"
                checked={runForever}
                disabled={active}
                onChange={e => setRunForever(e.target.checked)}
              />
              <span>Run until stopped</span>
            </label>
          </div>
        </div>

        {active ? (
          <button
            className={styles.btnStop}
            disabled={busy || !device.connected}
            onClick={() => {
              if (window.confirm('Stop the dryer now?')) {
                run(() => api.dryerStop(di), 'Stop dryer')
              }
            }}
          >
            Stop Dryer
          </button>
        ) : (
          <button
            className={styles.btnStart}
            disabled={busy || !device.connected}
            onClick={() => run(
              () => api.dryerStart(di, temp, startDuration),
              `Start dryer ${temp}°C ${runForever ? 'until stopped' : `${duration}min`}`
            )}
          >
            Start Dryer
          </button>
        )}
      </div>
    </div>
  )
}
