import React, { useState, useEffect } from 'react';
import axios from 'axios';

const DnsManager = ({ nodeId }) => {
  const [globalDns, setGlobalDns] = useState({
    globalDnsTag: '',
    globalClientIp: '',
    globalQueryStrategy: 'UseIP',
    globalDisableCache: false,
    globalDisableFallback: false,
    globalDisableFallbackIfMatch: false,
  });
  const [servers, setServers] = useState([]);
  const [editingServer, setEditingServer] = useState(null);
  const [showServerModal, setShowServerModal] = useState(false);

  useEffect(() => {
    fetchDnsConfig();
  }, []);

  const fetchDnsConfig = async () => {
    try {
      const response = await axios.get(`/api/node/${nodeId}/dns`);
      const data = response.data;
      setGlobalDns({
        globalDnsTag: data.tag || '',
        globalClientIp: data.clientIp || '',
        globalQueryStrategy: data.queryStrategy || 'UseIP',
        globalDisableCache: data.disableCache || false,
        globalDisableFallback: data.disableFallback || false,
        globalDisableFallbackIfMatch: data.disableFallbackIfMatch || false,
      });
      setServers(data.servers || []);
    } catch (error) {
      console.error('Error fetching DNS config', error);
    }
  };

  const handleGlobalChange = (e) => {
    const { name, value, type, checked } = e.target;
    setGlobalDns({
      ...globalDns,
      [name]: type === 'checkbox' ? checked : value,
    });
  };

  const openAddServerModal = () => {
    setEditingServer({
      connectionType: 'udp',
      address: '',
      port: '',
      domains: '',
      expectIPs: '',
      clientIP: '',
      skipFallback: false,
      queryStrategy: '',
    });
    setShowServerModal(true);
  };

  const openEditServerModal = (index) => {
    setEditingServer({ ...servers[index], index });
    setShowServerModal(true);
  };

  const saveServerModal = () => {
    if (!editingServer.address) {
      alert("Server address is required.");
      return;
    }
    let newServers = [...servers];
    if (editingServer.index !== undefined) {
      newServers[editingServer.index] = editingServer;
    } else {
      newServers.push(editingServer);
    }
    setServers(newServers);
    setShowServerModal(false);
    setEditingServer(null);
  };

  const deleteServer = (index) => {
    if (window.confirm("Are you sure you want to delete this server?")) {
      let newServers = [...servers];
      newServers.splice(index, 1);
      setServers(newServers);
    }
  };

  const saveDnsConfig = async () => {
    const payload = {
      globalDnsTag: globalDns.globalDnsTag,
      globalClientIp: globalDns.globalClientIp,
      globalQueryStrategy: globalDns.globalQueryStrategy,
      globalDisableCache: globalDns.globalDisableCache,
      globalDisableFallback: globalDns.globalDisableFallback,
      globalDisableFallbackIfMatch: globalDns.globalDisableFallbackIfMatch,
      hosts: {},
      servers: servers.map((server) => {
        let newServer = { ...server };
        if (typeof newServer.domains === 'string') {
          newServer.domains = newServer.domains.split(',').map(s => s.trim()).filter(s => s);
        }
        if (typeof newServer.expectIPs === 'string') {
          newServer.expectIPs = newServer.expectIPs.split(',').map(s => s.trim()).filter(s => s);
        }
        if (newServer.port) {
          newServer.port = parseInt(newServer.port);
        }
        return newServer;
      }),
    };
    try {
      const response = await axios.post(`/api/node/${nodeId}/dns`, payload);
      if (response.data.success) {
        alert("DNS configuration updated successfully.");
      } else {
        alert("Failed to update DNS configuration.");
      }
    } catch (error) {
      console.error('Error saving DNS config', error);
      alert("Error saving DNS configuration.");
    }
  };

  return (
    <div className="p-6 bg-gray-800 text-gray-100 min-h-screen">
      <h2 className="text-2xl font-bold text-center mb-6">DNS Server Configuration</h2>
      
      <div className="bg-gray-700 rounded-lg p-4 mb-6">
        <h4 className="text-xl font-semibold mb-4">Global DNS Settings</h4>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label className="block mb-1">DNS Tag</label>
            <input 
              type="text" 
              name="globalDnsTag"
              value={globalDns.globalDnsTag}
              onChange={handleGlobalChange}
              className="w-full p-2 rounded bg-gray-600"
              placeholder="e.g., dns_inbound"
            />
          </div>
          <div>
            <label className="block mb-1">Client IP</label>
            <input 
              type="text" 
              name="globalClientIp"
              value={globalDns.globalClientIp}
              onChange={handleGlobalChange}
              className="w-full p-2 rounded bg-gray-600"
              placeholder="e.g., 1.2.3.4"
            />
          </div>
          <div>
            <label className="block mb-1">Query Strategy</label>
            <select 
              name="globalQueryStrategy"
              value={globalDns.globalQueryStrategy}
              onChange={handleGlobalChange}
              className="w-full p-2 rounded bg-gray-600"
            >
              <option value="UseIP">UseIP</option>
              <option value="UseIPv4">UseIPv4</option>
              <option value="UseIPv6">UseIPv6</option>
            </select>
          </div>
          <div className="flex items-center">
            <input 
              type="checkbox"
              name="globalDisableCache"
              checked={globalDns.globalDisableCache}
              onChange={handleGlobalChange}
              className="mr-2"
            />
            <span>Disable Cache</span>
          </div>
          <div className="flex items-center">
            <input 
              type="checkbox"
              name="globalDisableFallback"
              checked={globalDns.globalDisableFallback}
              onChange={handleGlobalChange}
              className="mr-2"
            />
            <span>Disable Fallback</span>
          </div>
          <div className="flex items-center">
            <input 
              type="checkbox"
              name="globalDisableFallbackIfMatch"
              checked={globalDns.globalDisableFallbackIfMatch}
              onChange={handleGlobalChange}
              className="mr-2"
            />
            <span>Disable Fallback If Match</span>
          </div>
        </div>
      </div>

      <div className="bg-gray-700 rounded-lg p-4 mb-6">
        <div className="flex justify-between items-center mb-4">
          <h4 className="text-xl font-semibold">DNS Servers</h4>
          <button 
            onClick={openAddServerModal}
            className="bg-green-500 hover:bg-green-600 px-4 py-2 rounded"
          >
            Add Server
          </button>
        </div>
        <table className="min-w-full bg-gray-600 rounded">
          <thead>
            <tr>
              <th className="py-2 px-3 border">Conn. Type</th>
              <th className="py-2 px-3 border">Address</th>
              <th className="py-2 px-3 border">Port</th>
              <th className="py-2 px-3 border">Domains</th>
              <th className="py-2 px-3 border">Expected IPs</th>
              <th className="py-2 px-3 border">Client IP</th>
              <th className="py-2 px-3 border">Skip Fallback</th>
              <th className="py-2 px-3 border">Query Strategy</th>
              <th className="py-2 px-3 border">Actions</th>
            </tr>
          </thead>
          <tbody>
            {servers.map((srv, index) => (
              <tr key={index} className="text-center border-t">
                <td className="py-2 px-3">{srv.connectionType || "udp"}</td>
                <td className="py-2 px-3">{srv.address}</td>
                <td className="py-2 px-3">{srv.port}</td>
                <td className="py-2 px-3">{Array.isArray(srv.domains) ? srv.domains.join(", ") : srv.domains}</td>
                <td className="py-2 px-3">{Array.isArray(srv.expectIPs) ? srv.expectIPs.join(", ") : srv.expectIPs}</td>
                <td className="py-2 px-3">{srv.clientIP}</td>
                <td className="py-2 px-3">{srv.skipFallback ? "On" : "Off"}</td>
                <td className="py-2 px-3">{srv.queryStrategy}</td>
                <td className="py-2 px-3 space-x-2">
                  <button onClick={() => openEditServerModal(index)} className="bg-blue-500 hover:bg-blue-600 px-2 py-1 rounded">Edit</button>
                  <button onClick={() => deleteServer(index)} className="bg-red-500 hover:bg-red-600 px-2 py-1 rounded">Delete</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex justify-end">
        <button onClick={saveDnsConfig} className="bg-blue-500 hover:bg-blue-600 px-6 py-2 rounded">
          Save DNS Config to API
        </button>
      </div>

      {showServerModal && (
        <div className="fixed inset-0 flex items-center justify-center bg-black bg-opacity-50">
          <div className="bg-gray-800 p-6 rounded w-11/12 md:w-1/2">
            <h3 className="text-xl font-bold mb-4">{editingServer.index !== undefined ? "Edit" : "Add"} DNS Server</h3>
            <div className="space-y-4">
              <div>
                <label className="block mb-1">Server Address</label>
                <input 
                  type="text" 
                  value={editingServer.address}
                  onChange={(e) => setEditingServer({ ...editingServer, address: e.target.value })}
                  className="w-full p-2 rounded bg-gray-600"
                  placeholder="e.g., 8.8.8.8"
                />
              </div>
              <div>
                <label className="block mb-1">Connection Type</label>
                <select 
                  value={editingServer.connectionType}
                  onChange={(e) => setEditingServer({ ...editingServer, connectionType: e.target.value })}
                  className="w-full p-2 rounded bg-gray-600"
                >
                  <option value="udp">UDP</option>
                  <option value="tcp">TCP</option>
                  <option value="tcp_local">TCP Local</option>
                  <option value="doh">DOH</option>
                  <option value="doh_local">DOH Local</option>
                  <option value="doq_local">DOQ Local</option>
                </select>
              </div>
              {(editingServer.connectionType === "udp" ||
                editingServer.connectionType === "tcp" ||
                editingServer.connectionType === "tcp_local") && (
                <div>
                  <label className="block mb-1">Port</label>
                  <input 
                    type="number" 
                    value={editingServer.port}
                    onChange={(e) => setEditingServer({ ...editingServer, port: e.target.value })}
                    className="w-full p-2 rounded bg-gray-600"
                    placeholder="Default: 53"
                  />
                </div>
              )}
              <div>
                <label className="block mb-1">Domains</label>
                <input 
                  type="text" 
                  value={editingServer.domains}
                  onChange={(e) => setEditingServer({ ...editingServer, domains: e.target.value })}
                  className="w-full p-2 rounded bg-gray-600"
                  placeholder="Comma separated (e.g., domain:xray.com, geosite:netflix)"
                />
              </div>
              <div>
                <label className="block mb-1">Expected IPs</label>
                <input 
                  type="text" 
                  value={editingServer.expectIPs}
                  onChange={(e) => setEditingServer({ ...editingServer, expectIPs: e.target.value })}
                  className="w-full p-2 rounded bg-gray-600"
                  placeholder="Comma separated (e.g., geoip:cn)"
                />
              </div>
              <div>
                <label className="block mb-1">Client IP (optional)</label>
                <input 
                  type="text" 
                  value={editingServer.clientIP}
                  onChange={(e) => setEditingServer({ ...editingServer, clientIP: e.target.value })}
                  className="w-full p-2 rounded bg-gray-600"
                  placeholder="e.g., 1.2.3.4"
                />
              </div>
              <div className="flex items-center">
                <input 
                  type="checkbox" 
                  checked={editingServer.skipFallback}
                  onChange={(e) => setEditingServer({ ...editingServer, skipFallback: e.target.checked })}
                  className="mr-2"
                />
                <span>Skip Fallback</span>
              </div>
              <div>
                <label className="block mb-1">Query Strategy</label>
                <select 
                  value={editingServer.queryStrategy}
                  onChange={(e) => setEditingServer({ ...editingServer, queryStrategy: e.target.value })}
                  className="w-full p-2 rounded bg-gray-600"
                >
                  <option value="">(Leave empty)</option>
                  <option value="UseIP">UseIP</option>
                  <option value="UseIPv4">UseIPv4</option>
                  <option value="UseIPv6">UseIPv6</option>
                </select>
              </div>
            </div>
            <div className="mt-6 flex justify-end space-x-4">
              <button onClick={() => { setShowServerModal(false); setEditingServer(null); }} className="bg-gray-500 hover:bg-gray-600 px-4 py-2 rounded">
                Cancel
              </button>
              <button onClick={saveServerModal} className="bg-blue-500 hover:bg-blue-600 px-4 py-2 rounded">
                Save Server
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default DnsManager;
