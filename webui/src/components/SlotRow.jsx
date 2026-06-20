import { useState } from 'react'
import styles from './SlotRow.module.css'

const STATUS_COLOR = {
  EMPTY:      'var(--text3)',
  READY:      'var(--good)',
  LOADED:     'var(--good)',
  FEEDING:    'var(--text)',
  RETRACTING: 'var(--warn)',
  PRELOAD:    'var(--text2)',
  UNWINDING:  'var(--warn)',
  ASSISTING:  'color-mix(in srgb, var(--good) 70%, var(--text))',
  FEED_ERROR: 'var(--bad)',
  ROLLBACK_ERROR: 'var(--bad)',
  ASSIST_ERROR: 'var(--bad)',
  PRELOAD_ERROR: 'var(--bad)',
  STUCK:      'var(--bad)',
  TANGLED:    'var(--bad)',
  MOTOR_ERROR: 'var(--bad)',
  ERROR:      'var(--bad)',
}

const STATUS_LABEL = {
  EMPTY:      'Empty',
  READY:      'Ready',
  LOADED:     'Ready',
  FEEDING:    'Feeding',
  RETRACTING: 'Retracting',
  PRELOAD:    'Preload',
  UNWINDING:  'Unwinding',
  ASSISTING:  'Assisting',
  FEED_ERROR: 'Feed error',
  ROLLBACK_ERROR: 'Retract error',
  ASSIST_ERROR: 'Assist error',
  PRELOAD_ERROR: 'Preload error',
  STUCK:      'Stuck',
  TANGLED:    'Tangled',
  MOTOR_ERROR: 'Motor error',
  ERROR:      'Error',
}

export default function SlotRow({ slot, slotIndex, deviceIndex, api, onAction, deviceConnected, busy: globalBusy = false }) {
  const [busy, setBusy] = useState(false)
  const [editing, setEditing] = useState(false)
  const [manualType, setManualType] = useState('')
  const [manualColor, setManualColor] = useState('')
  const di = deviceIndex
  const si = slotIndex

  const run = async (fn, desc) => {
    setBusy(true)
    try { await onAction(fn, desc) }
    finally { setBusy(false) }
  }

  const [manual, setManual] = useState(null)
  const effectiveManual = slot.rfid_present && slot.filament_type ? null : manual

  const saveManual = () => {
    if (!manualType.trim()) return
    setManual({ type: manualType.trim(), color: manualColor.trim() })
    setEditing(false)
    setManualType('')
    setManualColor('')
  }

  const display = manual || slot
  const filamentType = slot.filament_type || effectiveManual?.type || ''
  const color = slot.color || effectiveManual?.color || ''
  const hasData = filamentType || color
  const effectiveStatus = effectiveManual ? 'READY' : slot.status
  const statusColor = STATUS_COLOR[effectiveStatus] || STATUS_COLOR.EMPTY
  const isBusy = effectiveStatus === 'FEEDING' || effectiveStatus === 'RETRACTING' || busy
  const locked = globalBusy || busy || !deviceConnected
  const speed = 80

  return (
    <div className={styles.row}>
      <div className={styles.slotNum}>
        <div className={styles.indicator} style={{ background: statusColor }} />
        <span className={styles.num}>{slotIndex}</span>
      </div>

      <div className={styles.info}>
        <div className={styles.topLine}>
          {effectiveStatus !== 'EMPTY' && (
            <span className={styles.status} style={{ color: statusColor }}>
              {STATUS_LABEL[effectiveStatus] || effectiveStatus?.toUpperCase() || '?'}
            </span>
          )}
          {filamentType && (
            <span className={styles.tag}>{filamentType}</span>
          )}
          {slot.brand && (
            <span className={styles.tag}>{slot.brand}</span>
          )}
        </div>
        {color && (
          <div className={styles.colorLine}>
            <span className={styles.colorName}>{color}</span>
            {slot.rfid_present && <span className={styles.rfidBadge}>RFID</span>}
            {effectiveManual && <span className={styles.manualBadge}>Manual</span>}
          </div>
        )}
        {!hasData && effectiveStatus === 'EMPTY' && (
          <div className={styles.emptyLabel}>Insert spool and feed to detect</div>
        )}

        {editing && (
          <div className={styles.editForm}>
            <input className={styles.editInput} placeholder="Filament type" value={manualType} onChange={e => setManualType(e.target.value)} />
            <input className={styles.editInput} placeholder="Color (optional)" value={manualColor} onChange={e => setManualColor(e.target.value)} />
            <button className={styles.btnSlot} onClick={saveManual}>Save</button>
            <button className={styles.btnSlot} onClick={() => setEditing(false)}>Cancel</button>
          </div>
        )}
      </div>

      <div className={styles.actions}>
        <button
          className={`${styles.btnSlot} ${styles.btnFeed}`}
          disabled={locked}
          title="Feed"
          onClick={() => run(() => api.feed(di, si), `Feed slot ${si}`)}
        >Feed</button>
        <button
          className={`${styles.btnSlot} ${styles.btnFeed}`}
          disabled={locked}
          title="Retract"
          onClick={() => run(() => api.retract(di, si), `Retract slot ${si}`)}
        >Retract</button>
        {!hasData && !editing && (
          <button
            className={`${styles.btnSlot} ${styles.btnFeed}`}
            title="Manually load a spool"
            disabled={locked}
            onClick={() => setEditing(true)}
          >Load spool</button>
        )}
      </div>
    </div>
  )
}
