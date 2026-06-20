import { useEffect, useState } from 'react'
import styles from './SettingsPanel.module.css'

const SETTINGS_SECTIONS = [
  {
    title: 'App',
    subtitle: 'Local web interface',
    fields: [
      { key: 'port', label: 'Web UI port', min: 1, max: 65535, step: 1, hint: 'Restart required' },
    ],
  },
  {
    title: 'Movement Defaults',
    subtitle: 'Used by all slots unless a slot override is enabled',
    fields: [
      { key: 'load_length', label: 'Load length', min: 0, max: 10000, step: 1, hint: 'mm' },
      { key: 'retract_length', label: 'Retract length', min: 0, max: 10000, step: 1, hint: 'mm' },
      { key: 'feed_speed', label: 'Feed speed', min: 1, max: 500, step: 1, hint: 'mm/s' },
      { key: 'retract_speed', label: 'Retract speed', min: 1, max: 500, step: 1, hint: 'mm/s' },
    ],
  },
]

const SLOT_FIELDS = [
  { key: 'feed_length', label: 'Feed', min: 0, max: 10000, step: 1, unit: 'mm' },
  { key: 'load_length', label: 'Load', min: 0, max: 10000, step: 1, unit: 'mm' },
  { key: 'retract_length', label: 'Retract', min: 0, max: 10000, step: 1, unit: 'mm' },
  { key: 'feed_speed', label: 'Feed speed', min: 1, max: 500, step: 1, unit: 'mm/s' },
  { key: 'retract_speed', label: 'Retract speed', min: 1, max: 500, step: 1, unit: 'mm/s' },
]

const emptySlotTuning = () => ({
  custom: false,
  feed_length: null,
  load_length: null,
  retract_length: null,
  feed_speed: null,
  retract_speed: null,
})

const normalizeSlotTuning = (slot = {}) => ({
  ...emptySlotTuning(),
  ...slot,
  custom: Boolean(slot.custom),
})

const normalizeConfig = (config) => ({
  ...config,
  slot_tuning: Array.from({ length: 4 }, (_, index) => (
    normalizeSlotTuning(config?.slot_tuning?.[index])
  )),
})

const numberOrNull = (value) => {
  if (value === '') return null
  return Number(value)
}

