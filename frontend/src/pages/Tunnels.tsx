import { useEffect, useState } from 'react'
import { Plus, Trash2, Edit2 } from 'lucide-react'
import api from '../api/client'
import { parseAddressPort, formatAddressPort } from '../utils/addressUtils'

interface Tunnel {
  id: string
  name: string
  core: string
  type: string
  node_id: string
  spec: Record<string, any>
  status: string
  error_message?: string | null
  revision: number
  created_at: string
  updated_at: string
}

type BackhaulTransport = 'tcp' | 'udp' | 'ws' | 'wsmux' | 'tcpmux'

interface BackhaulFormState {
  transport: BackhaulTransport
  control_port: string
  public_port: string
  listen_ip: string
  public_host: string
  remote_addr: string
  target_host: string
  target_port: string
  token: string
  accept_udp: boolean
}

interface BackhaulAdvancedServerState {
  keepalive_period: string
  heartbeat: string
  channel_size: string
  mux_con: string
  log_level: string
  nodelay: boolean
  skip_optz: boolean
  tls_cert: string
  tls_key: string
  sniffer: boolean
  web_port: string
  proxy_protocol: boolean
}

interface BackhaulAdvancedClientState {
  connection_pool: string
  retry_interval: string
  dial_timeout: string
  keepalive_period: string
  log_level: string
  nodelay: boolean
  aggressive_pool: boolean
  edge_ip: string
  skip_optz: boolean
}

interface BackhaulAdvancedState {
  server: BackhaulAdvancedServerState
  client: BackhaulAdvancedClientState
  customPorts: string
}

const createDefaultBackhaulState = (): BackhaulFormState => ({
  transport: 'tcp',
  control_port: '3080',
  public_port: '443',
  listen_ip: '0.0.0.0',
  public_host: '',
  remote_addr: '',
  target_host: '127.0.0.1',
  target_port: '8080',
  token: '',
  accept_udp: false,
})

const createDefaultBackhaulAdvancedState = (): BackhaulAdvancedState => ({
  server: {
    keepalive_period: '75',
    heartbeat: '40',
    channel_size: '2048',
    mux_con: '8',
    log_level: 'info',
    nodelay: true,
    skip_optz: false,
    tls_cert: '',
    tls_key: '',
    sniffer: false,
    web_port: '',
    proxy_protocol: false,
  },
  client: {
    connection_pool: '4',
    retry_interval: '3',
    dial_timeout: '10',
    keepalive_period: '75',
    log_level: 'info',
    nodelay: true,
    aggressive_pool: false,
    edge_ip: '',
    skip_optz: false,
  },
  customPorts: '',
})

const numericServerKeys = new Set([
  'keepalive_period',
  'heartbeat',
  'channel_size',
  'mux_con',
  'web_port',
])
const booleanServerKeys = new Set(['nodelay', 'skip_optz', 'sniffer', 'proxy_protocol'])
const stringServerKeys = new Set(['log_level', 'tls_cert', 'tls_key', 'sniffer_log'])

const numericClientKeys = new Set(['connection_pool', 'retry_interval', 'dial_timeout', 'keepalive_period'])
const booleanClientKeys = new Set(['nodelay', 'aggressive_pool', 'skip_optz'])
const stringClientKeys = new Set(['log_level', 'edge_ip'])

interface BackhaulDisplayInfo {
  controlPort: string
  publicPort: string
  target: string
}

const getBackhaulDisplayInfo = (spec: Record<string, any> | undefined): BackhaulDisplayInfo => {
  if (!spec) {
    return { controlPort: 'N/A', publicPort: 'N/A', target: 'N/A' }
  }

  const controlPort =
    spec.control_port ||
    (typeof spec.bind_addr === 'string' && spec.bind_addr.includes(':') ? spec.bind_addr.split(':').pop() : undefined) ||
    (typeof spec.remote_addr === 'string' && spec.remote_addr.includes(':') ? spec.remote_addr.split(':').pop() : undefined) ||
    'N/A'

  const publicPort =
    spec.public_port ||
    spec.listen_port ||
    (Array.isArray(spec.ports) && spec.ports.length > 0
      ? (() => {
          const [first] = spec.ports
          if (typeof first !== 'string') return undefined
          const [left] = first.split('=')
          const parts = left.split(':')
          return parts.pop()
        })()
      : undefined) ||
    'N/A'

  const target =
    spec.target_addr ||
    (Array.isArray(spec.ports) && spec.ports.length > 0
      ? (() => {
          const [first] = spec.ports
          if (typeof first !== 'string') return undefined
          const segments = first.split('=')
          return segments.length > 1 ? segments[1] : undefined
        })()
      : undefined) ||
    'N/A'

  return {
    controlPort: controlPort?.toString() || 'N/A',
    publicPort: publicPort?.toString() || 'N/A',
    target: target?.toString() || 'N/A',
  }
}

