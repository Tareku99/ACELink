import { useEffect, useState } from 'react'
import SlotRow from './SlotRow.jsx'
import DryerPanel from './DryerPanel.jsx'
import styles from './DeviceCard.module.css'

const PRESET_STORAGE_KEY = 'acelink-dryer-presets'

export default function DeviceCard({ deviceIndex, device, api, onAction, addLog, busy, maxDryerTemp = 55, minDryerTemp = 35 }) {
  const di = deviceIndex
  const [localBusy, setLocalBusy] = useState(false)
  const [temp, setTemp] = useState(55)
  const [duration, setDuration] = useState(240)
  const [runForever, setRunForever] = useState(false)
  const [presetName, setPresetName] = useState('')
  const [activePresetId, setActivePresetId] = useState('')
  const [presets, setPresets] = useState(() => loadPresets())
  const slots = device.slots || []
  const loadedSlots = slots.filter(slot => slot.status === 'LOADED' || slot.status === 'FEEDING').length

  useEffect(() => {
    localStorage.setItem(PRESET_STORAGE_KEY, JSON.stringify(presets))
  }, [presets])

  const locked = Boolean(busy) || localBusy

  const savePreset = () => {
    const name = presetName.trim()
    if (!name) return
    const existing = presets.find(p => p.name === name)
    if (existing && !window.confirm(`Preset "${name}" already exists. Update it?`)) {
      return
    }
    const preset = {
      id: existing?.id || crypto.randomUUID(),
      name,
      temp,
      duration,
      runForever,
    }
    setPresets(prev => {
      const filtered = prev.filter(p => p.id !== preset.id)
      if (existing) {
        const idx = prev.findIndex(p => p.id === existing.id)
        const next = [...filtered]
        next.splice(Math.min(idx, next.length), 0, preset)
        return next
      }
      return [preset, ...filtered]
    })
    setActivePresetId(preset.id)
    setPresetName('')
    addLog('info', `${existing ? 'Updated' : 'Saved'} dryer preset "${preset.name}"`)
  }

  const applyPreset = preset => {
    setTemp(preset.temp)
    setDuration(preset.duration)
    setRunForever(preset.runForever)
    setPresetName(preset.name)
    setActivePresetId(preset.id)
    addLog('info', `Loaded preset "${preset.name}"`)
  }

  const deletePreset = id => {
    const preset = presets.find(item => item.id === id)
    if (preset && !window.confirm(`Delete dryer preset "${preset.name}"?`)) {
      return
    }
    setPresets(prev => prev.filter(preset => preset.id !== id))
    if (activePresetId === id) {
      setActivePresetId('')
      setPresetName('')
    }
    if (preset) {
      addLog('warn', `Deleted dryer preset "${preset.name}"`)
    }
  }

  const updateTemp = value => {
    setTemp(value)
  }

  const updateDuration = value => {
    setDuration(value)
  }

  const updateRunForever = value => {
    setRunForever(value)
  }

  return (
    <div className={styles.card}>
      <div className={styles.titleBar}>
        <div className={styles.titleLeft}>
          <span className={styles.deviceId}>{device.model || 'ACE'}</span>
          {device.firmware_version && (
            <span className={styles.fw}>fw {device.firmware_version}</span>
          )}
        </div>
      </div>

      <div className={styles.workspace}>
        <section className={styles.slotsPanel}>
          <div className={styles.sectionHead}>
            <div>
              <div className={styles.sectionTitleRow}>
                <h2>Slots</h2>
                <span className={styles.loadedBadge}>{loadedSlots}/{slots.length || 4} loaded</span>
              </div>
              <p>Filament state and manual actions</p>
            </div>
          </div>

          <div className={styles.slots}>
            {slots.map((slot, i) => (
              <SlotRow
                key={i}
                slot={slot}
                slotIndex={i}
                deviceIndex={di}
                api={api}
                onAction={onAction}
                deviceConnected={device.connected}
                busy={locked}
              />
            ))}
          </div>
        </section>

        <aside className={styles.sideRail}>
          <section className={styles.sideSection}>
            <div className={styles.sectionHead}>
              <div>
                <h2>Dryer</h2>
                <p>Temperature and duration</p>
              </div>
            </div>
            <DryerPanel
              deviceIndex={di}
              device={device}
              api={api}
              onAction={onAction}
              temp={temp}
              setTemp={updateTemp}
              duration={duration}
              setDuration={updateDuration}
              runForever={runForever}
              setRunForever={updateRunForever}
              busy={locked}
              maxTemp={maxDryerTemp}
              minTemp={minDryerTemp}
            />
          </section>
        </aside>
      </div>

      <section className={styles.presetsPanel}>
        <div className={styles.sectionHead}>
          <div>
            <h2>Dryer Presets</h2>
            <p>Save and reload common temperature profiles</p>
          </div>
          <div className={styles.presetSave}>
            <input
              className={styles.presetInput}
              type="text"
              value={presetName}
              placeholder="Preset name"
              onChange={e => setPresetName(e.target.value)}
            />
            <button
              className={styles.btnCompact}
              type="button"
              disabled={!presetName.trim()}
              onClick={savePreset}
            >
              Save Preset
            </button>
          </div>
        </div>

        {presets.length === 0 ? (
          <div className={styles.presetEmpty}>
            Set dryer temperature and duration, name the profile, then save it here.
          </div>
        ) : (
          <div className={styles.presetGrid}>
            {presets.map(preset => (
              <div
                className={`${styles.presetCard} ${activePresetId === preset.id ? styles.presetCardActive : ''}`}
                key={preset.id}
              >
                <div className={styles.presetInfo}>
                  <div className={styles.presetNameRow}>
                    <span>{preset.name}</span>
                  </div>
                  <div className={styles.presetValues}>
                    <div>
                      <span>Temp</span>
                      <strong>{preset.temp}°C</strong>
                    </div>
                    <div>
                      <span>Duration</span>
                      <strong>{formatDuration(preset.duration, preset.runForever)}</strong>
                    </div>
                  </div>
                </div>
                <div className={styles.presetActions}>
                  <button
                    className={styles.btnPresetLoad}
                    type="button"
                    onClick={() => applyPreset(preset)}
                  >
                    Load
                  </button>
                  <button
                    className={styles.btnDeletePreset}
                    type="button"
                    title={`Delete ${preset.name}`}
                    onClick={() => deletePreset(preset.id)}
                  >
                    Delete
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}

function formatDuration(duration, runForever) {
  if (runForever) return 'Until stopped'
  if (duration >= 60) return `${Math.round(duration / 60)}h`
  return `${duration}min`
}

function loadPresets() {
  try {
    const raw = localStorage.getItem(PRESET_STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed
      .filter(item => item && typeof item.name === 'string')
      .map(item => ({
        id: item.id || crypto.randomUUID(),
        name: item.name,
        temp: Number(item.temp) || 55,
        duration: Number(item.duration) || 240,
        runForever: Boolean(item.runForever),
      }))
  } catch {
    return []
  }
}