export default function SettingsPanel({ config, api, onAction }) {
  const [draft, setDraft] = useState(config ? normalizeConfig(config) : config)
  const [saveNotice, setSaveNotice] = useState('')

  useEffect(() => {
    if (config) {
      setDraft(normalizeConfig(config))
    }
  }, [config])

  if (!config || !draft) {
    return (
      <div className={styles.panel}>
        <div className={styles.empty}>Loading settings...</div>
      </div>
    )
  }

  const updateField = (key, value) => {
    setDraft(prev => ({
      ...prev,
      [key]: value,
    }))
  }

  const updateSlot = (slotIndex, key, value) => {
    setDraft(prev => ({
      ...prev,
      slot_tuning: prev.slot_tuning.map((slot, index) => (
        index === slotIndex ? { ...slot, [key]: value } : slot
      )),
    }))
  }

  const save = async () => {
    setSaveNotice('')
    const result = await onAction(
      () => api.saveConfig(draft),
      'Save settings'
    )
    if (result?.error) {
      setSaveNotice(`Save failed: ${result.error}`)
      return result
    }
    if (result?.restart_required) {
      setSaveNotice('Saved. Restart ACELink to apply the new port.')
    } else {
      setSaveNotice('Saved to acelink.config.json.')
    }
    return result
  }

  const reload = async () => {
    setSaveNotice('')
    const fresh = await onAction(
      () => api.getConfig(),
      'Reload settings'
    )
    if (fresh?.error) {
      setSaveNotice(`Reload failed: ${fresh.error}`)
      return fresh
    }
    if (fresh) {
      setDraft(normalizeConfig(fresh))
      setSaveNotice('Reloaded from acelink.config.json.')
    }
    return fresh
  }

  const renderField = (field) => {
    const value = draft[field.key] ?? ''
    return (
      <label key={field.key} className={styles.field}>
        <div className={styles.fieldTop}>
          <span className={styles.fieldLabel}>{field.label}</span>
          <span className={styles.fieldHint}>{field.hint}</span>
        </div>
        {field.type === 'select' ? (
          <select
            className={styles.input}
            value={value}
            onChange={e => updateField(field.key, e.target.value)}
          >
            {field.options.map(option => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
        ) : (
          <input
            className={styles.input}
            type={field.type === 'checkbox' ? 'checkbox' : field.type || 'number'}
            min={field.min}
            max={field.max}
            step={field.step}
            checked={field.type === 'checkbox' ? Boolean(draft[field.key]) : undefined}
            value={field.type === 'checkbox' ? undefined : value}
            onChange={e => updateField(
              field.key,
              field.type === 'checkbox'
                ? e.target.checked
                : field.type === 'text'
                  ? e.target.value
                  : Number(e.target.value)
            )}
          />
        )}
      </label>
    )
  }

  return (
    <div className={styles.panel}>
      <div className={styles.header}>
        <div>
          <div className={styles.title}>Control Profile</div>
          <div className={styles.subtitle}>Saved to <code>acelink.config.json</code> — port changes require a restart</div>
        </div>
        <div className={styles.actions}>
          <button className={styles.btnPrimary} onClick={reload}>Reload</button>
          <button className={styles.btnPrimary} onClick={save}>Save</button>
        </div>
      </div>

      <div className={styles.sections}>
        {SETTINGS_SECTIONS.map(section => (
          <section key={section.title} className={styles.section}>
            <div className={styles.sectionHeader}>
              <div>
                <div className={styles.sectionTitle}>{section.title}</div>
                <div className={styles.sectionSubtitle}>{section.subtitle}</div>
              </div>
            </div>
            <div className={styles.grid}>
              {section.fields.map(renderField)}
            </div>
          </section>
        ))}

        <section className={styles.section}>
          <div className={styles.sectionHeader}>
            <div>
              <div className={styles.sectionTitle}>Slot Tuning</div>
              <div className={styles.sectionSubtitle}>
                Optional per-slot overrides for the connected ACE. Leave custom off to use the global defaults.
              </div>
            </div>
          </div>
          <div className={styles.slotGrid}>
            {draft.slot_tuning.map((slot, slotIndex) => (
              <div key={slotIndex} className={styles.slotCard}>
                <div className={styles.slotHeader}>
                  <div>
                    <div className={styles.slotTitle}>Slot {slotIndex}</div>
                    <div className={styles.slotSubtitle}>{slot.custom ? 'Custom movement values' : 'Using global defaults'}</div>
                  </div>
                  <label className={styles.toggleLine}>
                    <input
                      type="checkbox"
                      checked={slot.custom}
                      onChange={e => updateSlot(slotIndex, 'custom', e.target.checked)}
                    />
                    <span>Custom</span>
                  </label>
                </div>

                <div className={styles.slotFields}>
                  {SLOT_FIELDS.map(field => (
                    <label key={field.key} className={styles.slotField}>
                      <div className={styles.slotFieldTop}>
                        <span>{field.label}</span>
                        <span>{field.unit}</span>
                      </div>
                      <input
                        className={styles.input}
                        type="number"
                        min={field.min}
                        max={field.max}
                        step={field.step}
                        disabled={!slot.custom}
                        value={slot[field.key] ?? ''}
                        placeholder={String(draft[field.key] ?? '')}
                        onChange={e => updateSlot(slotIndex, field.key, numberOrNull(e.target.value))}
                      />
                    </label>
                  ))}
                </div>
              </div>
            ))}
          </div>
          <div className={styles.sectionNote}>
            Per-slot values override the global movement defaults. Leave Custom off to use the global settings.
          </div>
        </section>
      </div>

      <div className={styles.noteRow}>
        {saveNotice && <div className={styles.notice}>{saveNotice}</div>}
      </div>
    </div>
  )
}