const Tunnels = () => {
  const [tunnels, setTunnels] = useState<Tunnel[]>([])
  const [nodes, setNodes] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [showAddModal, setShowAddModal] = useState(false)
  const [editingTunnel, setEditingTunnel] = useState<Tunnel | null>(null)

  useEffect(() => {
    fetchData()
    const params = new URLSearchParams(window.location.search)
    if (params.get('create') === 'true') {
      setShowAddModal(true)
      window.history.replaceState({}, '', '/tunnels')
    }
    
  }, [])

  const fetchData = async () => {
    try {
      const [tunnelsRes, nodesRes] = await Promise.all([
        api.get('/tunnels'),
        api.get('/nodes'),
      ])
      setTunnels(tunnelsRes.data)
      setNodes(nodesRes.data)
    } catch (error) {
      console.error('Failed to fetch data:', error)
    } finally {
      setLoading(false)
    }
  }

  const deleteTunnel = async (id: string) => {
    if (!confirm('Are you sure you want to delete this tunnel?')) return
    
    try {
      await api.delete(`/tunnels/${id}`)
      fetchData()
    } catch (error) {
      console.error('Failed to delete tunnel:', error)
      alert('Failed to delete tunnel')
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="text-center">
          <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 dark:border-blue-400 mb-4"></div>
          <p className="text-gray-500 dark:text-gray-400">Loading tunnels...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="w-full max-w-7xl mx-auto">
      <div className="flex justify-between items-center mb-8">
        <div>
          <h1 className="text-3xl font-bold text-gray-900 dark:text-white mb-2">Tunnels</h1>
          <p className="text-gray-500 dark:text-gray-400">Manage your tunnel connections</p>
        </div>
        <button
          onClick={() => setShowAddModal(true)}
          className="px-5 py-2.5 bg-gradient-to-r from-blue-600 to-indigo-600 text-white rounded-lg hover:from-blue-700 hover:to-indigo-700 transition-all duration-200 font-medium shadow-sm hover:shadow-md flex items-center gap-2"
        >
          <Plus size={20} />
          Create Tunnel
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 sm:gap-6">
        {tunnels.map((tunnel) => (
          <div
            key={tunnel.id}
            className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-5 sm:p-6 transition-all hover:shadow-md"
          >
            {/* Header */}
            <div className="flex justify-between items-start mb-4">
              <div className="flex-1">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-1">{tunnel.name}</h3>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  {tunnel.core === 'xray' ? 'gost' : tunnel.core} / {tunnel.type}
                </p>
                {tunnel.node_id && (
                  <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
                    Node: {nodes.find(n => n.id === tunnel.node_id)?.name || tunnel.node_id}
                  </p>
                )}
              </div>
              <div className="flex gap-2 ml-2">
                <button
                  onClick={() => setEditingTunnel(tunnel)}
                  className="p-2 text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded-lg transition-colors"
                  title="Edit tunnel"
                >
                  <Edit2 size={18} />
                </button>
                <button
                  onClick={() => deleteTunnel(tunnel.id)}
                  className="p-2 text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-colors"
                  title="Delete tunnel"
                >
                  <Trash2 size={18} />
                </button>
              </div>
            </div>

            {/* Error Message */}
            {tunnel.status === 'error' && tunnel.error_message && (
              <div className="mb-4 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
                <p className="text-xs font-medium text-red-800 dark:text-red-200 mb-1">Error</p>
                <p className="text-sm text-red-700 dark:text-red-300">{tunnel.error_message}</p>
              </div>
            )}

            {/* Status Badge */}
            <div className="mb-4">
              <span
                className={`inline-block px-3 py-1 rounded-full text-xs font-medium ${
                  tunnel.status === 'active'
                    ? 'bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-200'
                    : tunnel.status === 'error'
                    ? 'bg-red-100 dark:bg-red-900/30 text-red-800 dark:text-red-200'
                    : 'bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-200'
                }`}
              >
                {tunnel.status}
              </span>
            </div>
            
            {/* Port Details */}
            <div className="space-y-3 mb-4">
              <div className="flex justify-between items-center py-2 border-b border-gray-100 dark:border-gray-700">
                <span className="text-sm text-gray-500 dark:text-gray-400">Listen Port</span>
                <span className="text-sm font-medium text-gray-900 dark:text-white">
                  {tunnel.spec?.listen_port || tunnel.spec?.remote_port || 'N/A'}
                </span>
              </div>
              {tunnel.core === 'rathole' && (
                <>
                  <div className="flex justify-between items-center py-2 border-b border-gray-100 dark:border-gray-700">
                    <span className="text-sm text-gray-500 dark:text-gray-400">Rathole Port</span>
                    <span className="text-sm font-medium text-gray-900 dark:text-white">
                      {tunnel.spec?.remote_addr ? tunnel.spec.remote_addr.split(':')[1] : 'N/A'}
                    </span>
                  </div>
                  <div className="flex justify-between items-center py-2 border-b border-gray-100 dark:border-gray-700">
                    <span className="text-sm text-gray-500 dark:text-gray-400">Local Port</span>
                    <span className="text-sm font-medium text-gray-900 dark:text-white">
                      {tunnel.spec?.local_addr ? (() => {
                        const parsed = parseAddressPort(tunnel.spec.local_addr)
                        return parsed.port?.toString() || 'N/A'
                      })() : 'N/A'}
                    </span>
                  </div>
                </>
              )}
              {tunnel.core === 'chisel' && (
                <>
                  <div className="flex justify-between items-center py-2 border-b border-gray-100 dark:border-gray-700">
                    <span className="text-sm text-gray-500 dark:text-gray-400">Control Port</span>
                    <span className="text-sm font-medium text-gray-900 dark:text-white">
                      {tunnel.spec?.control_port || (tunnel.spec?.listen_port ? (parseInt(tunnel.spec.listen_port.toString()) + 10000).toString() : 'N/A')}
                    </span>
                  </div>
                  <div className="flex justify-between items-center py-2 border-b border-gray-100 dark:border-gray-700">
                    <span className="text-sm text-gray-500 dark:text-gray-400">Local Port</span>
                    <span className="text-sm font-medium text-gray-900 dark:text-white">
                      {tunnel.spec?.local_addr ? (() => {
                        const parsed = parseAddressPort(tunnel.spec.local_addr)
                        return parsed.port?.toString() || 'N/A'
                      })() : 'N/A'}
                    </span>
                  </div>
                </>
              )}
              {tunnel.core === 'xray' && (tunnel.spec?.forward_to || (tunnel.spec?.remote_ip && tunnel.spec?.remote_port)) && (
                <div className="flex justify-between items-center py-2 border-b border-gray-100 dark:border-gray-700">
                  <span className="text-sm text-gray-500 dark:text-gray-400">Forward To</span>
                  <span className="text-sm font-medium text-gray-900 dark:text-white break-all ml-2">
                    {tunnel.spec.forward_to || formatAddressPort(tunnel.spec.remote_ip, tunnel.spec.remote_port)}
                  </span>
                </div>
              )}
              {tunnel.core === 'backhaul' && (
                <>
                  {(() => {
                    const info = getBackhaulDisplayInfo(tunnel.spec)
                    return (
                      <>
                        <div className="flex justify-between items-center py-2 border-b border-gray-100 dark:border-gray-700">
                          <span className="text-sm text-gray-500 dark:text-gray-400">Control Port</span>
                          <span className="text-sm font-medium text-gray-900 dark:text-white">{info.controlPort}</span>
                        </div>
                        <div className="flex justify-between items-center py-2 border-b border-gray-100 dark:border-gray-700">
                          <span className="text-sm text-gray-500 dark:text-gray-400">Public Port</span>
                          <span className="text-sm font-medium text-gray-900 dark:text-white">{info.publicPort}</span>
                        </div>
                        <div className="flex justify-between items-center py-2 border-b border-gray-100 dark:border-gray-700">
                          <span className="text-sm text-gray-500 dark:text-gray-400">Target</span>
                          <span className="text-sm font-medium text-gray-900 dark:text-white break-all ml-2">{info.target}</span>
                        </div>
                      </>
                    )
                  })()}
                </>
              )}
            </div>

          </div>
        ))}
      </div>

      {showAddModal && (
        <AddTunnelModal
          nodes={nodes}
          onClose={() => setShowAddModal(false)}
          onSuccess={() => {
            setShowAddModal(false)
            fetchData()
          }}
        />
      )}

      {editingTunnel && (
        <EditTunnelModal
          tunnel={editingTunnel}
          nodes={nodes}
          onClose={() => setEditingTunnel(null)}
          onSuccess={() => {
            setEditingTunnel(null)
            fetchData()
          }}
        />
      )}
    </div>
  )
}

interface EditTunnelModalProps {
  tunnel: Tunnel
  nodes: any[]
  onClose: () => void
  onSuccess: () => void
}

const EditTunnelModal = ({ tunnel, onClose, onSuccess }: EditTunnelModalProps) => {
  const forwardToParsed = tunnel.spec?.forward_to ? parseAddressPort(tunnel.spec.forward_to) : null
  const remoteIp = tunnel.spec?.remote_ip || forwardToParsed?.host || '127.0.0.1'
  const remotePort = tunnel.spec?.remote_port || forwardToParsed?.port || 8080
  
  const [formData, setFormData] = useState({
    name: tunnel.name,
    port: tunnel.spec?.listen_port || tunnel.spec?.remote_port || 8080,
    remote_ip: remoteIp,
    rathole_remote_addr: tunnel.spec?.remote_addr ? (() => {
      const parsed = parseAddressPort(tunnel.spec.remote_addr)
      return parsed.port?.toString() || ''
    })() : '',
    rathole_local_port: tunnel.spec?.local_addr ? (() => {
      const parsed = parseAddressPort(tunnel.spec.local_addr)
      return parsed.port?.toString() || ''
    })() : '',
    chisel_control_port: tunnel.spec?.control_port ? tunnel.spec.control_port.toString() : '',
    frp_bind_port: tunnel.spec?.bind_port ? tunnel.spec.bind_port.toString() : '7000',
    frp_token: tunnel.spec?.token || '',
    frp_local_ip: tunnel.spec?.local_ip || '127.0.0.1',
    frp_local_port: tunnel.spec?.local_port ? tunnel.spec.local_port.toString() : '8080',
    node_ipv6: tunnel.spec?.node_ipv6 || '',
  })
  const parsedBackhaul = parseBackhaulSpec(tunnel.spec, tunnel.type)
  const [backhaulState, setBackhaulState] = useState<BackhaulFormState>(parsedBackhaul.state)
  const [backhaulAdvanced, setBackhaulAdvanced] = useState<BackhaulAdvancedState>(parsedBackhaul.advanced)
  const [showBackhaulAdvanced, setShowBackhaulAdvanced] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      let updatedSpec = { ...tunnel.spec }
      
      const useV4ToV6 = updatedSpec.use_ipv6 || false
      
      if (tunnel.core === 'rathole') {
        if (formData.rathole_remote_addr) {
          const remoteHost = window.location.hostname
          const remotePort = formData.rathole_remote_addr.includes(':') 
            ? formData.rathole_remote_addr.split(':')[1] 
            : formData.rathole_remote_addr
          updatedSpec.remote_addr = `${remoteHost}:${remotePort || '23333'}`
        }
        if (formData.rathole_local_port) {
          const localHost = useV4ToV6 
            ? (formData.node_ipv6 || '::1')
            : '127.0.0.1'
          const localPort = parseInt(formData.rathole_local_port) || 8080
          updatedSpec.local_addr = formatAddressPort(localHost, localPort)
        }
        if (formData.node_ipv6) {
          updatedSpec.node_ipv6 = formData.node_ipv6
        }
        const port = parseInt(formData.port.toString()) || parseInt(formData.rathole_local_port) || 8090
        updatedSpec.remote_port = port
        updatedSpec.listen_port = port
      } else if (tunnel.core === 'xray' && (tunnel.type === 'tcp' || tunnel.type === 'udp' || tunnel.type === 'grpc' || tunnel.type === 'tcpmux')) {
        const remoteIp = formData.remote_ip || '127.0.0.1'
        const port = parseInt(formData.port.toString()) || 8080
        updatedSpec.remote_ip = remoteIp
        updatedSpec.remote_port = port
        updatedSpec.listen_port = port
        updatedSpec.forward_to = formatAddressPort(remoteIp, port)
      } else if (tunnel.core === 'chisel') {
        const listenPort = parseInt(formData.port.toString()) || 8080
        updatedSpec.listen_port = listenPort
        updatedSpec.remote_port = listenPort
        const controlPort = formData.chisel_control_port 
          ? parseInt(formData.chisel_control_port.toString())
          : listenPort + 10000
        updatedSpec.control_port = controlPort
        if (formData.rathole_local_port) {
          const localHost = updatedSpec.use_ipv6 
            ? (formData.node_ipv6 || '::1')
            : '127.0.0.1'
          const localPort = parseInt(formData.rathole_local_port) || 8080
          updatedSpec.local_addr = formatAddressPort(localHost, localPort)
        }
        if (formData.node_ipv6) {
          updatedSpec.node_ipv6 = formData.node_ipv6
        }
      } else if (tunnel.core === 'frp') {
        const bindPort = parseInt(formData.frp_bind_port) || 7000
        const localPort = parseInt(formData.frp_local_port) || 8080
        const remotePort = parseInt(formData.port.toString()) || localPort
        updatedSpec.bind_port = bindPort
        updatedSpec.listen_port = remotePort
        updatedSpec.remote_port = remotePort
        if (formData.frp_token) {
          updatedSpec.token = formData.frp_token
        } else {
          delete updatedSpec.token
        }
        updatedSpec.local_ip = formData.frp_local_ip || '127.0.0.1'
        updatedSpec.local_port = localPort
        updatedSpec.type = tunnel.type === 'udp' ? 'udp' : 'tcp'
      } else if (tunnel.core === 'backhaul') {
        updatedSpec = buildBackhaulSpec(backhaulState, backhaulAdvanced, tunnel.type as BackhaulTransport)
      }

      await api.put(`/tunnels/${tunnel.id}`, {
        name: formData.name,
        spec: updatedSpec,
      })
      onSuccess()
    } catch (error) {
      console.error('Failed to update tunnel:', error)
      alert('Failed to update tunnel')
    }
  }

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white dark:bg-gray-800 rounded-lg p-6 w-full max-w-md">
        <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-4">Edit Tunnel</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Name
            </label>
            <input
              type="text"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg"
              required
            />
          </div>
          {tunnel.core === 'xray' && (tunnel.type === 'tcp' || tunnel.type === 'udp' || tunnel.type === 'grpc' || tunnel.type === 'tcpmux') && (
            <>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Remote IP
                </label>
                <input
                  type="text"
                  value={formData.remote_ip}
                  onChange={(e) =>
                    setFormData({ ...formData, remote_ip: e.target.value || '127.0.0.1' })
                  }
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white"
                  placeholder="127.0.0.1 or [2001:db8::1]"
                />
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                  Target server IP address (IPv4 or IPv6)
                </p>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Port
                </label>
                <input
                  type="number"
                  value={formData.port}
                  onChange={(e) =>
                    setFormData({ ...formData, port: parseInt(e.target.value) || 8080 })
                  }
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white"
                  placeholder="8080"
                  min="1"
                  max="65535"
                />
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                  Port (same for panel and target server)
                </p>
              </div>
            </>
          )}
          
          {tunnel.core === 'backhaul' && (
            <BackhaulForm
              state={backhaulState}
              onChange={(partial) => {
                setBackhaulState((prev) => ({ ...prev, ...partial }))
              }}
              onOpenAdvanced={() => setShowBackhaulAdvanced(true)}
              acceptUdpVisible={
                backhaulState.transport === 'tcp' || backhaulState.transport === 'tcpmux'
              }
            />
          )}
          
          {tunnel.core === 'rathole' && (
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Local Port
              </label>
              <input
                type="number"
                value={formData.port}
                onChange={(e) =>
                  setFormData({ ...formData, port: parseInt(e.target.value) || 8080 })
                }
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white"
                min="1"
                max="65535"
              />
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                Port on panel where clients will connect
              </p>
            </div>
          )}
          
          {tunnel.core === 'rathole' && (
            <>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Rathole Port
                </label>
                <input
                  type="number"
                  value={formData.rathole_remote_addr ? formData.rathole_remote_addr.split(':')[1] || formData.rathole_remote_addr : ''}
                  onChange={(e) => {
                    const port = e.target.value
                    const host = window.location.hostname
                    setFormData({ ...formData, rathole_remote_addr: port ? `${host}:${port}` : '' })
                  }}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white"
                  placeholder="23333"
                  min="1"
                  max="65535"
                />
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">Rathole server port on panel (IP: {window.location.hostname})</p>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Local Port
                </label>
                <input
                  type="number"
                  value={formData.rathole_local_port}
                  onChange={(e) =>
                    setFormData({ ...formData, rathole_local_port: e.target.value })
                  }
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white"
                  placeholder="8080"
                  min="1"
                  max="65535"
                />
              </div>
            </>
          )}
          
          {tunnel.core === 'chisel' && (
            <>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Reverse Port
                  </label>
                  <input
                    type="number"
                    value={formData.port}
                    onChange={(e) =>
                      setFormData({ ...formData, port: parseInt(e.target.value) || 8080 })
                    }
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white"
                    min="1"
                    max="65535"
                    required
                  />
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                    Port where clients connect to access tunneled service
                  </p>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Control Port
                  </label>
                  <input
                    type="number"
                    value={formData.chisel_control_port}
                    onChange={(e) =>
                      setFormData({ ...formData, chisel_control_port: e.target.value })
                    }
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white"
                    placeholder={`${(parseInt(formData.port.toString()) || 8080) + 10000} (auto)`}
                    min="1"
                    max="65535"
                  />
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                    Chisel server control port (leave empty for auto: reverse port + 10000)
                  </p>
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Local Port
                </label>
                <input
                  type="number"
                  value={formData.rathole_local_port}
                  onChange={(e) =>
                    setFormData({ ...formData, rathole_local_port: e.target.value })
                  }
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white"
                  placeholder="8080"
                  min="1"
                  max="65535"
                  required
                />
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                  {tunnel.spec?.use_ipv6 
                    ? `Port on node where local service listens (IPv6: [${tunnel.spec?.node_ipv6 || '::1'}]:${formData.rathole_local_port || '8080'})`
                    : `Port on node where local service listens`}
                </p>
              </div>
              {/* Node IPv6 address field for Chisel when v4 to v6 is enabled */}
              {tunnel.spec?.use_ipv6 && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Node IPv6 Address (Optional)
                  </label>
                  <input
                    type="text"
                    value={formData.node_ipv6}
                    onChange={(e) =>
                      setFormData({ ...formData, node_ipv6: e.target.value })
                    }
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white"
                    placeholder="::1 or 2001:db8::1"
                  />
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                    IPv6 address of the node. Leave empty to use ::1 (localhost IPv6)
                  </p>
                </div>
              )}
            </>
          )}
          
          {tunnel.core === 'frp' && (
            <>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Bind Port
                  </label>
                  <input
                    type="number"
                    value={formData.frp_bind_port}
                    onChange={(e) =>
                      setFormData({ ...formData, frp_bind_port: e.target.value })
                    }
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white"
                    placeholder="7000"
                    min="1"
                    max="65535"
                    required
                  />
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                    FRP server port on panel (default: 7000)
                  </p>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Remote Port
                  </label>
                  <input
                    type="number"
                    value={formData.port}
                    onChange={(e) =>
                      setFormData({ ...formData, port: parseInt(e.target.value) || 8080 })
                    }
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white"
                    placeholder="8080"
                    min="1"
                    max="65535"
                    required
                  />
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                    Port where clients connect to access tunneled service
                  </p>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Token (Optional)
                  </label>
                  <input
                    type="text"
                    value={formData.frp_token}
                    onChange={(e) =>
                      setFormData({ ...formData, frp_token: e.target.value })
                    }
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white"
                    placeholder="authentication-token"
                  />
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">Authentication token (optional)</p>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Local IP
                  </label>
                  <input
                    type="text"
                    value={formData.frp_local_ip}
                    onChange={(e) =>
                      setFormData({ ...formData, frp_local_ip: e.target.value })
                    }
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white"
                    placeholder="127.0.0.1"
                    required
                  />
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">Local service IP address</p>
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Local Port
                </label>
                <input
                  type="number"
                  value={formData.frp_local_port}
                  onChange={(e) =>
                    setFormData({ ...formData, frp_local_port: e.target.value })
                  }
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white"
                  placeholder="8080"
                  min="1"
                  max="65535"
                  required
                />
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">Local service port ({formData.frp_local_ip || '127.0.0.1'}:{formData.frp_local_port || '8080'})</p>
              </div>
            </>
          )}
          
          {/* Node IPv6 address field for Rathole when v4 to v6 is enabled */}
          {tunnel.core === 'rathole' && tunnel.spec?.use_ipv6 && (
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Node IPv6 Address (Optional)
              </label>
              <input
                type="text"
                value={formData.node_ipv6}
                onChange={(e) =>
                  setFormData({ ...formData, node_ipv6: e.target.value })
                }
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white"
                placeholder="::1 or 2001:db8::1"
              />
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                IPv6 address of the node. Leave empty to use ::1 (localhost IPv6)
              </p>
            </div>
          )}
          
          <div className="flex gap-3 justify-end">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-200 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
            >
              Save Changes
            </button>
          </div>
        </form>
        <BackhaulAdvancedDrawer
          open={showBackhaulAdvanced}
          state={backhaulAdvanced}
          onClose={() => setShowBackhaulAdvanced(false)}
          onChange={setBackhaulAdvanced}
        />
      </div>
    </div>
  )
}

