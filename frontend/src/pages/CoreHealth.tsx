import { useState, useEffect } from 'react'
import { Activity, RefreshCw, Clock, CheckCircle2, XCircle, AlertCircle, Settings } from 'lucide-react'
import api from '../api/client'

interface CoreHealth {
  core: string
  panel_status: string
  panel_healthy: boolean
  nodes_status: Record<string, {
    healthy: boolean
    status: string
    active_tunnels: number
  }>
}

interface ResetConfig {
  core: string
  enabled: boolean
  interval_minutes: number
  last_reset: string | null
  next_reset: string | null
}

const CoreHealth = () => {
  const [health, setHealth] = useState<CoreHealth[]>([])
  const [configs, setConfigs] = useState<ResetConfig[]>([])
  const [loading, setLoading] = useState(true)
  const [updating, setUpdating] = useState<string | null>(null)

  const fetchData = async () => {
    try {
      const [healthRes, configsRes] = await Promise.all([
        api.get('/core-health/health'),
        api.get('/core-health/reset-config')
      ])
      setHealth(healthRes.data)
      setConfigs(configsRes.data)
    } catch (error) {
      console.error('Failed to fetch core health:', error)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 10000)
    return () => clearInterval(interval)
  }, [])

  const handleReset = async (core: string) => {
    if (!confirm(`Are you sure you want to reset ${core} core?`)) return
    
    setUpdating(core)
    try {
      await api.post(`/core-health/reset/${core}`)
      await fetchData()
    } catch (error) {
      console.error(`Failed to reset ${core}:`, error)
      alert(`Failed to reset ${core}`)
    } finally {
      setUpdating(null)
    }
  }

  const handleConfigUpdate = async (core: string, updates: Partial<ResetConfig>) => {
    setUpdating(core)
    try {
      await api.put(`/core-health/reset-config/${core}`, updates)
      await fetchData()
    } catch (error) {
      console.error(`Failed to update config for ${core}:`, error)
      alert(`Failed to update config`)
    } finally {
      setUpdating(null)
    }
  }

  const getStatusIcon = (healthy: boolean, status: string) => {
    if (healthy) {
      return <CheckCircle2 className="w-5 h-5 text-green-500" />
    } else if (status === "error") {
      return <XCircle className="w-5 h-5 text-red-500" />
    } else {
      return <AlertCircle className="w-5 h-5 text-yellow-500" />
    }
  }

  const getStatusText = (healthy: boolean, status: string) => {
    if (healthy) {
      return "Healthy"
    } else if (status === "error") {
      return "Error"
    } else if (status === "no_active_servers") {
      return "No Active Servers"
    } else if (status === "disconnected") {
      return "Disconnected"
    } else {
      return "Unknown"
    }
  }

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return "Never"
    return new Date(dateStr).toLocaleString()
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="text-center">
          <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 dark:border-blue-400 mb-4"></div>
          <p className="text-gray-500 dark:text-gray-400">Loading core health...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="w-full max-w-7xl mx-auto">
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-gray-900 dark:text-white mb-2">Core Health</h1>
        <p className="text-gray-600 dark:text-gray-400">Monitor and manage reverse tunnel cores</p>
      </div>

      <div className="space-y-6">
        {health.map((coreHealth) => {
          const config = configs.find(c => c.core === coreHealth.core)
          const nodeCount = Object.keys(coreHealth.nodes_status).length
          const healthyNodes = Object.values(coreHealth.nodes_status).filter(n => n.healthy).length

          return (
            <div
              key={coreHealth.core}
              className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-6"
            >
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-3">
                  <div className="p-2 bg-blue-100 dark:bg-blue-900/30 rounded-lg">
                    <Activity className="w-6 h-6 text-blue-600 dark:text-blue-400" />
                  </div>
                  <div>
                    <h2 className="text-xl font-semibold text-gray-900 dark:text-white capitalize">
                      {coreHealth.core}
                    </h2>
                    <p className="text-sm text-gray-500 dark:text-gray-400">
                      {nodeCount} node(s)
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {getStatusIcon(coreHealth.panel_healthy, coreHealth.panel_status)}
                  <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                    {getStatusText(coreHealth.panel_healthy, coreHealth.panel_status)}
                  </span>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
                <div>
                  <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
                    Panel Status
                  </h3>
                  <div className="flex items-center gap-2">
                    {getStatusIcon(coreHealth.panel_healthy, coreHealth.panel_status)}
                    <span className="text-sm text-gray-600 dark:text-gray-400">
                      {getStatusText(coreHealth.panel_healthy, coreHealth.panel_status)}
                    </span>
                  </div>
                </div>

                <div>
                  <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
                    Nodes Status
                  </h3>
                  <div className="space-y-2">
                    {Object.entries(coreHealth.nodes_status).map(([nodeId, nodeStatus]) => (
                      <div key={nodeId} className="flex items-center justify-between text-sm">
                        <span className="text-gray-600 dark:text-gray-400 truncate max-w-[200px]">
                          {nodeId.substring(0, 8)}...
                        </span>
                        <div className="flex items-center gap-2">
                          {getStatusIcon(nodeStatus.healthy, nodeStatus.status)}
                          <span className="text-gray-600 dark:text-gray-400">
                            {getStatusText(nodeStatus.healthy, nodeStatus.status)}
                          </span>
                        </div>
                      </div>
                    ))}
                    {nodeCount === 0 && (
                      <span className="text-sm text-gray-500 dark:text-gray-400">No active nodes</span>
                    )}
                  </div>
                </div>
              </div>

              <div className="border-t border-gray-200 dark:border-gray-700 pt-4">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-2">
                    <Clock className="w-5 h-5 text-gray-500 dark:text-gray-400" />
                    <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300">
                      Auto Reset Timer
                    </h3>
                  </div>
                  <label className="relative inline-flex items-center cursor-pointer">
                    <input
                      type="checkbox"
                      checked={config?.enabled || false}
                      onChange={(e) => handleConfigUpdate(coreHealth.core, { enabled: e.target.checked })}
                      disabled={updating === coreHealth.core}
                      className="sr-only peer"
                    />
                    <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-blue-300 dark:peer-focus:ring-blue-800 rounded-full peer dark:bg-gray-700 peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all dark:border-gray-600 peer-checked:bg-blue-600"></div>
                  </label>
                </div>

                {config?.enabled && (
                  <div className="space-y-3">
                    <div className="flex items-center gap-3">
                      <label className="text-sm text-gray-600 dark:text-gray-400">
                        Interval (minutes):
                      </label>
                      <input
                        type="number"
                        min="1"
                        value={config.interval_minutes}
                        onChange={(e) => {
                          const minutes = parseInt(e.target.value)
                          if (minutes >= 1) {
                            handleConfigUpdate(coreHealth.core, { interval_minutes: minutes })
                          }
                        }}
                        disabled={updating === coreHealth.core}
                        className="w-20 px-2 py-1 text-sm border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                      />
                    </div>
                    <div className="text-xs text-gray-500 dark:text-gray-400">
                      <div>Last reset: {formatDate(config.last_reset)}</div>
                    </div>
                  </div>
                )}

                <div className="flex items-center justify-between mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
                  <button
                    onClick={() => handleReset(coreHealth.core)}
                    disabled={updating === coreHealth.core}
                    className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {updating === coreHealth.core ? (
                      <>
                        <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                        <span>Resetting...</span>
                      </>
                    ) : (
                      <>
                        <RefreshCw className="w-4 h-4" />
                        <span>Reset Now</span>
                      </>
                    )}
                  </button>
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default CoreHealth

