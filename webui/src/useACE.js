import { useState, useEffect, useCallback, useRef } from 'react'

export function useACE() {
  const [devices, setDevices] = useState({})
  const [connected, setConnected] = useState(false)
  const [logs, setLogs] = useState([])
  const [config, setConfig] = useState(null)
  const wsRef = useRef(null)
  const reconnectTimer = useRef(null)
  const shouldReconnect = useRef(true)

  const addLog = useCallback((level, msg) => {
    setLogs(prev => [{
      id: Date.now() + Math.random(),
      time: new Date().toLocaleTimeString(),
      level,
      msg,
    }, ...prev].slice(0, 200))
  }, [])

  const handleEvent = useCallback((msg) => {
    switch (msg.event) {
      case 'initial_state':
        if (msg.data) setDevices(msg.data)
        break
      case 'status_update':
      case 'device_connected':
      case 'device_disconnected':
        setDevices(prev => ({
          ...prev,
          [msg.device_index]: msg.data,
        }))
        if (msg.event === 'device_connected') {
          addLog('info', 'ACE connected')
        } else if (msg.event === 'device_disconnected') {
          addLog('warn', 'ACE disconnected')
        }
        break
      case 'command_result':
        addLog('info', `Command result: ${JSON.stringify(msg.data)}`)
        break
      case 'error':
        addLog('error', msg.data || 'Unknown error')
        break
    }
  }, [addLog])

  const connect = useCallback(() => {
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${proto}://${window.location.host}/ws`)
    wsRef.current = ws

    ws.onopen = () => {
      setConnected(true)
      addLog('info', 'Connected to ACE controller')
    }

    ws.onmessage = (e) => {
      try {
        handleEvent(JSON.parse(e.data))
      } catch {}
    }

    ws.onclose = () => {
      setConnected(false)
      if (shouldReconnect.current) {
        addLog('warn', 'Disconnected - reconnecting in 3s...')
        reconnectTimer.current = setTimeout(connect, 3000)
      }
    }

    ws.onerror = () => {
      addLog('error', 'WebSocket error')
    }
  }, [addLog, handleEvent])

  useEffect(() => {
    shouldReconnect.current = true
    connect()
    return () => {
      shouldReconnect.current = false
      clearTimeout(reconnectTimer.current)
      wsRef.current?.close()
    }
  }, [connect])

  const post = useCallback(async (path, body = {}) => {
    const r = await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    const data = await r.json()
    if (!r.ok) throw new Error(data.detail || 'Request failed')
    return data
  }, [])

  const get = useCallback(async (path) => {
    const r = await fetch(path)
    const data = await r.json()
    if (!r.ok) throw new Error(data.detail || 'Request failed')
    return data
  }, [])

  const put = useCallback(async (path, body = {}) => {
    const r = await fetch(path, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    const data = await r.json()
    if (!r.ok) throw new Error(data.detail || 'Request failed')
    return data
  }, [])

  const refreshConfig = useCallback(async () => {
    const data = await get('/config')
    setConfig(data)
    return data
  }, [get])

  const saveConfig = useCallback(async (patch) => {
    const data = await put('/config', patch)
    if (data?.config) {
      setConfig(data.config)
    }
    return data
  }, [put])

  useEffect(() => {
    refreshConfig().catch(err => {
      addLog('error', `Failed to load settings: ${err.message}`)
    })
  }, [refreshConfig, addLog])

  const api = {
    loadSlot:   (di, slot)          => post(`/devices/${di}/load_slot`, { slot }),
    unloadSlot: (di, slot)          => post(`/devices/${di}/unload_slot`, { slot }),
    loadAll:    (di)                => post(`/devices/${di}/load_all`),
    unloadAll:  (di)                => post(`/devices/${di}/unload_all`),
    feed:       (di, slot)          => post(`/devices/${di}/feed`, { slot }),
    retract:    (di, slot)          => post(`/devices/${di}/retract`, { slot }),
    dryerStart: (di, temp, dur)     => post(`/devices/${di}/dryer/start`, { temp_c: temp, duration_min: dur }),
    dryerStop:  (di)                => post(`/devices/${di}/dryer/stop`),
    getRfid:    (di, slot)          => get(`/devices/${di}/rfid/${slot}`),
    getConfig:  refreshConfig,
    saveConfig,
    listSerialPorts: ()             => get('/serial/ports'),
    probeHardware: ()               => post('/hardware/probe'),
  }

  return { devices, connected, logs, config, api, addLog }
}
