import { useEffect, useState } from 'react'
import { Plus, Trash2, Edit2 } from 'lucide-react'
import api from '../api/client'

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

const Tunnels = () => {
  const [tunnels, setTunnels] = useState<Tunnel[]>([])
  const [nodes, setNodes] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [showAddModal, setShowAddModal] = useState(false)
  const [editingTunnel, setEditingTunnel] = useState<Tunnel | null>(null)

  useEffect(() => {
    fetchData()
    // Check if we should open the modal from URL params
    const params = new URLSearchParams(window.location.search)
    if (params.get('create') === 'true') {
      setShowAddModal(true)
      // Clean URL
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
                  {tunnel.core} / {tunnel.type}
                </p>
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
                      {tunnel.spec?.local_addr ? tunnel.spec.local_addr.split(':')[1] : 'N/A'}
                    </span>
                  </div>
                </>
              )}
              {tunnel.core === 'xray' && (tunnel.spec?.forward_to || (tunnel.spec?.remote_ip && tunnel.spec?.remote_port)) && (
                <div className="flex justify-between items-center py-2 border-b border-gray-100 dark:border-gray-700">
                  <span className="text-sm text-gray-500 dark:text-gray-400">Forward To</span>
                  <span className="text-sm font-medium text-gray-900 dark:text-white break-all ml-2">
                    {tunnel.spec.forward_to || `${tunnel.spec.remote_ip}:${tunnel.spec.remote_port}`}
                  </span>
                </div>
              )}
            </div>

            {/* Footer Info */}
            <div className="flex justify-between items-center text-xs text-gray-500 dark:text-gray-400 pt-3 border-t border-gray-100 dark:border-gray-700">
              <span>Revision {tunnel.revision}</span>
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
  // Extract remote_ip and remote_port from spec (Shifter pattern)
  // Fallback to parsing forward_to for backward compatibility
  const remoteIp = tunnel.spec?.remote_ip || (tunnel.spec?.forward_to ? tunnel.spec.forward_to.split(':')[0] : '127.0.0.1')
  const remotePort = tunnel.spec?.remote_port || (tunnel.spec?.forward_to ? parseInt(tunnel.spec.forward_to.split(':')[1]) || 8080 : 8080)
  
  const [formData, setFormData] = useState({
    name: tunnel.name,
    local_port: tunnel.spec?.listen_port || tunnel.spec?.remote_port || 8080,  // listen_port is panel port
    remote_ip: remoteIp,
    remote_port: remotePort,
    rathole_remote_addr: tunnel.spec?.remote_addr || '',
    rathole_local_port: tunnel.spec?.local_addr ? tunnel.spec.local_addr.split(':')[1] : '',
  })

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      // Build updated spec
      const updatedSpec = { ...tunnel.spec }
      // listen_port: panel port where clients connect (Shifter pattern)
      updatedSpec.listen_port = parseInt(formData.local_port.toString()) || 8080
      
      if (tunnel.core === 'rathole') {
        if (formData.rathole_remote_addr) {
          const remoteParts = formData.rathole_remote_addr.split(':')
          const remoteHost = remoteParts[0] || window.location.hostname
          const remotePort = remoteParts[1] || '23333'
          updatedSpec.remote_addr = `${remoteHost}:${remotePort}`
        }
        if (formData.rathole_local_port) {
          updatedSpec.local_addr = `127.0.0.1:${formData.rathole_local_port}`
        }
      } else if (tunnel.core === 'xray' && (tunnel.type === 'tcp' || tunnel.type === 'udp' || tunnel.type === 'ws' || tunnel.type === 'grpc' || tunnel.type === 'tcpmux')) {
        const remoteIp = formData.remote_ip || '127.0.0.1'
        const remotePort = parseInt(formData.remote_port.toString()) || 8080
        updatedSpec.remote_ip = remoteIp
        updatedSpec.remote_port = remotePort
        // Also set forward_to for backward compatibility
        updatedSpec.forward_to = `${remoteIp}:${remotePort}`
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
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Local Port
            </label>
            <input
              type="number"
              value={formData.local_port}
              onChange={(e) =>
                setFormData({ ...formData, local_port: parseInt(e.target.value) || 8080 })
              }
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white"
              min="1"
              max="65535"
            />
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
              Port on panel where clients will connect
            </p>
          </div>
          
          {tunnel.core === 'xray' && (tunnel.type === 'tcp' || tunnel.type === 'udp' || tunnel.type === 'ws' || tunnel.type === 'grpc' || tunnel.type === 'tcpmux') && (
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
                  placeholder="127.0.0.1"
                />
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                  Target server IP address
                </p>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Remote Port
                </label>
                <input
                  type="number"
                  value={formData.remote_port}
                  onChange={(e) =>
                    setFormData({ ...formData, remote_port: parseInt(e.target.value) || 8080 })
                  }
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white"
                  placeholder="8080"
                  min="1"
                  max="65535"
                />
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                  Port on target server (e.g., 8080 for VLESS)
                </p>
              </div>
            </>
          )}
          
          {tunnel.core === 'rathole' && (
            <>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Rathole Port
                </label>
                <input
                  type="text"
                  value={formData.rathole_remote_addr}
                  onChange={(e) =>
                    setFormData({ ...formData, rathole_remote_addr: e.target.value })
                  }
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white"
                  placeholder={`${window.location.hostname}:23333`}
                />
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
          
          {tunnel.core === 'xray' && (tunnel.type === 'tcp' || tunnel.type === 'udp' || tunnel.type === 'ws' || tunnel.type === 'grpc' || tunnel.type === 'tcpmux') && (
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Forward To
              </label>
              <input
                type="text"
                value={formData.forward_to || (formData.forward_port ? `127.0.0.1:${formData.forward_port}` : '127.0.0.1:2053')}
                onChange={(e) => {
                  const value = e.target.value || '127.0.0.1:2053'
                  setFormData({ ...formData, forward_to: value })
                  // Extract port for backward compatibility
                  if (value.includes(':')) {
                    const parts = value.split(':')
                    if (parts.length >= 2) {
                      setFormData(prev => ({ ...prev, forward_port: parts[parts.length - 1] }))
                    }
                  }
                }}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white"
                placeholder="127.0.0.1:2053"
              />
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                Target address (host:port) to forward traffic to
              </p>
            </div>
          )}
          
          <div className="flex gap-3 justify-end">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200"
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
    local_port: 8080,
    remote_ip: '127.0.0.1',
    remote_port: 8080,
    rathole_remote_addr: `${window.location.hostname}:23333`,
    rathole_token: '',
    rathole_local_port: '8080',
    spec: {} as Record<string, any>,
  })

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      const spec = getSpecForType(formData.core, formData.type)
      // listen_port: panel port where clients connect (Shifter pattern)
      spec.listen_port = parseInt(formData.local_port.toString()) || 8080
      
      // For GOST tunnels (TCP/UDP/WS/gRPC/TCPMux), set remote_ip and remote_port (Shifter pattern)
      if (formData.core === 'xray' && (formData.type === 'tcp' || formData.type === 'udp' || formData.type === 'ws' || formData.type === 'grpc' || formData.type === 'tcpmux')) {
        const remoteIp = formData.remote_ip || '127.0.0.1'
        const remotePort = parseInt(formData.remote_port.toString()) || 8080
        spec.remote_ip = remoteIp
        spec.remote_port = remotePort
        // Also set forward_to for backward compatibility
        spec.forward_to = `${remoteIp}:${remotePort}`
      }
      
      // For Rathole, add required fields
      if (formData.core === 'rathole') {
        // Parse rathole_remote_addr to get IP and port
        const remoteParts = formData.rathole_remote_addr.split(':')
        const remoteHost = remoteParts[0] || window.location.hostname
        const remotePort = remoteParts[1] || '23333'
        spec.remote_addr = `${remoteHost}:${remotePort}`
        spec.token = formData.rathole_token
        spec.local_addr = `127.0.0.1:${formData.rathole_local_port}`
        spec.remote_port = parseInt(formData.remote_port.toString()) || 10000  // Proxy port for clients
      }
      
      const payload = {
        name: formData.name,
        core: formData.core,
        type: formData.type,
        node_id: formData.node_id || null,  // null for GOST tunnels (no node needed)
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
    const baseSpec: Record<string, any> = {
      // listen_port will be set from formData.local_port
    }

    // Rathole is a separate core, not a type
    if (core === 'rathole') {
      return { ...baseSpec, remote_addr: `${window.location.hostname}:23333`, token: '', local_addr: '127.0.0.1:8080' }
    }

    // GOST core types
    switch (type) {
      case 'ws':
        return { ...baseSpec, path: '/', uuid: generateUUID() }
      case 'grpc':
        return { ...baseSpec, service_name: 'GrpcService', uuid: generateUUID() }
      case 'udp':
        return { ...baseSpec, uuid: generateUUID(), header_type: 'none' }
      default:
        return baseSpec
    }
  }

  // When core changes, update type accordingly
  const handleCoreChange = (core: string) => {
    let newType = formData.type
    if (core === 'rathole') {
      newType = core // Type matches core for rathole
    } else if (formData.type === 'rathole') {
      newType = 'tcp' // Reset to default GOST type
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
      <div className="bg-white rounded-lg p-6 w-full max-w-2xl my-8">
        <h2 className="text-xl font-bold text-gray-900 mb-4">Create Tunnel</h2>
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
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Node
              </label>
              <select
                value={formData.node_id}
                onChange={(e) => setFormData({ ...formData, node_id: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white"
                required={formData.core === 'rathole'}
              >
                <option value="">Select a node</option>
                {nodes.map((node) => (
                  <option key={node.id} value={node.id}>
                    {node.name}
                  </option>
                ))}
              </select>
            </div>
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
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Type
              </label>
              <select
                value={formData.type}
                onChange={(e) => setFormData({ ...formData, type: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white"
                disabled={formData.core === 'rathole'}
              >
                {formData.core === 'rathole' ? (
                  <option value={formData.core}>{formData.core.charAt(0).toUpperCase() + formData.core.slice(1)}</option>
                ) : (
                  <>
                    <option value="tcp">TCP</option>
                    <option value="udp">UDP</option>
                    <option value="ws">WebSocket</option>
                    <option value="grpc">gRPC</option>
                    <option value="tcpmux">TCPMux</option>
                  </>
                )}
              </select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Local Port
              </label>
              <input
                type="number"
                value={formData.local_port}
                onChange={(e) =>
                  setFormData({ ...formData, local_port: parseInt(e.target.value) || 8080 })
                }
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white"
                min="1"
                max="65535"
                required
              />
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                {formData.core === 'rathole' 
                  ? 'Port on panel for clients to connect (should match local service port)'
                  : 'Port on panel where clients will connect (e.g., 8080)'}
              </p>
            </div>
            {formData.core === 'xray' && (formData.type === 'tcp' || formData.type === 'udp' || formData.type === 'ws' || formData.type === 'grpc' || formData.type === 'tcpmux') && (
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
                    placeholder="127.0.0.1"
                  />
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                    Target server IP address
                  </p>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Remote Port
                  </label>
                  <input
                    type="number"
                    value={formData.remote_port}
                    onChange={(e) =>
                      setFormData({ ...formData, remote_port: parseInt(e.target.value) || 8080 })
                    }
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white"
                    placeholder="8080"
                    min="1"
                    max="65535"
                  />
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                    Port on target server (e.g., 8080 for VLESS)
                  </p>
                </div>
              </>
            )}
            {formData.core === 'rathole' && (
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Rathole Port
                </label>
                <input
                  type="text"
                  value={formData.rathole_remote_addr}
                  onChange={(e) =>
                    setFormData({ ...formData, rathole_remote_addr: e.target.value })
                  }
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white"
                  placeholder={`${window.location.hostname}:23333`}
                  required
                />
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">Panel IP:Port for rathole server (e.g., {window.location.hostname}:23333)</p>
              </div>
            )}
          </div>
          
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

          <div className="flex gap-3 justify-end">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200"
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
      </div>
    </div>
  )
}

export default Tunnels