interface AddTunnelModalProps {
  nodes: any[]
  onClose: () => void
  onSuccess: () => void
}

const AddTunnelModal = ({ nodes, onClose, onSuccess }: AddTunnelModalProps) => {
  const [formData, setFormData] = useState({
    name: '',
    core: 'xray',
    type: 'tcp',
    node_id: '',
    port: 8080,
    remote_ip: '127.0.0.1',
    rathole_remote_addr: '23333',
    rathole_token: '',
    rathole_local_port: '8080',
    chisel_control_port: '',  // Empty means auto (listen_port + 10000)
    frp_bind_port: '7000',
    frp_token: '',
    frp_local_ip: '127.0.0.1',
    frp_local_port: '8080',
    use_ipv6: false,
    node_ipv6: '',  // Optional IPv6 address for node (Rathole/Chisel)
    spec: {} as Record<string, any>,
  })
  const [backhaulState, setBackhaulState] = useState<BackhaulFormState>(createDefaultBackhaulState())
  const [backhaulAdvanced, setBackhaulAdvanced] = useState<BackhaulAdvancedState>(createDefaultBackhaulAdvancedState())
  const [showBackhaulAdvanced, setShowBackhaulAdvanced] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      let spec = getSpecForType(formData.core, formData.type)
      let tunnelType = formData.type
      
      spec.use_ipv6 = formData.use_ipv6 || false
      
      if (formData.core === 'xray' && (formData.type === 'tcp' || formData.type === 'udp' || formData.type === 'grpc' || formData.type === 'tcpmux')) {
        const remoteIp = formData.remote_ip || (formData.use_ipv6 ? '::1' : '127.0.0.1')
        const port = parseInt(formData.port.toString()) || 8080
        spec.remote_ip = remoteIp
        spec.remote_port = port
        spec.listen_port = port
        spec.forward_to = formatAddressPort(remoteIp, port)
      }
      
      if (formData.core === 'rathole') {
        const remoteHost = window.location.hostname
        const remotePort = formData.rathole_remote_addr || '23333'
        spec.remote_addr = `${remoteHost}:${remotePort}`
        spec.token = formData.rathole_token
        const localHost = formData.use_ipv6 
          ? (formData.node_ipv6 || '::1')
          : '127.0.0.1'
        const localPort = parseInt(formData.rathole_local_port) || 8080
        spec.local_addr = formatAddressPort(localHost, localPort)
        const port = parseInt(formData.port.toString()) || parseInt(formData.rathole_local_port) || 8090
        spec.remote_port = port
        spec.listen_port = port
      }
      
      if (formData.core === 'chisel') {
        const listenPort = parseInt(formData.port.toString()) || 8080
        spec.listen_port = listenPort
        spec.remote_port = listenPort
        spec.server_port = listenPort
        const controlPort = formData.chisel_control_port 
          ? parseInt(formData.chisel_control_port.toString())
          : listenPort + 10000
        spec.control_port = controlPort
        const localPort = parseInt(formData.rathole_local_port?.toString() || formData.port?.toString() || '8080')
        const localHost = formData.use_ipv6 
          ? (formData.node_ipv6 || '::1')
          : '127.0.0.1'
        spec.local_addr = formatAddressPort(localHost, localPort)
        const panelHost = typeof window !== 'undefined' ? window.location.hostname : 'localhost'
        spec.panel_host = panelHost
      }
      
      if (formData.core === 'backhaul') {
        if (!formData.node_id) {
          alert('Backhaul tunnels require a node')
          return
        }
        spec = buildBackhaulSpec(backhaulState, backhaulAdvanced)
        spec.use_ipv6 = formData.use_ipv6 || false
        tunnelType = backhaulState.transport
      }
      
      if (formData.core === 'frp') {
        if (!formData.node_id) {
          alert('FRP tunnels require a node')
          return
        }
        const bindPort = parseInt(formData.frp_bind_port) || 7000
        const localPort = parseInt(formData.frp_local_port) || 8080
        const remotePort = parseInt(formData.port.toString()) || localPort
        spec.bind_port = bindPort
        spec.listen_port = remotePort
        spec.remote_port = remotePort
        if (formData.frp_token) {
          spec.token = formData.frp_token
        }
        spec.local_ip = formData.frp_local_ip || '127.0.0.1'
        spec.local_port = localPort
        spec.type = formData.type === 'udp' ? 'udp' : 'tcp'
        tunnelType = formData.type === 'udp' ? 'udp' : 'tcp'
      }
      
      const payload = {
        name: formData.name,
        core: formData.core,
        type: tunnelType,
        node_id: formData.node_id || null,
        spec: spec,
      }
      await api.post('/tunnels', payload)
      onSuccess()
    } catch (error) {
      console.error('Failed to create tunnel:', error)
      alert('Failed to create tunnel')
    }
  }

  const getSpecForType = (core: string, type: string): Record<string, any> => {
    const baseSpec: Record<string, any> = {}

    if (core === 'rathole') {
      return { ...baseSpec, remote_addr: '', token: '', local_addr: '127.0.0.1:8080' }
    }

    switch (type) {
      case 'grpc':
        return { ...baseSpec, service_name: 'GrpcService', uuid: generateUUID() }
      case 'udp':
        return { ...baseSpec, uuid: generateUUID(), header_type: 'none' }
      default:
        return baseSpec
    }
  }

  const handleCoreChange = (core: string) => {
    let newType = formData.type
    if (core === 'rathole' || core === 'chisel' || core === 'frp') {
      newType = core === 'frp' ? 'tcp' : core
    } else if (core === 'backhaul') {
      newType = backhaulState.transport
    } else if (formData.type === 'rathole' || formData.type === 'chisel' || formData.core === 'backhaul' || formData.core === 'frp') {
      newType = 'tcp'
    }
    setFormData({ ...formData, core, type: newType })
  }

  const generateUUID = () => {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
      const r = (Math.random() * 16) | 0
      const v = c === 'x' ? r : (r & 0x3) | 0x8
      return v.toString(16)
    })
  }

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 overflow-auto">
      <div className="bg-white dark:bg-gray-800 rounded-lg p-6 w-full max-w-2xl my-8">
        <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-4">Create Tunnel</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Name
              </label>
              <input
                type="text"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white"
                required
              />
            </div>
            {formData.core !== 'xray' && (
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Node
                </label>
                <select
                  value={formData.node_id}
                  onChange={(e) => setFormData({ ...formData, node_id: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white"
                required={formData.core === 'rathole' || formData.core === 'backhaul' || formData.core === 'frp'}
                >
                  <option value="">Select a node</option>
                  {nodes.map((node) => (
                    <option key={node.id} value={node.id}>
                      {node.name}
                    </option>
                  ))}
                </select>
              </div>
            )}
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Core
              </label>
              <select
                value={formData.core}
                onChange={(e) => handleCoreChange(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white"
              >
                <option value="xray">GOST</option>
                <option value="rathole">Rathole</option>
                <option value="backhaul">Backhaul</option>
                <option value="chisel">Chisel</option>
                <option value="frp">FRP</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Type
              </label>
              <select
                value={formData.type}
                onChange={(e) => {
                  const value = e.target.value as BackhaulTransport
                  setFormData({ ...formData, type: value })
                  if (formData.core === 'backhaul') {
                    setBackhaulState((prev) => ({ ...prev, transport: value }))
                  }
                }}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white"
                disabled={formData.core === 'rathole' || formData.core === 'chisel' || formData.core === 'frp'}
              >
                {formData.core === 'rathole' || formData.core === 'chisel' ? (
                  <option value={formData.core}>{formData.core.charAt(0).toUpperCase() + formData.core.slice(1)}</option>
                ) : formData.core === 'frp' ? (
                  <>
                    <option value="tcp">TCP</option>
                    <option value="udp">UDP</option>
                  </>
                ) : formData.core === 'backhaul' ? (
                  <>
                    <option value="tcp">TCP</option>
                    <option value="udp">UDP</option>
                    <option value="ws">WebSocket (WS)</option>
                    <option value="wsmux">WebSocket Mux</option>
                    <option value="tcpmux">TCPMux</option>
                  </>
                ) : (
                  <>
                    <option value="tcp">TCP</option>
                    <option value="udp">UDP</option>
                    <option value="grpc">gRPC</option>
                    <option value="tcpmux">TCPMux</option>
                  </>
                )}
              </select>
            </div>
          </div>

          {formData.core === 'xray' && (formData.type === 'tcp' || formData.type === 'udp' || formData.type === 'grpc' || formData.type === 'tcpmux') && (
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Remote IP
                </label>
                <input
                  type="text"
                  value={formData.remote_ip}
                  onChange={(e) =>
                    setFormData({ ...formData, remote_ip: e.target.value || '127.0.0.1' })
                  }
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white"
                  placeholder="127.0.0.1 or [2001:db8::1]"
                />
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                  Target server IP address (IPv4 or IPv6)
                </p>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Port
                </label>
                <input
                  type="number"
                  value={formData.port}
                  onChange={(e) =>
                    setFormData({ ...formData, port: parseInt(e.target.value) || 8080 })
                  }
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white"
                  placeholder="8080"
                  min="1"
                  max="65535"
                  required
                />
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                  Port (same for panel and target server)
                </p>
              </div>
            </div>
          )}
          
          {formData.core === 'backhaul' && (
            <BackhaulForm
              state={backhaulState}
              onChange={(partial) => {
                setBackhaulState((prev) => ({ ...prev, ...partial }))
                if (partial.transport) {
                  setFormData((prev) => ({ ...prev, type: partial.transport as string }))
                }
              }}
              onOpenAdvanced={() => setShowBackhaulAdvanced(true)}
              acceptUdpVisible={
                backhaulState.transport === 'tcp' || backhaulState.transport === 'tcpmux'
              }
            />
          )}
          
          {formData.core === 'rathole' && (
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Local Port
                </label>
                <input
                  type="number"
                  value={formData.port}
                  onChange={(e) =>
                    setFormData({ ...formData, port: parseInt(e.target.value) || 8080 })
                  }
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white"
                  min="1"
                  max="65535"
                  required
                />
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                  Port on panel for clients to connect (should match local service port)
                </p>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Rathole Port
                </label>
                <input
                  type="number"
                  value={formData.rathole_remote_addr}
                  onChange={(e) =>
                    setFormData({ ...formData, rathole_remote_addr: e.target.value })
                  }
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white"
                  placeholder="23333"
                  min="1"
                  max="65535"
                  required
                />
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">Rathole server port on panel (IP: {window.location.hostname})</p>
              </div>
            </div>
          )}
          
          {formData.core === 'rathole' && (
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Token
                </label>
                <input
                  type="text"
                  value={formData.rathole_token}
                  onChange={(e) =>
                    setFormData({ ...formData, rathole_token: e.target.value })
                  }
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white"
                  placeholder="your-token"
                  required
                />
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">Authentication token</p>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Local Port
                </label>
                <input
                  type="number"
                  value={formData.rathole_local_port}
                  onChange={(e) =>
                    setFormData({ ...formData, rathole_local_port: e.target.value })
                  }
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white"
                  placeholder="8080"
                  min="1"
                  max="65535"
                  required
                />
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">Local service port (127.0.0.1:{formData.rathole_local_port || '8080'})</p>
              </div>
            </div>
          )}
          
          {formData.core === 'chisel' && (
            <>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Reverse Port
                  </label>
                  <input
                    type="number"
                    value={formData.port}
                    onChange={(e) =>
                      setFormData({ ...formData, port: parseInt(e.target.value) || 8080 })
                    }
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white"
                    min="1"
                    max="65535"
                    required
                  />
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                    Port where clients connect to access tunneled service
                  </p>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Control Port
                  </label>
                  <input
                    type="number"
                    value={formData.chisel_control_port}
                    onChange={(e) =>
                      setFormData({ ...formData, chisel_control_port: e.target.value })
                    }
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white"
                    placeholder={`${(parseInt(formData.port.toString()) || 8080) + 10000} (auto)`}
                    min="1"
                    max="65535"
                  />
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                    Chisel server control port (leave empty for auto: reverse port + 10000)
                  </p>
                </div>
              </div>
              <div className="grid grid-cols-1 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Local Port
                  </label>
                  <input
                    type="number"
                    value={formData.rathole_local_port}
                    onChange={(e) =>
                      setFormData({ ...formData, rathole_local_port: e.target.value })
                    }
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white"
                    placeholder="8080"
                    min="1"
                    max="65535"
                    required
                  />
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">Port on node where local service listens</p>
                </div>
              </div>
            </>
          )}
          
          {formData.core === 'frp' && (
            <>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Bind Port
                  </label>
                  <input
                    type="number"
                    value={formData.frp_bind_port}
                    onChange={(e) =>
                      setFormData({ ...formData, frp_bind_port: e.target.value })
                    }
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white"
                    placeholder="7000"
                    min="1"
                    max="65535"
                    required
                  />
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                    FRP server port on panel (default: 7000)
                  </p>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Remote Port
                  </label>
                  <input
                    type="number"
                    value={formData.port}
                    onChange={(e) =>
                      setFormData({ ...formData, port: parseInt(e.target.value) || 8080 })
                    }
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white"
                    placeholder="8080"
                    min="1"
                    max="65535"
                    required
                  />
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                    Port where clients connect to access tunneled service
                  </p>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Token (Optional)
                  </label>
                  <input
                    type="text"
                    value={formData.frp_token}
                    onChange={(e) =>
                      setFormData({ ...formData, frp_token: e.target.value })
                    }
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white"
                    placeholder="authentication-token"
                  />
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">Authentication token (optional)</p>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Local IP
                  </label>
                  <input
                    type="text"
                    value={formData.frp_local_ip}
                    onChange={(e) =>
                      setFormData({ ...formData, frp_local_ip: e.target.value })
                    }
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white"
                    placeholder="127.0.0.1"
                    required
                  />
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">Local service IP address</p>
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Local Port
                </label>
                <input
                  type="number"
                  value={formData.frp_local_port}
                  onChange={(e) =>
                    setFormData({ ...formData, frp_local_port: e.target.value })
                  }
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white"
                  placeholder="8080"
                  min="1"
                  max="65535"
                  required
                />
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">Local service port ({formData.frp_local_ip || '127.0.0.1'}:{formData.frp_local_port || '8080'})</p>
              </div>
            </>
          )}
          
          {/* v4 to v6 tunnel checkbox - only for Rathole, Backhaul, Chisel (not GOST) */}
          {formData.core !== 'xray' && formData.core !== 'frp' && (
            <>
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="v4_to_v6"
                  checked={formData.use_ipv6}
                  onChange={(e) => setFormData({ ...formData, use_ipv6: e.target.checked })}
                  className="w-4 h-4 text-blue-600 bg-gray-100 border-gray-300 rounded focus:ring-blue-500 dark:focus:ring-blue-600 dark:ring-offset-gray-800 focus:ring-2 dark:bg-gray-700 dark:border-gray-600"
                />
                <label htmlFor="v4_to_v6" className="text-sm font-medium text-gray-700 dark:text-gray-300">
                  v4 to v6 tunnel
                </label>
              </div>
              <p className="text-xs text-gray-500 dark:text-gray-400 -mt-2">
                Enable this to create a tunnel from IPv4 (panel) to IPv6 (node/target). Panel listens on IPv4, target uses IPv6.
              </p>
            </>
          )}

          <div className="flex gap-3 justify-end">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-200 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
            >
              Create Tunnel
            </button>
          </div>
        </form>
        <BackhaulAdvancedDrawer
          open={showBackhaulAdvanced}
          state={backhaulAdvanced}
          onClose={() => setShowBackhaulAdvanced(false)}
          onChange={setBackhaulAdvanced}
        />
      </div>
    </div>
  )
}

const BACKHAUL_TRANSPORTS: BackhaulTransport[] = ['tcp', 'udp', 'ws', 'wsmux', 'tcpmux']

function BackhaulForm({
  state,
  onChange,
  onOpenAdvanced,
  acceptUdpVisible,
}: {
  state: BackhaulFormState
  onChange: (partial: Partial<BackhaulFormState>) => void
  onOpenAdvanced: () => void
  acceptUdpVisible?: boolean
}) {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Control Port
          </label>
          <input
            type="number"
            value={state.control_port}
            onChange={(e) => onChange({ control_port: e.target.value })}
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white"
            placeholder="3080"
            min={1}
            max={65535}
          />
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
            Port where the node connects back to the panel.
          </p>
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Public Host
          </label>
          <input
            type="text"
            value={state.public_host}
            onChange={(e) => onChange({ public_host: e.target.value })}
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white"
            placeholder={typeof window !== 'undefined' ? window.location.hostname : 'panel.example.com'}
          />
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
            Hostname clients and nodes will use (defaults to current hostname).
          </p>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Public Port
          </label>
          <input
            type="number"
            value={state.public_port}
            onChange={(e) => onChange({ public_port: e.target.value })}
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white"
            placeholder="443"
            min={1}
            max={65535}
          />
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
            Port exposed on the panel for clients.
          </p>
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Bind IP (Public)
          </label>
          <input
            type="text"
            value={state.listen_ip}
            onChange={(e) => onChange({ listen_ip: e.target.value })}
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white"
            placeholder="0.0.0.0"
          />
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
            Optional specific IP for public listeners (default 0.0.0.0).
          </p>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Target Host
          </label>
          <input
            type="text"
            value={state.target_host}
            onChange={(e) => onChange({ target_host: e.target.value })}
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white"
            placeholder="127.0.0.1"
          />
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
            Destination host reachable from the node.
          </p>
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Target Port
          </label>
          <input
            type="number"
            value={state.target_port}
            onChange={(e) => onChange({ target_port: e.target.value })}
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white"
            placeholder="8080"
            min={1}
            max={65535}
          />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Override Control Address
          </label>
          <input
            type="text"
            value={state.remote_addr}
            onChange={(e) => onChange({ remote_addr: e.target.value })}
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white"
            placeholder="panel.example.com:3080"
          />
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
            Optional: override the control address the node should dial.
          </p>
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Token
          </label>
          <input
            type="text"
            value={state.token}
            onChange={(e) => onChange({ token: e.target.value })}
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white"
            placeholder="Optional authentication token"
          />
        </div>
      </div>

      {acceptUdpVisible && (
        <div className="flex items-center justify-between">
          <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
            Allow UDP over TCP
          </label>
          <input
            type="checkbox"
            checked={state.accept_udp}
            onChange={() => onChange({ accept_udp: !state.accept_udp })}
            className="h-4 w-4 text-blue-600 rounded border-gray-300 dark:border-gray-600 focus:ring-blue-500"
          />
        </div>
      )}

      <div className="pt-2">
        <button
          type="button"
          onClick={onOpenAdvanced}
          className="px-3 py-2 text-sm font-medium text-blue-600 dark:text-blue-400 hover:underline"
        >
          Advanced settings
        </button>
      </div>
    </div>
  )
}

function BackhaulAdvancedDrawer({
  open,
  onClose,
  state,
  onChange,
}: {
  open: boolean
  onClose: () => void
  state: BackhaulAdvancedState
  onChange: (next: BackhaulAdvancedState) => void
}) {
  if (!open) {
    return null
  }

  const updateServer = (key: keyof BackhaulAdvancedServerState, value: string | boolean) => {
    onChange({
      ...state,
      server: {
        ...state.server,
        [key]: value,
      },
    })
  }

  const updateClient = (key: keyof BackhaulAdvancedClientState, value: string | boolean) => {
    onChange({
      ...state,
      client: {
        ...state.client,
        [key]: value,
      },
    })
  }

  return (
    <div className="fixed inset-0 z-50 flex">
      <div className="flex-1 bg-black bg-opacity-40" onClick={onClose} />
      <div className="w-full max-w-xl h-full bg-white dark:bg-gray-900 shadow-xl overflow-y-auto p-6">
        <div className="flex justify-between items-center mb-6">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Backhaul Advanced Settings</h3>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
          >
            Close
          </button>
        </div>

        <div className="space-y-6">
          <div>
            <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wide mb-3">
              Server Options
            </h4>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Keepalive (s)</label>
                <input
                  type="number"
                  value={state.server.keepalive_period}
                  onChange={(e) => updateServer('keepalive_period', e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-800 dark:text-white"
                  min={1}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Heartbeat (s)</label>
                <input
                  type="number"
                  value={state.server.heartbeat}
                  onChange={(e) => updateServer('heartbeat', e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-800 dark:text-white"
                  min={1}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Channel Size</label>
                <input
                  type="number"
                  value={state.server.channel_size}
                  onChange={(e) => updateServer('channel_size', e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-800 dark:text-white"
                  min={1}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Mux Concurrency</label>
                <input
                  type="number"
                  value={state.server.mux_con}
                  onChange={(e) => updateServer('mux_con', e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-800 dark:text-white"
                  min={1}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Log Level</label>
                <select
                  value={state.server.log_level}
                  onChange={(e) => updateServer('log_level', e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-800 dark:text-white"
                >
                  <option value="panic">panic</option>
                  <option value="fatal">fatal</option>
                  <option value="error">error</option>
                  <option value="warn">warn</option>
                  <option value="info">info</option>
                  <option value="debug">debug</option>
                  <option value="trace">trace</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Web UI Port</label>
                <input
                  type="number"
                  value={state.server.web_port}
                  onChange={(e) => updateServer('web_port', e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-800 dark:text-white"
                  placeholder="0 (disable)"
                  min={0}
                />
              </div>
              <div className="col-span-2 flex items-center gap-3">
                <label className="text-sm font-medium text-gray-700 dark:text-gray-300 flex-1">Enable Sniffer</label>
                <input
                  type="checkbox"
                  checked={state.server.sniffer}
                  onChange={() => updateServer('sniffer', !state.server.sniffer)}
                  className="h-4 w-4 text-blue-600 rounded border-gray-300 dark:border-gray-600 focus:ring-blue-500"
                />
              </div>
              <div className="col-span-2">
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Sniffer Log Path</label>
                <input
                  type="text"
                  value={state.server.sniffer_log}
                  onChange={(e) => updateServer('sniffer_log', e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-800 dark:text-white"
                  placeholder="/var/log/backhaul.json"
                />
              </div>
              <div className="col-span-2">
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">TLS Certificate Path</label>
                <input
                  type="text"
                  value={state.server.tls_cert}
                  onChange={(e) => updateServer('tls_cert', e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-800 dark:text-white"
                />
              </div>
              <div className="col-span-2">
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">TLS Key Path</label>
                <input
                  type="text"
                  value={state.server.tls_key}
                  onChange={(e) => updateServer('tls_key', e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-800 dark:text-white"
                />
              </div>
              <div className="col-span-2 flex items-center gap-3">
                <label className="text-sm font-medium text-gray-700 dark:text-gray-300 flex-1">Disable Optimizations</label>
                <input
                  type="checkbox"
                  checked={state.server.skip_optz}
                  onChange={() => updateServer('skip_optz', !state.server.skip_optz)}
                  className="h-4 w-4 text-blue-600 rounded border-gray-300 dark:border-gray-600 focus:ring-blue-500"
                />
              </div>
              <div className="col-span-2 flex items-center gap-3">
                <label className="text-sm font-medium text-gray-700 dark:text-gray-300 flex-1">Enable Proxy Protocol</label>
                <input
                  type="checkbox"
                  checked={state.server.proxy_protocol}
                  onChange={() => updateServer('proxy_protocol', !state.server.proxy_protocol)}
                  className="h-4 w-4 text-blue-600 rounded border-gray-300 dark:border-gray-600 focus:ring-blue-500"
                />
              </div>
              <div className="col-span-2 flex items-center gap-3">
                <label className="text-sm font-medium text-gray-700 dark:text-gray-300 flex-1">TCP Nodelay</label>
                <input
                  type="checkbox"
                  checked={state.server.nodelay}
                  onChange={() => updateServer('nodelay', !state.server.nodelay)}
                  className="h-4 w-4 text-blue-600 rounded border-gray-300 dark:border-gray-600 focus:ring-blue-500"
                />
              </div>
            </div>
          </div>

          <div>
            <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wide mb-3">
              Client Options
            </h4>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Connection Pool</label>
                <input
                  type="number"
                  value={state.client.connection_pool}
                  onChange={(e) => updateClient('connection_pool', e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-800 dark:text-white"
                  min={1}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Retry Interval (s)</label>
                <input
                  type="number"
                  value={state.client.retry_interval}
                  onChange={(e) => updateClient('retry_interval', e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-800 dark:text-white"
                  min={1}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Dial Timeout (s)</label>
                <input
                  type="number"
                  value={state.client.dial_timeout}
                  onChange={(e) => updateClient('dial_timeout', e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-800 dark:text-white"
                  min={1}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Keepalive (s)</label>
                <input
                  type="number"
                  value={state.client.keepalive_period}
                  onChange={(e) => updateClient('keepalive_period', e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-800 dark:text-white"
                  min={1}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Log Level</label>
                <select
                  value={state.client.log_level}
                  onChange={(e) => updateClient('log_level', e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-800 dark:text-white"
                >
                  <option value="panic">panic</option>
                  <option value="fatal">fatal</option>
                  <option value="error">error</option>
                  <option value="warn">warn</option>
                  <option value="info">info</option>
                  <option value="debug">debug</option>
                  <option value="trace">trace</option>
                </select>
              </div>
              <div className="col-span-2">
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Edge IP (for WS/WSS)</label>
                <input
                  type="text"
                  value={state.client.edge_ip}
                  onChange={(e) => updateClient('edge_ip', e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-800 dark:text-white"
                  placeholder="Optional CDN edge IP"
                />
              </div>
              <div className="col-span-2 flex items-center gap-3">
                <label className="text-sm font-medium text-gray-700 dark:text-gray-300 flex-1">Aggressive Pool</label>
                <input
                  type="checkbox"
                  checked={state.client.aggressive_pool}
                  onChange={() => updateClient('aggressive_pool', !state.client.aggressive_pool)}
                  className="h-4 w-4 text-blue-600 rounded border-gray-300 dark:border-gray-600 focus:ring-blue-500"
                />
              </div>
              <div className="col-span-2 flex items-center gap-3">
                <label className="text-sm font-medium text-gray-700 dark:text-gray-300 flex-1">TCP Nodelay</label>
                <input
                  type="checkbox"
                  checked={state.client.nodelay}
                  onChange={() => updateClient('nodelay', !state.client.nodelay)}
                  className="h-4 w-4 text-blue-600 rounded border-gray-300 dark:border-gray-600 focus:ring-blue-500"
                />
              </div>
              <div className="col-span-2 flex items-center gap-3">
                <label className="text-sm font-medium text-gray-700 dark:text-gray-300 flex-1">Disable Optimizations</label>
                <input
                  type="checkbox"
                  checked={state.client.skip_optz}
                  onChange={() => updateClient('skip_optz', !state.client.skip_optz)}
                  className="h-4 w-4 text-blue-600 rounded border-gray-300 dark:border-gray-600 focus:ring-blue-500"
                />
              </div>
            </div>
          </div>

          <div>
            <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wide mb-3">
              Custom Ports
            </h4>
            <textarea
              value={state.customPorts}
              onChange={(e) => onChange({ ...state, customPorts: e.target.value })}
              className="w-full min-h-[120px] px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-800 dark:text-white"
              placeholder={`One entry per line. Examples:\n443\n443=127.0.0.1:8080\n443=[2001:db8::1]:8080\n2000-2100=127.0.0.1:22`}
            />
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
              Format matches Backhaul ports syntax. Leave empty to use the single public port above.
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}

function buildBackhaulSpec(
  base: BackhaulFormState,
  advanced: BackhaulAdvancedState,
  transportOverride?: BackhaulTransport,
): Record<string, any> {
  const transport = transportOverride ?? base.transport
  const controlPort = parseInt(base.control_port, 10)
  const publicPort = parseInt(base.public_port, 10)
  const targetPort = parseInt(base.target_port, 10)
  const listenIp = base.listen_ip.trim() || '0.0.0.0'
  const targetHost = base.target_host.trim() || '127.0.0.1'
  const token = base.token.trim()
  const panelHost = base.public_host.trim() || (typeof window !== 'undefined' ? window.location.hostname : '') || '127.0.0.1'

  const effectiveControlPort = !Number.isNaN(controlPort) && controlPort > 0
    ? controlPort
    : (!Number.isNaN(publicPort) && publicPort > 0
        ? publicPort
        : (!Number.isNaN(targetPort) && targetPort > 0 ? targetPort : 3080))
  const effectivePublicPort = !Number.isNaN(publicPort) && publicPort > 0 ? publicPort : effectiveControlPort
  const effectiveTargetPort = !Number.isNaN(targetPort) && targetPort > 0 ? targetPort : effectivePublicPort

  const remoteAddr = base.remote_addr.trim() || `${panelHost}:${effectiveControlPort}`
  const listenedPort = listenIp !== '0.0.0.0' ? `${listenIp}:${effectivePublicPort}` : `${effectivePublicPort}`
  const defaultPortEntry = `${listenedPort}=${targetHost}:${effectiveTargetPort}`

  const ports = advanced.customPorts
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
  if (ports.length === 0) {
    ports.push(defaultPortEntry)
  }

  const serverOptions: Record<string, any> = {}
  Object.entries(advanced.server).forEach(([key, value]) => {
    if (booleanServerKeys.has(key)) {
      if (value) {
        serverOptions[key] = true
      }
      return
    }
    if (numericServerKeys.has(key)) {
      const num = Number(value)
      if (!Number.isNaN(num) && value !== '') {
        serverOptions[key] = num
      }
      return
    }
    if (stringServerKeys.has(key)) {
      const val = typeof value === 'string' ? value.trim() : value
      if (val) {
        serverOptions[key] = val
      }
    }
  })

  const clientOptions: Record<string, any> = {}
  Object.entries(advanced.client).forEach(([key, value]) => {
    if (booleanClientKeys.has(key)) {
      if (value) {
        clientOptions[key] = true
      }
      return
    }
    if (numericClientKeys.has(key)) {
      const num = Number(value)
      if (!Number.isNaN(num) && value !== '') {
        clientOptions[key] = num
      }
      return
    }
    if (stringClientKeys.has(key)) {
      const val = typeof value === 'string' ? value.trim() : value
      if (val) {
        clientOptions[key] = val
      }
    }
  })

  const spec: Record<string, any> = {
    transport,
    bind_addr: `0.0.0.0:${effectiveControlPort}`,
    remote_addr: remoteAddr,
    listen_ip: listenIp,
    control_port: effectiveControlPort,
    public_port: effectivePublicPort,
    listen_port: effectivePublicPort,
    target_host: targetHost,
    target_port: effectiveTargetPort,
    target_addr: `${targetHost}:${effectiveTargetPort}`,
    public_host: panelHost,
    ports,
  }

  if (token) {
    spec.token = token
  }
  if (base.accept_udp && (transport === 'tcp' || transport === 'tcpmux')) {
    spec.accept_udp = true
  }
  if (Object.keys(serverOptions).length > 0) {
    spec.server_options = serverOptions
  }
  if (Object.keys(clientOptions).length > 0) {
    spec.client_options = clientOptions
  }

  return spec
}

function parseBackhaulSpec(spec: Record<string, any>, currentType: string): {
  state: BackhaulFormState
  advanced: BackhaulAdvancedState
} {
  const state = createDefaultBackhaulState()
  const advanced = createDefaultBackhaulAdvancedState()

  if (BACKHAUL_TRANSPORTS.includes(currentType as BackhaulTransport)) {
    state.transport = currentType as BackhaulTransport
  }

  if (!spec) {
    return { state, advanced }
  }

  const controlPortCandidate =
    spec.control_port ??
    extractPort(spec.bind_addr) ??
    extractPort(spec.remote_addr)
  if (controlPortCandidate) {
    state.control_port = String(controlPortCandidate)
  }

  state.listen_ip = spec.listen_ip ?? state.listen_ip

  const publicPortCandidate =
    spec.public_port ??
    spec.listen_port ??
    derivePortFromPorts(spec.ports)
  if (publicPortCandidate) {
    state.public_port = String(publicPortCandidate)
  }

  if (spec.target_host) {
    state.target_host = String(spec.target_host)
  } else if (typeof spec.target_addr === 'string') {
    const parsed = parseAddressPort(spec.target_addr)
    state.target_host = parsed.host
  }

  const targetPortCandidate =
    spec.target_port ??
    (typeof spec.target_addr === 'string'
      ? parseAddressPort(spec.target_addr).port
      : undefined)
  if (targetPortCandidate) {
    state.target_port = String(targetPortCandidate)
  }

  state.token = spec.token ?? ''
  state.public_host = spec.public_host ?? ''
  state.remote_addr = spec.remote_addr ?? ''
  state.accept_udp = Boolean(spec.accept_udp)

  if (Array.isArray(spec.ports) && spec.ports.length > 0) {
    advanced.customPorts = spec.ports.join('\n')
  }

  const serverOptions = spec.server_options || {}
  Object.entries(advanced.server).forEach(([key, defaultValue]) => {
    const value = serverOptions[key]
    if (value === undefined || value === null) {
      return
    }
    if (typeof defaultValue === 'boolean') {
      advanced.server[key as keyof BackhaulAdvancedServerState] = Boolean(value)
    } else {
      advanced.server[key as keyof BackhaulAdvancedServerState] = String(value)
    }
  })

  const clientOptions = spec.client_options || {}
  Object.entries(advanced.client).forEach(([key, defaultValue]) => {
    const value = clientOptions[key]
    if (value === undefined || value === null) {
      return
    }
    if (typeof defaultValue === 'boolean') {
      advanced.client[key as keyof BackhaulAdvancedClientState] = Boolean(value)
    } else {
      advanced.client[key as keyof BackhaulAdvancedClientState] = String(value)
    }
  })

  return { state, advanced }
}

function extractPort(value: unknown): string | undefined {
  if (typeof value === 'number') {
    return value.toString()
  }
  if (typeof value === 'string') {
    const parts = value.split(':')
    const port = parts[parts.length - 1]
    if (port && !Number.isNaN(Number(port))) {
      return port
    }
  }
  return undefined
}

function derivePortFromPorts(value: unknown): string | undefined {
  if (!Array.isArray(value) || value.length === 0) {
    return undefined
  }
  const first = value[0]
  if (typeof first !== 'string') {
    return undefined
  }
  const [left] = first.split('=')
  if (!left) {
    return undefined
  }
  const segments = left.split(':')
  const port = segments[segments.length - 1]
  return port && !Number.isNaN(Number(port)) ? port : undefined
}

export default Tunnels
