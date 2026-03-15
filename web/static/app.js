// ============================================================================
// AUTHENTICATION HELPER
// ============================================================================

const AuthFetch = async (url, options = {}) => {
    const token = localStorage.getItem('pso_token');
    
    if (!token) {
        window.location.href = '/login';
        throw new Error('Not authenticated');
    }

    options.headers = {
        ...options.headers,
        'Authorization': `Bearer ${token}`
    };

    const response = await fetch(url, options);
    
    if (response.status === 401) {
        localStorage.removeItem('pso_token');
        localStorage.removeItem('pso_user');
        window.location.href = '/login';
        throw new Error('Session expired');
    }
    
    return response;
};

// Check auth on page load
if (!localStorage.getItem('pso_token')) {
    window.location.href = '/login';
}


// ============================================================================
// INSTALLATION PROGRESS MODAL
// ============================================================================

function InstallProgressModal({ serviceId, serviceName, isOpen, onClose, onCancel }) {
    const [progress, setProgress] = useState({ status: 'not_started', progress: 0, step: '', error: null });
    const [polling, setPolling] = useState(null);

    useEffect(() => {
        if (isOpen && serviceId) {
            // Start polling for progress
            const interval = setInterval(async () => {
                try {
                    const response = await AuthFetch(`${API_URL}/services/${serviceId}/install-status`);
                    const data = await response.json();
                    setProgress(data);

                    // Stop polling if complete, failed, or cancelled
                    if (data.status === 'complete' || data.status === 'failed' || data.status === 'cancelled') {
                        clearInterval(interval);
                        // Auto-close after 2 seconds on completion
                        if (data.status === 'complete') {
                            setTimeout(() => onClose(), 2000);
                        }
                    }
                } catch (error) {
                    console.error('Failed to fetch install status:', error);
                }
            }, 500);

            setPolling(interval);
            return () => clearInterval(interval);
        }
    }, [isOpen, serviceId]);

    const handleCancel = async () => {
        try {
            await AuthFetch(`${API_URL}/services/${serviceId}/install-cancel`, {
                method: 'POST'
            });
        } catch (error) {
            console.error('Failed to cancel installation:', error);
        }
    };

    if (!isOpen) return null;

    const getStatusColor = () => {
        switch (progress.status) {
            case 'complete': return 'var(--success)';
            case 'failed': return 'var(--error)';
            case 'cancelled': return 'var(--warning)';
            default: return 'var(--primary)';
        }
    };

    return (
        <div className="modal">
            <div className="modal-content install-progress-modal">
                <div className="modal-header">
                    <div>
                        <h2 className="modal-title">Installing {serviceName || serviceId}</h2>
                        <p style={{color: 'var(--text-dim)', marginTop: '4px', fontSize: '14px'}}>
                            {progress.step || 'Preparing installation...'}
                        </p>
                    </div>
                    {progress.status !== 'in_progress' && (
                        <button className="modal-close" onClick={onClose}>✕</button>
                    )}
                </div>
                
                <div className="modal-body">
                    <div className="install-progress-bar">
                        <div 
                            className="install-progress-fill" 
                            style={{
                                width: `${progress.progress}%`,
                                backgroundColor: getStatusColor()
                            }}
                        />
                    </div>

                    <div style={{marginTop: '1rem', textAlign: 'center', color: 'var(--text-dim)'}}>
                        {progress.progress}%
                    </div>

                    {progress.status === 'in_progress' && (
                        <div className="install-step">
                            <div className="step-spinner"></div>
                            <span>{progress.step}</span>
                        </div>
                    )}

                    {progress.status === 'complete' && (
                        <div className="install-complete">
                            <div className="step-icon">✓</div>
                            <span>Installation complete!</span>
                        </div>
                    )}

                    {progress.status === 'failed' && (
                        <div className="install-failed">
                            <div className="step-icon">✗</div>
                            <span>Installation failed: {progress.error || 'Unknown error'}</span>
                        </div>
                    )}

                    {progress.status === 'cancelled' && (
                        <div className="install-failed">
                            <div className="step-icon">✗</div>
                            <span>Installation cancelled</span>
                        </div>
                    )}
                </div>

                {progress.status === 'in_progress' && (
                    <div className="modal-footer">
                        <button className="btn btn-secondary" onClick={handleCancel}>
                            Cancel Installation
                        </button>
                    </div>
                )}
            </div>
        </div>
    );
}

// ============================================================================
// SERVICE CONFIGURATION MODAL
// ============================================================================

function ConfigModal({ isOpen, onClose, service, onInstall }) {
    const [config, setConfig] = useState({});
    const [configSchema, setConfigSchema] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        if (isOpen && service) {
            fetchConfigSchema();
        }
    }, [isOpen, service]);

    const fetchConfigSchema = async () => {
        try {
            const response = await AuthFetch(`${API_URL}/services/${service.id}/config-schema`);
            const data = await response.json();
            setConfigSchema(data);
            
            // Set defaults
            const defaults = {};
            if (data.inputs) {
                data.inputs.forEach(input => {
                    defaults[input.name] = input.default || '';
                });
            }
            setConfig(defaults);
            setLoading(false);
        } catch (error) {
            console.error('Failed to fetch config schema:', error);
            setLoading(false);
        }
    };

    const handleSubmit = () => {
        onInstall(service.id, config);
        onClose();
    };

    if (!isOpen || !service) return null;

    return (
        <div className="modal">
            <div className="modal-content config-modal">
                <div className="modal-header">
                    <div>
                        <h2 className="modal-title">Configure {service.name}</h2>
                        <p style={{color: 'var(--text-dim)', marginTop: '4px', fontSize: '14px'}}>
                            This service requires configuration before installation
                        </p>
                    </div>
                    <button className="modal-close" onClick={onClose}>✕</button>
                </div>
                
                <div className="modal-body">
                    {loading ? (
                        <div style={{textAlign: 'center', padding: '40px'}}>
                            <div className="spinner"></div>
                            <p style={{marginTop: '16px', color: 'var(--text-dim)'}}>Loading configuration...</p>
                        </div>
                    ) : (
                        <div className="config-form">
                            {configSchema?.inputs?.map(input => (
                                <div key={input.name} className="config-field">
                                    <label className="config-label">
                                        {input.prompt || input.name}
                                        {input.required && <span style={{color: 'var(--error)'}}>*</span>}
                                    </label>
                                    <input
                                        type={input.type === 'password' ? 'password' : 'text'}
                                        className="config-input"
                                        value={config[input.name] || ''}
                                        onChange={(e) => setConfig({
                                            ...config,
                                            [input.name]: e.target.value
                                        })}
                                        placeholder={input.default || ''}
                                        required={input.required}
                                    />
                                    {input.description && (
                                        <p className="config-help">{input.description}</p>
                                    )}
                                </div>
                            ))}
                        </div>
                    )}
                </div>

                <div className="modal-footer">
                    <button className="btn btn-secondary" onClick={onClose}>
                        Cancel
                    </button>
                    <button 
                        className="btn btn-primary" 
                        onClick={handleSubmit}
                        disabled={loading}
                    >
                        Install with Configuration
                    </button>
                </div>
            </div>
        </div>
    );
}

// ============================================================================
// RESOURCE MANAGEMENT MODAL
// ============================================================================

function ResourceModal({ isOpen, onClose, service }) {
    const [loading, setLoading] = useState(true);
    const [resources, setResources] = useState(null);
    const [profiles, setProfiles] = useState({});
    const [selectedProfile, setSelectedProfile] = useState('small');
    const [customMode, setCustomMode] = useState(false);
    const [customValues, setCustomValues] = useState({
        cpu_cores: 1.0,
        memory_mb: 512,
        disk_mb: 5120,
        restart_policy: 'unless-stopped'
    });

    useEffect(() => {
        if (isOpen && service) {
            fetchResourceData();
        }
    }, [isOpen, service]);

    const fetchResourceData = async () => {
        setLoading(true);
        try {
            // Fetch profiles
            const profilesRes = await AuthFetch(`${API_URL}/resources/profiles`);
            const profilesData = await profilesRes.json();
            setProfiles(profilesData.profiles);

            // Fetch service resources
            const resourcesRes = await AuthFetch(`${API_URL}/services/${service.id}/resources`);
            const resourcesData = await resourcesRes.json();
            setResources(resourcesData);

            // Set current profile/values
            if (resourcesData.limits.custom) {
                setCustomMode(true);
                setCustomValues({
                    cpu_cores: resourcesData.limits.cpu_cores,
                    memory_mb: resourcesData.limits.memory_mb,
                    disk_mb: resourcesData.limits.disk_mb,
                    restart_policy: resourcesData.limits.restart_policy
                });
            } else {
                setSelectedProfile(resourcesData.limits.profile);
            }

            setLoading(false);
        } catch (error) {
            console.error('Failed to fetch resource data:', error);
            setLoading(false);
        }
    };

    const handleApply = async () => {
        try {
            const payload = customMode ? {
                cpu_cores: customValues.cpu_cores,
                memory_mb: customValues.memory_mb,
                disk_mb: customValues.disk_mb,
                restart_policy: customValues.restart_policy
            } : {
                profile: selectedProfile
            };

            // Set limits
            const setRes = await AuthFetch(`${API_URL}/services/${service.id}/resources`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            if (!setRes.ok) {
                const error = await setRes.json();
                throw new Error(error.error || 'Failed to update limits');
            }

            // Apply to running container if service is running
            if (service.status === 'running') {
                const applyRes = await AuthFetch(`${API_URL}/services/${service.id}/resources/apply`, {
                    method: 'POST'
                });

                if (!applyRes.ok) {
                    console.warn('Failed to apply to running container');
                }
            }

            onClose();
        } catch (error) {
            alert(`Error: ${error.message}`);
        }
    };

    if (!isOpen || !service) return null;

    return (
        <div className="modal">
            <div className="modal-content resource-modal">
                <div className="modal-header">
                    <div>
                        <h2 className="modal-title">Resource Management</h2>
                        <p style={{color: 'var(--text-dim)', marginTop: '4px', fontSize: '14px'}}>
                            {service.name}
                        </p>
                    </div>
                    <button className="modal-close" onClick={onClose}>✕</button>
                </div>

                <div className="modal-body">
                    {loading ? (
                        <div style={{textAlign: 'center', padding: '40px'}}>
                            <div className="spinner"></div>
                            <p style={{marginTop: '16px', color: 'var(--text-dim)'}}>Loading resource data...</p>
                        </div>
                    ) : (
                        <>
                            {/* Current Usage */}
                            {resources && resources.usage && (
                                <div className="resource-usage-section">
                                    <h3 style={{marginBottom: '12px', fontSize: '14px', fontWeight: 600}}>
                                        Current Usage
                                    </h3>
                                    <div className="resource-usage-grid">
                                        <div className="resource-usage-item">
                                            <div className="resource-usage-label">CPU</div>
                                            <div className="resource-usage-value">
                                                {resources.usage.cpu_percent.toFixed(1)}%
                                            </div>
                                        </div>
                                        <div className="resource-usage-item">
                                            <div className="resource-usage-label">Memory</div>
                                            <div className="resource-usage-value">
                                                {resources.usage.memory_mb.toFixed(0)} MB
                                            </div>
                                        </div>
                                        <div className="resource-usage-item">
                                            <div className="resource-usage-label">Disk</div>
                                            <div className="resource-usage-value">
                                                {resources.usage.disk_mb.toFixed(0)} MB
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            )}

                            {/* Profile Selection */}
                            <div className="resource-config-section">
                                <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px'}}>
                                    <h3 style={{fontSize: '14px', fontWeight: 600}}>Resource Limits</h3>
                                    <button
                                        onClick={() => setCustomMode(!customMode)}
                                        style={{
                                            background: 'none',
                                            border: '1px solid var(--border)',
                                            color: 'var(--text)',
                                            padding: '4px 12px',
                                            borderRadius: '4px',
                                            fontSize: '12px',
                                            cursor: 'pointer'
                                        }}
                                    >
                                        {customMode ? 'Use Profile' : 'Custom'}
                                    </button>
                                </div>

                                {!customMode ? (
                                    <div className="profile-selector">
                                        {Object.entries(profiles).map(([key, profile]) => (
                                            <div
                                                key={key}
                                                className={`profile-option ${selectedProfile === key ? 'selected' : ''}`}
                                                onClick={() => setSelectedProfile(key)}
                                            >
                                                <div className="profile-name">{key.toUpperCase()}</div>
                                                <div className="profile-specs">
                                                    <span>{profile.cpu_cores} CPU</span>
                                                    <span>{profile.memory_mb} MB</span>
                                                    <span>{(profile.disk_mb / 1024).toFixed(0)} GB</span>
                                                </div>
                                                <div className="profile-desc">{profile.description}</div>
                                            </div>
                                        ))}
                                    </div>
                                ) : (
                                    <div className="custom-limits">
                                        <div className="custom-limit-field">
                                            <label>CPU Cores</label>
                                            <input
                                                type="number"
                                                step="0.5"
                                                min="0.5"
                                                max="16"
                                                value={customValues.cpu_cores}
                                                onChange={(e) => setCustomValues({...customValues, cpu_cores: parseFloat(e.target.value)})}
                                                className="config-input"
                                            />
                                        </div>
                                        <div className="custom-limit-field">
                                            <label>Memory (MB)</label>
                                            <input
                                                type="number"
                                                step="128"
                                                min="128"
                                                max="16384"
                                                value={customValues.memory_mb}
                                                onChange={(e) => setCustomValues({...customValues, memory_mb: parseInt(e.target.value)})}
                                                className="config-input"
                                            />
                                        </div>
                                        <div className="custom-limit-field">
                                            <label>Disk Quota (MB)</label>
                                            <input
                                                type="number"
                                                step="1024"
                                                min="512"
                                                max="1048576"
                                                value={customValues.disk_mb}
                                                onChange={(e) => setCustomValues({...customValues, disk_mb: parseInt(e.target.value)})}
                                                className="config-input"
                                            />
                                        </div>
                                        <div className="custom-limit-field">
                                            <label>Restart Policy</label>
                                            <select
                                                value={customValues.restart_policy}
                                                onChange={(e) => setCustomValues({...customValues, restart_policy: e.target.value})}
                                                className="config-select"
                                            >
                                                <option value="no">No</option>
                                                <option value="on-failure">On Failure</option>
                                                <option value="always">Always</option>
                                                <option value="unless-stopped">Unless Stopped</option>
                                            </select>
                                        </div>
                                    </div>
                                )}
                            </div>
                        </>
                    )}
                </div>

                <div className="modal-footer">
                    <button className="btn btn-secondary" onClick={onClose}>
                        Cancel
                    </button>
                    <button className="btn btn-primary" onClick={handleApply} disabled={loading}>
                        Apply Limits
                    </button>
                </div>
            </div>
        </div>
    );
}

// ============================================================================
// METRICS CHART COMPONENT
// ============================================================================

function SimpleLineChart({ data, width = 400, height = 200, color = 'var(--accent)', label = '' }) {
    if (!data || data.length === 0) {
        return (
            <div style={{width, height, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-dim)'}}>
                No data
            </div>
        );
    }

    // Sort by timestamp
    const sortedData = [...data].sort((a, b) => a.timestamp - b.timestamp);
    
    // Calculate bounds
    const values = sortedData.map(d => d.value);
    const maxValue = Math.max(...values);
    const minValue = Math.min(...values);
    const range = maxValue - minValue || 1;
    
    // Padding
    const padding = 40;
    const chartWidth = width - padding * 2;
    const chartHeight = height - padding * 2;
    
    // Generate path
    const points = sortedData.map((d, i) => {
        const x = padding + (i / (sortedData.length - 1 || 1)) * chartWidth;
        const y = padding + chartHeight - ((d.value - minValue) / range) * chartHeight;
        return `${x},${y}`;
    });
    
    const path = `M ${points.join(' L ')}`;
    
    return (
        <div style={{position: 'relative'}}>
            <svg width={width} height={height}>
                {/* Grid lines */}
                <line x1={padding} y1={padding} x2={padding} y2={height - padding} stroke="var(--border)" strokeWidth="1" />
                <line x1={padding} y1={height - padding} x2={width - padding} y2={height - padding} stroke="var(--border)" strokeWidth="1" />
                
                {/* Data line */}
                <path d={path} fill="none" stroke={color} strokeWidth="2" />
                
                {/* Area fill */}
                <path
                    d={`${path} L ${width - padding},${height - padding} L ${padding},${height - padding} Z`}
                    fill={color}
                    fillOpacity="0.1"
                />
                
                {/* Labels */}
                <text x={padding} y={padding - 10} fontSize="12" fill="var(--text-dim)">{maxValue.toFixed(1)}</text>
                <text x={padding} y={height - padding + 20} fontSize="12" fill="var(--text-dim)">{minValue.toFixed(1)}</text>
            </svg>
            {label && (
                <div style={{textAlign: 'center', marginTop: '4px', fontSize: '12px', color: 'var(--text-dim)'}}>
                    {label}
                </div>
            )}
        </div>
    );
}

// ============================================================================
// METRICS MODAL COMPONENT
// ============================================================================

function MetricsModal({ isOpen, onClose, service }) {
    const [loading, setLoading] = useState(true);
    const [timeRange, setTimeRange] = useState(24); // hours
    const [metrics, setMetrics] = useState({
        cpu: [],
        memory: [],
        network_rx: [],
        network_tx: []
    });
    const [latest, setLatest] = useState({});

    useEffect(() => {
        if (isOpen && service) {
            fetchMetrics();
            const interval = setInterval(fetchMetrics, 30000); // Refresh every 30s
            return () => clearInterval(interval);
        }
    }, [isOpen, service, timeRange]);

    const fetchMetrics = async () => {
        setLoading(true);
        try {
            const baseUrl = service ? `${API_URL}/metrics/services/${service.id}` : `${API_URL}/metrics/system`;
            
            // Fetch latest
            const latestRes = await AuthFetch(`${baseUrl}/latest`);
            const latestData = await latestRes.json();
            setLatest(latestData.metrics);
            
            // Fetch historical data
            const metricNames = service 
                ? ['service_cpu_percent', 'service_memory_percent', 'service_network_rx_bytes_rate', 'service_network_tx_bytes_rate']
                : ['host_cpu_percent', 'host_memory_pct', 'host_disk_pct', 'host_disk_used_gb'];
            
            const [cpuRes, memRes, rxRes, txRes] = await Promise.all(
                metricNames.map(name => 
                    AuthFetch(`${baseUrl}/${name}?hours=${timeRange}&limit=100`)
                )
            );
            
            const [cpuData, memData, rxData, txData] = await Promise.all([
                cpuRes.json(),
                memRes.json(),
                rxRes.json(),
                txRes.json()
            ]);
            
            setMetrics({
                cpu: cpuData.data || [],
                memory: memData.data || [],
                extra1: rxData.data || [],   // disk_pct for system, net_rx for service
                extra2: txData.data || []    // disk_used_gb for system, net_tx for service
            });
            
            setLoading(false);
        } catch (error) {
            console.error('Failed to fetch metrics:', error);
            setLoading(false);
        }
    };

    if (!isOpen) return null;

    const formatBytes = (bytes) => {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return (bytes / Math.pow(k, i)).toFixed(2) + ' ' + sizes[i];
    };

    const formatBytesRate = (bytesPerSec) => {
        return formatBytes(bytesPerSec) + '/s';
    };

    return (
        <div className="modal">
            <div className="modal-content metrics-modal">
                <div className="modal-header">
                    <div>
                        <h2 className="modal-title">
                            {service ? `Metrics: ${service.name}` : 'System Metrics'}
                        </h2>
                        <p style={{color: 'var(--text-dim)', marginTop: '4px', fontSize: '14px'}}>
                            Real-time performance monitoring
                        </p>
                    </div>
                    <button className="modal-close" onClick={onClose}>✕</button>
                </div>

                <div className="modal-body">
                    {/* Time range selector */}
                    <div style={{display: 'flex', gap: '8px', marginBottom: '20px', justifyContent: 'center'}}>
                        {[1, 6, 24, 168].map(hours => (
                            <button
                                key={hours}
                                onClick={() => setTimeRange(hours)}
                                className={`time-range-btn ${timeRange === hours ? 'active' : ''}`}
                                style={{
                                    padding: '6px 12px',
                                    background: timeRange === hours ? 'var(--accent)' : 'var(--bg-secondary)',
                                    color: timeRange === hours ? 'var(--terminal-bg)' : 'var(--text)',
                                    border: '1px solid var(--border)',
                                    borderRadius: '4px',
                                    cursor: 'pointer',
                                    fontSize: '12px',
                                    fontWeight: 600
                                }}
                            >
                                {hours < 24 ? `${hours}h` : hours === 24 ? '1d' : '7d'}
                            </button>
                        ))}
                    </div>

                    {loading ? (
                        <div style={{textAlign: 'center', padding: '40px'}}>
                            <div className="spinner"></div>
                            <p style={{marginTop: '16px', color: 'var(--text-dim)'}}>Loading metrics...</p>
                        </div>
                    ) : (
                        <>
                            {/* Current stats */}
                            <div className="metrics-current">
                                <div className="metric-card">
                                    <div className="metric-label">CPU</div>
                                    <div className="metric-value">
                                        {(latest[service ? 'service_cpu_percent' : 'host_cpu_percent'] || 0).toFixed(1)}%
                                    </div>
                                </div>
                                <div className="metric-card">
                                    <div className="metric-label">Memory</div>
                                    <div className="metric-value">
                                        {(latest[service ? 'service_memory_mb' : 'host_memory_pct'] || 0).toFixed(1)}%
                                    </div>
                                </div>
                                {service && (
                                    <div className="metric-card">
                                        <div className="metric-label">Memory Usage</div>
                                        <div className="metric-value" style={{fontSize: '18px'}}>
                                            {((latest['service_memory_mb'] || 0).toFixed(0) + ' MB')}
                                        </div>
                                    </div>
                                )}
                            </div>

                            {/* Charts */}
                            <div className="metrics-charts">
                                <div className="metric-chart">
                                    <h4>CPU Usage</h4>
                                    <SimpleLineChart 
                                        data={metrics.cpu}
                                        width={600}
                                        height={150}
                                        color="var(--accent)"
                                        label="Percent"
                                    />
                                </div>

                                <div className="metric-chart">
                                    <h4>Memory Usage</h4>
                                    <SimpleLineChart 
                                        data={metrics.memory}
                                        width={600}
                                        height={150}
                                        color="#3b82f6"
                                        label="Percent"
                                    />
                                </div>

                                <div className="metric-chart">
                                    <h4>{service ? 'Network - Receive' : 'Disk Usage %'}</h4>
                                    <SimpleLineChart 
                                        data={metrics.extra1}
                                        width={600}
                                        height={150}
                                        color="#22c55e"
                                        label={service ? 'Bytes/sec' : '%'}
                                    />
                                </div>

                                <div className="metric-chart">
                                    <h4>{service ? 'Network - Transmit' : 'Disk Used (GB)'}</h4>
                                    <SimpleLineChart 
                                        data={metrics.extra2}
                                        width={600}
                                        height={150}
                                        color="#f59e0b"
                                        label={service ? 'Bytes/sec' : 'GB'}
                                    />
                                </div>
                            </div>
                        </>
                    )}
                </div>

                <div className="modal-footer">
                    <button className="btn btn-secondary" onClick={onClose}>
                        Close
                    </button>
                </div>
            </div>
        </div>
    );
}

// ============================================================================
// SETUP WIZARD COMPONENT
// ============================================================================

function SetupWizardModal({ isOpen, onClose, coreServices, services, onInstall, actionLoading }) {
    if (!isOpen) return null;

    const installedServices = services.filter(s => s.installed).map(s => s.id);
    const coreProgress = coreServices.map(core => ({
        ...core,
        installed: installedServices.includes(core.id)
    }));
    const installedCount = coreProgress.filter(c => c.installed).length;
    const isComplete = installedCount === coreServices.length;

    const handleDismiss = () => {
        sessionStorage.setItem('setup-wizard-dismissed', 'true');
        onClose();
    };

    return (
        <div className="modal">
            <div className="modal-content setup-wizard-modal">
                <div className="modal-header">
                    <div>
                        <h2 className="modal-title">Welcome to PSO</h2>
                        <p style={{color: 'var(--text-dim)', marginTop: '4px', fontSize: '14px'}}>
                            Let's set up your core infrastructure
                        </p>
                    </div>
                    <button className="modal-close" onClick={handleDismiss}>✕</button>
                </div>
                
                <div className="modal-body">
                    <div className="setup-progress">
                        <div className="setup-progress-bar">
                            <div 
                                className="setup-progress-fill" 
                                style={{width: `${(installedCount / coreServices.length) * 100}%`}}
                            />
                        </div>
                        <div className="setup-progress-text">
                            {installedCount} of {coreServices.length} core services installed
                        </div>
                    </div>

                    {!isComplete && (
                        <div className="setup-info">
                            <p>For best results, install these core services in order:</p>
                        </div>
                    )}

                    <div className="setup-services">
                        {coreProgress.map((core) => (
                            <div 
                                key={core.id} 
                                className={`setup-service-item ${core.installed ? 'installed' : ''}`}
                            >
                                <div className="setup-service-header">
                                    <div className="setup-service-number">
                                        {core.installed ? '✓' : core.order}
                                    </div>
                                    <div className="setup-service-info">
                                        <div className="setup-service-name">{core.name}</div>
                                        <div className="setup-service-reason">{core.reason}</div>
                                    </div>
                                </div>
                                {!core.installed && (
                                    <button 
                                        className="btn btn-primary"
                                        onClick={() => onInstall(core.id, 'install')}
                                        disabled={actionLoading[`${core.id}-install`]}
                                    >
                                        {actionLoading[`${core.id}-install`] ? (
                                            <>
                                                <div className="spinner"></div>
                                                Installing...
                                            </>
                                        ) : (
                                            'Install Now'
                                        )}
                                    </button>
                                )}
                                {core.installed && (
                                    <div className="setup-service-status">
                                        ✓ Installed
                                    </div>
                                )}
                            </div>
                        ))}
                    </div>

                    {isComplete && (
                        <div className="setup-complete">
                            <div className="setup-complete-icon">🎉</div>
                            <h3>Core Setup Complete!</h3>
                            <p>Your server infrastructure is ready. You can now install additional services.</p>
                        </div>
                    )}
                </div>

                <div className="modal-footer">
                    {!isComplete && (
                        <button className="btn btn-secondary" onClick={handleDismiss}>
                            I'll do this later
                        </button>
                    )}
                    {isComplete && (
                        <button className="btn btn-primary" onClick={onClose}>
                            Get Started
                        </button>
                    )}
                </div>
            </div>
        </div>
    );
}

function SetupBanner({ coreServices, services, onOpenWizard }) {
    const installedServices = services.filter(s => s.installed).map(s => s.id);
    const installedCount = coreServices.filter(core => installedServices.includes(core.id)).length;
    const isComplete = installedCount === coreServices.length;

    if (isComplete) return null;

    return (
        <div className="setup-banner">
            <div className="setup-banner-content">
                <div className="setup-banner-icon">⚠️</div>
                <div className="setup-banner-text">
                    <strong>Core Setup Incomplete</strong>
                    <span>{installedCount} of {coreServices.length} essential services installed</span>
                </div>
            </div>
            <button className="btn btn-primary" onClick={onOpenWizard}>
                Complete Setup
            </button>
        </div>
    );
}


// ============================================================================
// ORIGINAL APP CODE
// ============================================================================

const { useState, useEffect, useRef, useCallback, useMemo } = React;

const API_URL = 'http://localhost:5000/api';

function App() {
    const [services, setServices] = useState([]);
    const [stats, setStats] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [theme, setTheme] = useState(localStorage.getItem('pso-theme') || 'cyber');
    const [searchQuery, setSearchQuery] = useState('');
    const [toasts, setToasts] = useState([]);
    const [logsModal, setLogsModal] = useState({ open: false, serviceId: null, logs: '' });
    const [actionLoading, setActionLoading] = useState({});
    const [viewMode, setViewMode] = useState(localStorage.getItem('pso-view-mode') || 'all');
    const [showLogViewer, setShowLogViewer] = useState(false);
    const [showActivityLog, setShowActivityLog] = useState(false);
    const [showUpdateModal, setShowUpdateModal] = useState(false);
    const [showBackupModal, setShowBackupModal] = useState(false);
    const [selectedService, setSelectedService] = useState(null);
    const [showSetupWizard, setShowSetupWizard] = useState(false);
    const [showConfigModal, setShowConfigModal] = useState(false);
    const [serviceToConfig, setServiceToConfig] = useState(null);
    const [installProgress, setInstallProgress] = useState({ 
        isOpen: false, 
        serviceId: null, 
        serviceName: null 
    });
    const [showResourceModal, setShowResourceModal] = useState(false);
    const [resourceService, setResourceService] = useState(null);
    const [showMetricsModal, setShowMetricsModal] = useState(false);
    const [metricsService, setMetricsService] = useState(null);

// Core services that should be installed first (best practice)
const CORE_SERVICES = [
    { id: 'nginx', order: 1, name: 'Nginx', reason: 'Reverse proxy for SSL/TLS and subdomain routing' },
    { id: 'vaultwarden', order: 2, name: 'Vaultwarden', reason: 'Secure password manager for all credentials' },
    { id: 'portainer', order: 3, name: 'Portainer', reason: 'Docker container management interface' },
    { id: 'uptime-kuma', order: 4, name: 'Uptime Kuma', reason: 'Service monitoring and uptime tracking' }
];

    useEffect(() => {
        document.documentElement.setAttribute('data-theme', theme);
        localStorage.setItem('pso-theme', theme);
    }, [theme]);

    useEffect(() => {
        localStorage.setItem('pso-view-mode', viewMode);
    }, [viewMode]);

    // Keyboard shortcuts
    useEffect(() => {
        const handleKeyPress = (e) => {
            if (e.key === 'Escape' && logsModal.open) {
                setLogsModal({ open: false, serviceId: null, logs: '' });
            }
            if (e.key === '/' && e.ctrlKey) {
                e.preventDefault();
                document.querySelector('.search-input')?.focus();
            }
        };
        window.addEventListener('keydown', handleKeyPress);
        return () => window.removeEventListener('keydown', handleKeyPress);
    }, [logsModal.open]);

    useEffect(() => {
        fetchData();
        const interval = setInterval(fetchData, 30000);
        return () => clearInterval(interval);
    }, []);

    useEffect(() => {
        if (services.length > 0) {
            const installedServices = services.filter(s => s.installed).map(s => s.id);
            const coreInstalled = CORE_SERVICES.filter(core => installedServices.includes(core.id));
            const setupComplete = coreInstalled.length === CORE_SERVICES.length;
        
        if (!setupComplete && !sessionStorage.getItem('setup-wizard-dismissed')) {
            setShowSetupWizard(true);
            }
        }
    }, [services]);

    const fetchData = async () => {
        try {
            const [servicesRes, statsRes] = await Promise.all([
                AuthFetch(`${API_URL}/services`),
                AuthFetch(`${API_URL}/system/stats`)
            ]);
            
            const servicesData = await servicesRes.json();
            const statsData = await statsRes.json();
            
            setServices(servicesData.services || []);
            setStats(statsData);
            setLoading(false);
        } catch (err) {
            console.error('Fetch error:', err);
            setError(err.message);
            setLoading(false);
        }
    };

    const showToast = (message, type = 'success') => {
        const id = Date.now();
        setToasts(prev => [...prev, { id, message, type }]);
        setTimeout(() => {
            setToasts(prev => prev.filter(t => t.id !== id));
        }, 4000);
    };
    window.showToast = showToast;
    window.AuthFetch = AuthFetch;

    const handleAction = async (serviceId, action, config = null) => {
    // Confirmation dialog for uninstall
    if (action === 'uninstall') {
        const service = services.find(s => s.id === serviceId);
        const serviceName = service ? service.name : serviceId;

        const confirmMessage = `⚠️ UNINSTALL ${serviceName.toUpperCase()}?\n\n` +
            `This will permanently delete:\n` +
            `• Docker container\n` +
            `• All volumes and data\n` +
            `• Network configuration\n` +
            `• Database entries\n` +
            `• Service secrets\n\n` +
            `This action CANNOT be undone!\n\n` +
            `Type "${serviceName}" to confirm:`;

        const userInput = prompt(confirmMessage);

        if (userInput !== serviceName) {
            showToast('Uninstall cancelled', 'info');
            return;
        }
    }

    setActionLoading(prev => ({ ...prev, [`${serviceId}-${action}`]: true }));

    try {
        // Special handling for install action
        if (action === 'install') {
            let userConfig = {};  // ← Declare here, outside the if blocks
            
            // First check if service needs configuration
            if (!config) {
                // Handle configuration if needed
                const configResponse = await AuthFetch(`${API_URL}/services/${serviceId}/config-schema`);
                const configData = await configResponse.json();

                if (configData.needs_config && configData.inputs.length > 0) {
                    // Show configuration modal (userConfig already declared above)
                    
                    for (const input of configData.inputs) {
                        let value;
                        
                        // Build prompt text with help
                        let promptText = input.prompt;
                        if (input.help) {
                            promptText += `\n\nℹ️ ${input.help}`;
                        }
                        
                        // Handle different input types
                        if (input.type === 'choice' && input.options) {
                            // For choice type, show options
                            promptText += `\n\nOptions: ${input.options.join(', ')}`;
                            value = prompt(promptText, input.default);
                            
                            // Validate choice
                            if (value && !input.options.includes(value)) {
                                showToast(`Invalid choice. Please select one of: ${input.options.join(', ')}`, 'error');
                                return;
                            }
                        } else if (input.type === 'bool') {
                            // Handle old-style boolean (for compatibility)
                            const defaultValue = input.default ? 'yes' : 'no';
                            promptText += '\n\nEnter: yes or no';
                            value = prompt(promptText, defaultValue);
                            
                            // Convert to boolean for backend
                            value = value?.toLowerCase() === 'yes';
                        } else {
                            // Regular text input (domain, string, etc)
                            value = prompt(promptText, input.default);
                        }
                        
                        // Check if user cancelled
                        if (value === null) {
                            showToast('Installation cancelled', 'error');
                            return;
                        }
                        
                        userConfig[input.name] = value;
                    }
                    
                    config = userConfig;
                }
            }
            
            // Get service name for progress modal
            const service = services.find(s => s.id === serviceId);
            const serviceName = service ? service.name : serviceId;
            
            // Show progress modal
            setInstallProgress({
                isOpen: true,
                serviceId: serviceId,
                serviceName: serviceName
            });
            
            // Install with config if provided
            const response = await AuthFetch(`${API_URL}/services/${serviceId}/${action}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ configuration: userConfig || config || {} })
            });
            
            const data = await response.json();
            
            if (response.ok) {
                // Progress modal will handle success display
                fetchData();
            } else {
                showToast(data.error || `Failed to ${action} ${serviceId}`, 'error');
                setInstallProgress({ isOpen: false, serviceId: null, serviceName: null });
            }
        } else {
            // Other actions (start, stop, restart, etc.)
            const response = await AuthFetch(`${API_URL}/services/${serviceId}/${action}`, {
                method: 'POST'
            });
            
            const data = await response.json();
            
            if (response.ok) {
                showToast(`${serviceId} ${action} successful!`, 'success');
                // Give Docker a moment to update status before refreshing
                if (action === 'uninstall') {
                    await new Promise(r => setTimeout(r, 800));
                } else if (action === 'start' || action === 'stop' || action === 'restart') {
                    await new Promise(r => setTimeout(r, 500));
                }
                fetchData();
            } else {
                console.error(`${action} failed:`, data);
                showToast(data.error || `Failed to ${action} ${serviceId}`, 'error');
            }
        }
    } catch (err) {
        console.error('Action error:', err);
        showToast(`Error: ${err.message}`, 'error');
        if (action === 'install') {
            setInstallProgress({ isOpen: false, serviceId: null, serviceName: null });
        }
    } finally {
        setActionLoading(prev => ({ ...prev, [`${serviceId}-${action}`]: false }));
    }
};

    const showLogs = async (serviceId) => {
        setLogsModal({ open: true, serviceId, logs: 'Loading logs...' });
        try {
            const res = await AuthFetch(`${API_URL}/services/${serviceId}/logs?lines=200`);
            const data = await res.json();
            setLogsModal({ open: true, serviceId, logs: data.logs || 'No logs available' });
        } catch (err) {
            setLogsModal({ open: true, serviceId, logs: `Error loading logs: ${err.message}` });
        }
    };

    if (loading) return <div className="container"><div className="loading">LOADING CONTROL PANEL</div></div>;
    if (error) return <div className="container"><div className="loading">ERROR: {error}</div></div>;

    const installedServices = services.filter(s => s.installed);
    const availableServices = services.filter(s => !s.installed);
    
    const filteredInstalled = installedServices.filter(s => 
        s.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        s.description.toLowerCase().includes(searchQuery.toLowerCase()) ||
        s.category.toLowerCase().includes(searchQuery.toLowerCase())
    );
    
    const filteredAvailable = availableServices.filter(s =>
        s.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        s.description.toLowerCase().includes(searchQuery.toLowerCase()) ||
        s.category.toLowerCase().includes(searchQuery.toLowerCase())
    );
    
    const runningCount = installedServices.filter(s => s.status === 'running').length;

    // Group services by category
    const groupByCategory = (serviceList) => {
        const grouped = {};
        serviceList.forEach(service => {
            const category = service.category || 'Uncategorized';
            if (!grouped[category]) {
                grouped[category] = [];
            }
            grouped[category].push(service);
        });
        return grouped;
    };

    return (
        <>
            <SetupWizardModal
            isOpen={showSetupWizard}
            onClose={() => setShowSetupWizard(false)}
            coreServices={CORE_SERVICES}
            services={services}
            onInstall={handleAction}
            actionLoading={actionLoading}
            />

            {/* Resource Management Modal */}
            <ResourceModal
                isOpen={showResourceModal}
                onClose={() => {
                    setShowResourceModal(false);
                    setResourceService(null);
                }}
                service={resourceService}
            />

            {/* Metrics Modal */}
            <MetricsModal
                isOpen={showMetricsModal}
                onClose={() => {
                    setShowMetricsModal(false);
                    setMetricsService(null);
                }}
                service={metricsService}
            />

            {/* Configuration Modal */}
            <ConfigModal
            isOpen={showConfigModal}
            onClose={() => {
                setShowConfigModal(false);
                setServiceToConfig(null);
            }}
            service={serviceToConfig}
            onInstall={(serviceId, config) => {
                handleAction(serviceId, 'install', config);
            }}
        />

            {/* Installation Progress Modal */}
            <InstallProgressModal
                serviceId={installProgress.serviceId}
                serviceName={installProgress.serviceName}
                isOpen={installProgress.isOpen}
                onClose={() => {
                    setInstallProgress({ isOpen: false, serviceId: null, serviceName: null });
                    fetchData();
                }}
                onCancel={() => {
                    setInstallProgress({ isOpen: false, serviceId: null, serviceName: null });
                }}
            />

            <div className="toast-container">
                {toasts.map(toast => (
                    <div key={toast.id} className={`toast ${toast.type}`}>
                        {toast.message}
                    </div>
                ))}
            </div>

            {logsModal.open && (
                <div className="modal" onClick={() => setLogsModal({ open: false, serviceId: null, logs: '' })}>
                    <div className="modal-content" onClick={(e) => e.stopPropagation()}>
                        <div className="modal-header">
                            <div className="modal-title">LOGS: {logsModal.serviceId}</div>
                            <button className="modal-close" onClick={() => setLogsModal({ open: false, serviceId: null, logs: '' })}>
                                CLOSE [ESC]
                            </button>
                        </div>
                        <div className="modal-body">
                            <div className="logs-container">{logsModal.logs}</div>
                        </div>
                    </div>
                </div>
            )}

            <div className="container">
            <header className="header">
                <div className="header-title">
                    <div className="pso-logo">PSO</div>
                    <div>
                        <h1 style={{fontSize: '1.5rem', fontWeight: 600}}>Control Panel</h1>
                        <p style={{color: 'var(--text-dim)', fontSize: '0.9rem'}}>Personal Server OS Management</p>
                    </div>
                </div>
                <div style={{display: 'flex', gap: '1.5rem', alignItems: 'center'}}>
                    <div className="view-mode-selector">
                        <button
                            className={`view-btn ${viewMode === 'all' ? 'active' : ''}`}
                            onClick={() => setViewMode('all')}
                            title="All Services"
                        >
                            All
                        </button>
                        <button
                            className={`view-btn ${viewMode === 'installed' ? 'active' : ''}`}
                            onClick={() => setViewMode('installed')}
                            title="Installed Only"
                        >
                            Installed
                        </button>
                        <button
                            className={`view-btn ${viewMode === 'category' ? 'active' : ''}`}
                            onClick={() => setViewMode('category')}
                            title="Group by Category"
                        >
                            Categories
                        </button>
                    </div>
                    <div className="theme-switcher">
                        <button
                            className={`theme-btn cyber ${theme === 'cyber' ? 'active' : ''}`}
                            onClick={() => setTheme('cyber')}
                            title="Cyber Green"
                        />
                        <button
                            className={`theme-btn neon ${theme === 'neon' ? 'active' : ''}`}
                            onClick={() => setTheme('neon')}
                            title="Neon Blue"
                        />
                        <button
                            className={`theme-btn purple ${theme === 'purple' ? 'active' : ''}`}
                            onClick={() => setTheme('purple')}
                            title="Purple Haze"
                        />
                        <button
                            className={`theme-btn ember ${theme === 'ember' ? 'active' : ''}`}
                            onClick={() => setTheme('ember')}
                            title="Ember Orange"
                        />
                    </div>
                    {/* Setup Guide Button */}
                    <button
                        onClick={() => setShowSetupWizard(true)}
                        style={{
                            background: 'var(--bg-secondary)',
                            border: '1px solid var(--border)',
                            color: 'var(--text)',
                            padding: '8px 16px',
                            borderRadius: '6px',
                            cursor: 'pointer',
                            fontSize: '0.85rem',
                            fontWeight: 500,
                            fontFamily: 'JetBrains Mono',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '8px'
                        }}
                        onMouseOver={(e) => {
                            e.target.style.borderColor = 'var(--accent)';
                            e.target.style.color = 'var(--accent)';
                        }}
                        onMouseOut={(e) => {
                            e.target.style.borderColor = 'var(--border)';
                            e.target.style.color = 'var(--text)';
                        }}
                    >
                        <span style={{fontSize: '16px'}}></span>
                        SETUP GUIDE
                    </button>
                    <button
                        onClick={() => {
                            setMetricsService(null);
                            setShowMetricsModal(true);
                        }}
                        style={{
                            background: 'var(--bg-secondary)',
                            border: '1px solid var(--border)',
                            color: 'var(--text)',
                            padding: '8px 16px',
                            borderRadius: '6px',
                            cursor: 'pointer',
                            fontSize: '14px',
                            fontWeight: 500
                        }}
                    >
                        ⬡ System Metrics
                    </button>
                    <button
                        onClick={() => setShowActivityLog(!showActivityLog)}
                        style={{
                            background: showActivityLog ? 'var(--accent)' : 'var(--bg-secondary)',
                            border: `1px solid ${showActivityLog ? 'var(--accent)' : 'var(--border)'}`,
                            color: showActivityLog ? 'var(--bg-primary)' : 'var(--text)',
                            padding: '8px 16px',
                            borderRadius: '6px',
                            cursor: 'pointer',
                            fontSize: '14px',
                            fontWeight: 500,
                            fontFamily: 'JetBrains Mono',
                        }}
                        onMouseOver={e => { e.currentTarget.style.borderColor = 'var(--accent)'; e.currentTarget.style.color = 'var(--accent)'; }}
                        onMouseOut={e => { e.currentTarget.style.borderColor = 'var(--border)'; e.currentTarget.style.color = 'var(--text)'; }}
                    >
                        ▸ Activity Log
                    </button>
                    <div className="status-badge" style={{
                        borderColor: (() => {
                            const installed = services.filter(s => s.installed);
                            if (installed.length === 0) return 'var(--border)';
                            const unhealthy = installed.filter(s => s.status === 'error' || s.status === 'stopped');
                            if (unhealthy.length > 0) return 'var(--error)';
                            return 'var(--success)';
                        })()
                    }}>
                        <div className="status-dot" style={{
                            background: (() => {
                                const installed = services.filter(s => s.installed);
                                if (installed.length === 0) return 'var(--text-dim)';
                                const errored = installed.filter(s => s.status === 'error');
                                const stopped = installed.filter(s => s.status === 'stopped');
                                if (errored.length > 0) return 'var(--error)';
                                if (stopped.length > 0) return 'var(--warning)';
                                return 'var(--success)';
                            })()
                        }}></div>
                        <span>{(() => {
                            const installed = services.filter(s => s.installed);
                            if (installed.length === 0) return 'NO SERVICES';
                            const errored = installed.filter(s => s.status === 'error');
                            const stopped = installed.filter(s => s.status === 'stopped');
                            if (errored.length > 0) return `${errored.length} ERROR${errored.length > 1 ? 'S' : ''}`;
                            if (stopped.length > 0) return `${stopped.length} STOPPED`;
                            return 'ALL OPERATIONAL';
                        })()}</span>
                    </div>
                    <button
                        onClick={() => {
                            const token = localStorage.getItem('pso_token');
                            if (token) {
                                fetch(`${API_URL}/auth/logout`, {
                                    method: 'POST',
                                    headers: { 'Authorization': `Bearer ${token}` }
                                }).finally(() => {
                                    localStorage.removeItem('pso_token');
                                    localStorage.removeItem('pso_user');
                                    window.location.href = '/login';
                                });
                            } else {
                                window.location.href = '/login';
                            }
                        }}
                        style={{
                            background: 'var(--bg-secondary)',
                            border: '1px solid var(--border)',
                            color: 'var(--text)',
                            padding: '8px 16px',
                            borderRadius: '6px',
                            cursor: 'pointer',
                            fontSize: '14px',
                            fontWeight: 500
                        }}
                    >
                        ⎋ Logout
                    </button>
                </div>
            </header>

            <div className="stats-bar">
                <div className="stat-card">
                    <div className="stat-value">{installedServices.length}</div>
                    <div className="stat-label">Installed Services</div>
                </div>
                <div className="stat-card">
                    <div className="stat-value">{runningCount}</div>
                    <div className="stat-label">Running</div>
                </div>
                <div className="stat-card">
                    <div className="stat-value">{availableServices.length}</div>
                    <div className="stat-label">Available to Install</div>
                </div>
            </div>


            <div className="search-bar">
                <svg className="search-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <circle cx="11" cy="11" r="8"/>
                    <path d="m21 21-4.35-4.35"/>
                </svg>
                <input 
                    type="text"
                    className="search-input"
                    placeholder="Search services... (Ctrl+/)"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                />
            </div>

            {/* Bulk Actions Bar */}
            {filteredInstalled.length > 0 && (
                <div className="bulk-actions-bar">
                    <button
                        className="btn btn-bulk btn-success"
                        onClick={async () => {
                            if (confirm('Start all stopped services?')) {
                                try {
                                    const res = await AuthFetch(`${API_URL}/services/bulk/start-all`, { method: 'POST' });
                                    const data = await res.json();
                                    showToast(`Started ${data.count} service(s)`, 'success');
                                    // Wait for containers to start
                                    await new Promise(r => setTimeout(r, 1000));
                                    fetchData();
                                } catch (e) {
                                    showToast(`Error: ${e.message}`, 'error');
                                }
                            }
                        }}
                    >
                        ▶ Start All Stopped
                    </button>
                    <button
                        className="btn btn-bulk btn-warning"
                        onClick={async () => {
                            if (confirm('Stop all running services?')) {
                                try {
                                    const res = await AuthFetch(`${API_URL}/services/bulk/stop-all`, { method: 'POST' });
                                    const data = await res.json();
                                    showToast(`Stopped ${data.count} service(s)`, 'success');
                                    // Wait for containers to stop
                                    await new Promise(r => setTimeout(r, 1000));
                                    fetchData();
                                } catch (e) {
                                    showToast(`Error: ${e.message}`, 'error');
                                }
                            }
                        }}
                    >
                        ■ Stop All Running
                    </button>
                    <div className="bulk-actions-spacer"></div>
                    <div className="service-count-badge">
                        {runningCount} Running · {filteredInstalled.length - runningCount} Stopped
                    </div>
                </div>
            )}

            {/* View Mode: All (default - installed and available separate) */}
            {viewMode === 'all' && (
                <>
                    {filteredInstalled.length > 0 && (
                        <>
                            <div className="category-header">INSTALLED SERVICES</div>
                            <div className="services-grid">
                                {filteredInstalled.map(service => (
                                    <ServiceCard 
                                        key={service.id}
                                        service={service}
                                        onAction={handleAction}
                                        onShowLogs={showLogs}
                                        installed={true}
                                        actionLoading={actionLoading}
                                        onOpenLogViewer={(svc) => {
                                            setSelectedService(svc);
                                            setShowLogViewer(true);
                                        }}
                                        onOpenUpdateModal={(svc) => {
                                            setSelectedService(svc);
                                            setShowUpdateModal(true);
                                        }}
                                        onOpenBackupModal={(svc) => {
                                            setSelectedService(svc);
                                            setShowBackupModal(true);
                                        }}
                                        onOpenResourceModal={(svc) => {
                                            setResourceService(svc);
                                            setShowResourceModal(true);
                                        }}
                                        onOpenMetricsModal={(svc) => {
                                            setMetricsService(svc);
                                            setShowMetricsModal(true);
                                        }}
                                    />
                                ))}
                            </div>
                        </>
                    )}

                    <div className="accent-line"></div>

                    {filteredAvailable.length > 0 && (
                        <>
                            <div className="category-header">AVAILABLE SERVICES</div>
                            <div className="services-grid">
                                {filteredAvailable.map(service => (
                                    <ServiceCard 
                                        key={service.id}
                                        service={service}
                                        onAction={handleAction}
                                        onShowLogs={showLogs}
                                        installed={false}
                                        actionLoading={actionLoading}
                                        onOpenLogViewer={(svc) => {
                                            setSelectedService(svc);
                                            setShowLogViewer(true);
                                        }}
                                        onOpenUpdateModal={(svc) => {
                                            setSelectedService(svc);
                                            setShowUpdateModal(true);
                                        }}
                                        onOpenBackupModal={(svc) => {
                                            setSelectedService(svc);
                                            setShowBackupModal(true);
                                        }}
                                        onOpenResourceModal={(svc) => {
                                            setResourceService(svc);
                                            setShowResourceModal(true);
                                        }}
                                        onOpenMetricsModal={(svc) => {
                                            setMetricsService(svc);
                                            setShowMetricsModal(true);
                                        }}
                                    />
                                ))}
                            </div>
                        </>
                    )}
                </>
            )}

            {/* View Mode: Installed Only */}
            {viewMode === 'installed' && (
                <>
                    {filteredInstalled.length > 0 ? (
                        <>
                            <div className="category-header">INSTALLED SERVICES ({filteredInstalled.length})</div>
                            <div className="services-grid">
                                {filteredInstalled.map(service => (
                                    <ServiceCard 
                                        key={service.id}
                                        service={service}
                                        onAction={handleAction}
                                        onShowLogs={showLogs}
                                        installed={true}
                                        actionLoading={actionLoading}
                                        onOpenLogViewer={(svc) => {
                                            setSelectedService(svc);
                                            setShowLogViewer(true);
                                        }}
                                        onOpenUpdateModal={(svc) => {
                                            setSelectedService(svc);
                                            setShowUpdateModal(true);
                                        }}
                                        onOpenBackupModal={(svc) => {
                                            setSelectedService(svc);
                                            setShowBackupModal(true);
                                        }}
                                        onOpenResourceModal={(svc) => {
                                            setResourceService(svc);
                                            setShowResourceModal(true);
                                        }}
                                        onOpenMetricsModal={(svc) => {
                                            setMetricsService(svc);
                                            setShowMetricsModal(true);
                                        }}
                                    />
                                ))}
                            </div>
                        </>
                    ) : (
                        <div style={{textAlign: 'center', padding: '4rem', color: 'var(--text-dim)'}}>
                            No installed services yet. Switch to "All" view to install services.
                        </div>
                    )}
                </>
            )}

            {/* View Mode: By Category */}
            {viewMode === 'category' && (
                <>
                    {Object.entries(groupByCategory([...filteredInstalled, ...filteredAvailable]))
                        .sort(([a], [b]) => a.localeCompare(b))
                        .map(([category, categoryServices]) => (
                            <div key={category}>
                                <div className="category-header">{category.toUpperCase()}</div>
                                <div className="services-grid">
                                    {categoryServices.map(service => (
                                        <ServiceCard 
                                            key={service.id}
                                            service={service}
                                            onAction={handleAction}
                                            onShowLogs={showLogs}
                                            installed={service.installed}
                                            actionLoading={actionLoading}
                                            onOpenLogViewer={(svc) => {
                                                setSelectedService(svc);
                                                setShowLogViewer(true);
                                            }}
                                            onOpenUpdateModal={(svc) => {
                                                setSelectedService(svc);
                                                setShowUpdateModal(true);
                                            }}
                                            onOpenBackupModal={(svc) => {
                                                setSelectedService(svc);
                                                setShowBackupModal(true);
                                            }}
                                            onOpenResourceModal={(svc) => {
                                                setResourceService(svc);
                                                setShowResourceModal(true);
                                            }}
                                            onOpenMetricsModal={(svc) => {
                                                setMetricsService(svc);
                                                setShowMetricsModal(true);
                                            }}
                                        />
                                    ))}
                                </div>
                                <div className="accent-line"></div>
                            </div>
                        ))}
                </>
            )}

            <footer className="footer">

            {showLogViewer && selectedService && (
                <LogViewerModal
                    service={selectedService}
                    onClose={() => {
                        setShowLogViewer(false);
                        setSelectedService(null);
                    }}
                />
            )}

            <SystemActivityLog
                isOpen={showActivityLog}
                onClose={() => setShowActivityLog(false)}
            />

            {showUpdateModal && selectedService && (
                <UpdateManagerModal
                    service={selectedService}
                    onClose={() => {
                        setShowUpdateModal(false);
                        setSelectedService(null);
                    }}
                    onUpdate={fetchData}
                />
            )}

            {showBackupModal && selectedService && (
                <BackupManagerModal
                    service={selectedService}
                    onClose={() => {
                        setShowBackupModal(false);
                        setSelectedService(null);
                    }}
                />
            )}

                <div className="footer-info">
                    <span style={{color: 'var(--text-dim)', fontSize: '0.9rem'}}>
                        Personal Server OS • {new Date().getFullYear()}
                    </span>
                </div>
            </footer>
        </div>
        </>
    );
}

function ServiceCard({ service, onAction, onShowLogs, installed, actionLoading, onOpenLogViewer, onOpenUpdateModal, onOpenBackupModal, onOpenResourceModal, onOpenMetricsModal }) {
    const [showDescription, setShowDescription] = useState(false);
    const [showPopover, setShowPopover] = useState(false);

    const getPrimaryPort = () => {
        if (!service.ports) return null;
        const portEntry = Object.entries(service.ports)[0];
        return portEntry ? portEntry[1] : null;
    };

    const isRecommended = service.metadata?.priority && service.metadata.priority <= 2;
    const isEssential = service.metadata?.tags?.includes('essential-for-production');
    const port = getPrimaryPort();
    const isLoading = (action) => actionLoading[`${service.id}-${action}`];
    const isRunning = service.status === 'running';

    return (
        <div className="service-card" onClick={() => showPopover && setShowPopover(false)}>

            {(isRecommended || isEssential) && (
                <div className={`priority-badge ${isEssential ? 'essential' : 'recommended'}`}>
                    {isEssential ? '⚡ Essential' : '★ Recommended'}
                </div>
            )}

            {/* Category above logo */}
            <div className="service-category-header">
                <span className="meta-category">{service.category}</span>
                {port && isRunning && (
                    <a href={`http://localhost:${port}`} target="_blank" rel="noopener noreferrer"
                        className="meta-port-inline" onClick={(e) => e.stopPropagation()}>
                        :{port} ↗
                    </a>
                )}
            </div>

            {/* Logo */}
            <div className="service-card-logo">
                {service.id && (
                    <img src={`/logos/${service.id}.svg`} alt="" className="service-logo"
                        onError={(e) => { e.target.style.display = 'none'; }} />
                )}
            </div>

            {/* Service info */}
            <div className="service-card-info">
                {/* Name + status dot inline */}
                <div className="service-name">
                    {installed && (
                        <span className={`status-dot ${isRunning ? 'running' : 'stopped'}`} title={isRunning ? 'Running' : 'Stopped'} />
                    )}
                    {service.name}
                    <button className="info-toggle"
                        onClick={(e) => { e.stopPropagation(); setShowDescription(!showDescription); }}
                        title={showDescription ? 'Hide' : 'About'}>ℹ</button>
                </div>
                {/* Version only */}
                <div className="service-meta">
                    <span>v{service.version}</span>
                </div>
            </div>

            {showDescription && (
                <div className="service-description">{service.description}</div>
            )}

            {(service.metadata?.website || service.metadata?.github_repo) && (
                <div className="service-links">
                    {service.metadata?.website && (
                        <a href={service.metadata.website} target="_blank" rel="noopener noreferrer" className="service-link">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                <circle cx="12" cy="12" r="10"/>
                                <line x1="2" y1="12" x2="22" y2="12"/>
                                <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
                            </svg>
                            Website
                        </a>
                    )}
                    {service.metadata?.github_repo && (
                        <a href={service.metadata.github_repo} target="_blank" rel="noopener noreferrer" className="service-link">
                            <svg viewBox="0 0 16 16" fill="currentColor">
                                <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"/>
                            </svg>
                            GitHub
                        </a>
                    )}
                </div>
            )}

            {/* Actions */}
            <div className="service-actions">
                {installed ? (
                    <div className="card-action-row" onClick={(e) => e.stopPropagation()}>

                        {/* Split button: primary action + ⋯ popover trigger */}
                        <div className="split-btn-group" style={{position: 'relative'}}>
                            {isRunning ? (
                                <button
                                    className={`split-btn split-btn-main split-btn-stop ${isLoading('stop') ? 'loading' : ''}`}
                                    onClick={() => onAction(service.id, 'stop')}
                                    disabled={isLoading('stop')}
                                >
                                    {isLoading('stop') ? <div className="spinner"></div> : '■ Stop'}
                                </button>
                            ) : (
                                <button
                                    className={`split-btn split-btn-main split-btn-start ${isLoading('start') ? 'loading' : ''}`}
                                    onClick={() => onAction(service.id, 'start')}
                                    disabled={isLoading('start')}
                                >
                                    {isLoading('start') ? <div className="spinner"></div> : '▶ Start'}
                                </button>
                            )}
                            <button
                                className="split-btn split-btn-chevron"
                                onClick={() => setShowPopover(p => !p)}
                                title="More options"
                            >⋯</button>

                            {/* Popover */}
                            {showPopover && (
                                <div className="card-popover">
                                    {isRunning && (
                                        <button className="popover-item"
                                            onClick={() => { onAction(service.id, 'restart'); setShowPopover(false); }}>
                                            <span className="popover-icon">↺</span> Restart
                                        </button>
                                    )}
                                    {isRunning && <div className="popover-divider" />}
                                    <button className="popover-item"
                                        onClick={() => { onShowLogs(service.id); setShowPopover(false); }}>
                                        <span className="popover-icon">≡</span> Logs
                                    </button>
                                    <button className="popover-item"
                                        onClick={() => { onOpenLogViewer && onOpenLogViewer(service); setShowPopover(false); }}>
                                        <span className="popover-icon">⬡</span> Advanced
                                    </button>
                                    <button className="popover-item"
                                        onClick={() => { onOpenUpdateModal && onOpenUpdateModal(service); setShowPopover(false); }}>
                                        <span className="popover-icon">↑</span> Updates
                                    </button>
                                    <button className="popover-item"
                                        onClick={() => { onOpenBackupModal && onOpenBackupModal(service); setShowPopover(false); }}>
                                        <span className="popover-icon">⊡</span> Backups
                                    </button>
                                    <button className="popover-item"
                                        onClick={() => { onOpenResourceModal && onOpenResourceModal(service); setShowPopover(false); }}>
                                        <span className="popover-icon">⚙</span> Resources
                                    </button>
                                    <button className="popover-item"
                                        onClick={() => { onOpenMetricsModal && onOpenMetricsModal(service); setShowPopover(false); }}>
                                        <span className="popover-icon">◈</span> Metrics
                                    </button>
                                </div>
                            )}
                        </div>

                        {/* Uninstall — right side, danger */}
                        <button
                            className={`btn btn-danger btn-sm-text ${isLoading('uninstall') ? 'loading' : ''}`}
                            onClick={() => onAction(service.id, 'uninstall')}
                            disabled={isLoading('uninstall')}
                        >
                            {isLoading('uninstall') ? <div className="spinner"></div> : 'Uninstall'}
                        </button>
                    </div>
                ) : (
                    <button
                        className={`btn btn-primary ${isLoading('install') ? 'loading' : ''}`}
                        onClick={(e) => { e.stopPropagation(); onAction(service.id, 'install'); }}
                        disabled={isLoading('install')}
                        style={{width: '100%'}}
                    >
                        {isLoading('install') && <div className="spinner"></div>}
                        Install
                    </button>
                )}
            </div>
        </div>
    );
}

ReactDOM.render(<App />, document.getElementById('root'));

// ============================================================================
// TIER UI COMPONENTS - INTEGRATED
// ============================================================================

function TierBadge({ tier }) {
    if (tier === null || tier === undefined) return null;
    
    const getTierInfo = (tierLevel) => {
        const tiers = {
            0: { label: 'T0', color: '#10b981', title: 'Tier 0: Internal Only' },
            1: { label: 'T1', color: '#f59e0b', title: 'Tier 1: LAN Only' },
            2: { label: 'T2', color: '#3b82f6', title: 'Tier 2: VPN Access' },
            3: { label: 'T3', color: '#ef4444', title: 'Tier 3: Internet Exposed' }
        };
        return tiers[tierLevel] || tiers[0];
    };

    const info = getTierInfo(tier);

    return (
        <div 
            className="tier-badge"
            style={{ 
                backgroundColor: `${info.color}20`,
                border: `1px solid ${info.color}`,
                color: info.color
            }}
            title={info.title}
        >
            {info.label}
        </div>
    );
}

function TierSelectorModal({ service, currentTier, onClose, onChangeTier }) {
    const [selectedTier, setSelectedTier] = useState(currentTier);
    const [showConfirmation, setShowConfirmation] = useState(false);
    const [loading, setLoading] = useState(false);

    const tiers = [
        {
            level: 0,
            name: 'Internal Only',
            description: 'Service binds to 127.0.0.1 - accessible only from this machine',
            color: '#10b981',
            risk: 'MINIMAL'
        },
        {
            level: 1,
            name: 'LAN Only',
            description: 'Accessible on home network only (192.168.x.x)',
            color: '#f59e0b',
            risk: 'LOW'
        },
        {
            level: 2,
            name: 'VPN Access',
            description: 'Accessible via VPN (Tailscale/WireGuard) only',
            color: '#3b82f6',
            risk: 'MEDIUM'
        },
        {
            level: 3,
            name: 'Internet Exposed',
            description: 'PUBLIC internet access - Rate limited to 100 requests/min per IP',
            color: '#ef4444',
            risk: 'HIGH'
        }
    ];

    const handleApply = async () => {
        if (selectedTier === 3 && !showConfirmation) {
            setShowConfirmation(true);
            return;
        }

        setLoading(true);
        const result = await onChangeTier(service.id, selectedTier, selectedTier === 3);
        setLoading(false);
        
        if (result && result.success) {
            onClose();
        }
    };

    return (
        <div className="modal-overlay" onClick={onClose}>
            <div className="modal-content tier-modal" onClick={e => e.stopPropagation()}>
                <div className="modal-header">
                    <h2>Security Tier - {service.name}</h2>
                    <button className="modal-close" onClick={onClose}>×</button>
                </div>

                <div className="modal-body">
                    {!showConfirmation ? (
                        <>
                            <p className="tier-current">
                                Current Tier: <strong>Tier {currentTier}</strong>
                            </p>

                            <div className="tier-options">
                                {tiers.map(tier => (
                                    <div
                                        key={tier.level}
                                        className={`tier-option ${selectedTier === tier.level ? 'selected' : ''}`}
                                        style={{ borderColor: tier.color }}
                                        onClick={() => setSelectedTier(tier.level)}
                                    >
                                        <div className="tier-option-header">
                                            <span className="tier-option-level">Tier {tier.level}</span>
                                            <span className="tier-option-name">{tier.name}</span>
                                        </div>
                                        <p className="tier-option-desc">{tier.description}</p>
                                        <div className="tier-option-risk" style={{ color: tier.color }}>
                                            Risk: {tier.risk}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </>
                    ) : (
                        <div className="tier-confirmation">
                            <div className="warning-banner">
                                <span className="warning-icon">⚠️</span>
                                <h3>WARNING: Internet Exposure</h3>
                            </div>
                            <p>
                                You are about to expose <strong>{service.name}</strong> to the PUBLIC INTERNET.
                            </p>
                            <p className="warning-text">This means:</p>
                            <ul className="warning-list">
                                <li>Anyone can access this service from anywhere in the world</li>
                                <li>Service will be visible to port scanners and bots</li>
                                <li>Rate limiting will be applied (100 requests/minute per IP)</li>
                                <li>SSL/TLS certificate is strongly recommended</li>
                                <li>Regular security updates are critical</li>
                            </ul>
                            <p className="warning-question">
                                Are you absolutely sure you want to do this?
                            </p>
                        </div>
                    )}
                </div>

                <div className="modal-footer">
                    {showConfirmation ? (
                        <>
                            <button className="btn-secondary" onClick={() => setShowConfirmation(false)} disabled={loading}>
                                Go Back
                            </button>
                            <button className="btn-danger" onClick={handleApply} disabled={loading}>
                                {loading ? 'Applying...' : 'Yes, Expose to Internet'}
                            </button>
                        </>
                    ) : (
                        <>
                            <button className="btn-secondary" onClick={onClose} disabled={loading}>
                                Cancel
                            </button>
                            <button 
                                className="btn-primary" 
                                onClick={handleApply}
                                disabled={selectedTier === currentTier || loading}
                            >
                                {loading ? 'Applying...' : `Apply Tier ${selectedTier}`}
                            </button>
                        </>
                    )}
                </div>
            </div>
        </div>
    );
}

// ============================================================================
// ENHANCED DASHBOARD COMPONENTS
// ============================================================================

// ============================================================================
// SYSTEM ACTIVITY LOG PANEL
// ============================================================================

function SystemActivityLog({ isOpen, onClose }) {
    const [entries, setEntries] = React.useState([]);
    const [paused, setPaused] = React.useState(false);
    const [filter, setFilter] = React.useState('ALL');
    const bottomRef = React.useRef(null);
    const sinceRef = React.useRef(0);

    // Poll /api/logs every second
    React.useEffect(() => {
        if (!isOpen) return;
        let cancelled = false;

        const poll = async () => {
            if (paused || cancelled) return;
            try {
                const res = await AuthFetch(`${API_URL}/logs?since=${sinceRef.current}`);
                if (!res.ok) return;
                const data = await res.json();
                if (data.logs && data.logs.length > 0) {
                    sinceRef.current = data.total;
                    setEntries(prev => [...prev, ...data.logs].slice(-500));
                }
            } catch (_) {}
        };

        poll();
        const interval = setInterval(poll, 1000);
        return () => { cancelled = true; clearInterval(interval); };
    }, [isOpen, paused]);

    // Auto-scroll to bottom
    React.useEffect(() => {
        if (!paused && bottomRef.current) {
            bottomRef.current.scrollIntoView({ behavior: 'smooth' });
        }
    }, [entries, paused]);

    const levelColor = {
        INFO:    'var(--accent)',
        WARNING: '#f59e0b',
        ERROR:   '#ef4444',
        DEBUG:   'var(--text-dim)',
    };

    const filtered = filter === 'ALL' ? entries
        : entries.filter(e => e.level === filter);

    if (!isOpen) return null;

    return (
        <div style={{
            position: 'fixed', inset: 0, zIndex: 1000,
            display: 'flex', justifyContent: 'flex-end',
        }}>
            {/* Backdrop */}
            <div
                onClick={onClose}
                style={{ position: 'absolute', inset: 0, background: 'rgba(0,0,0,0.5)' }}
            />
            {/* Drawer */}
            <div style={{
                position: 'relative', zIndex: 1,
                width: 'min(680px, 95vw)', height: '100vh',
                background: 'var(--bg-primary)',
                borderLeft: '1px solid var(--border)',
                display: 'flex', flexDirection: 'column',
                fontFamily: 'JetBrains Mono',
            }}>
                {/* Header */}
                <div style={{
                    padding: '16px 20px',
                    borderBottom: '1px solid var(--border)',
                    display: 'flex', alignItems: 'center', gap: '12px',
                }}>
                    <span style={{ color: 'var(--accent)', fontSize: '1.1rem' }}>⬡</span>
                    <span style={{ fontWeight: 600, flex: 1 }}>System Activity Log</span>

                    {/* Level filter */}
                    <div style={{ display: 'flex', gap: '6px' }}>
                        {['ALL','INFO','WARNING','ERROR'].map(l => (
                            <button key={l} onClick={() => setFilter(l)} style={{
                                padding: '3px 8px', fontSize: '0.72rem',
                                borderRadius: '4px', cursor: 'pointer',
                                fontFamily: 'JetBrains Mono',
                                background: filter === l ? 'var(--accent)' : 'var(--bg-secondary)',
                                color: filter === l ? 'var(--bg-primary)' : 'var(--text-dim)',
                                border: '1px solid var(--border)',
                            }}>{l}</button>
                        ))}
                    </div>

                    <button onClick={() => setPaused(p => !p)} style={{
                        padding: '4px 10px', fontSize: '0.75rem',
                        borderRadius: '4px', cursor: 'pointer',
                        fontFamily: 'JetBrains Mono',
                        background: paused ? '#f59e0b22' : 'var(--bg-secondary)',
                        color: paused ? '#f59e0b' : 'var(--text-dim)',
                        border: `1px solid ${paused ? '#f59e0b' : 'var(--border)'}`,
                    }}>{paused ? '▶ Resume' : '⏸ Pause'}</button>

                    <button onClick={() => setEntries([])} style={{
                        padding: '4px 10px', fontSize: '0.75rem',
                        borderRadius: '4px', cursor: 'pointer',
                        fontFamily: 'JetBrains Mono',
                        background: 'var(--bg-secondary)',
                        color: 'var(--text-dim)',
                        border: '1px solid var(--border)',
                    }}>Clear</button>

                    <button onClick={onClose} style={{
                        background: 'none', border: 'none',
                        color: 'var(--text-dim)', cursor: 'pointer',
                        fontSize: '1.2rem', lineHeight: 1,
                    }}>✕</button>
                </div>

                {/* Log entries */}
                <div style={{
                    flex: 1, overflowY: 'auto',
                    padding: '12px 16px',
                    fontSize: '0.78rem', lineHeight: '1.7',
                }}>
                    {filtered.length === 0 ? (
                        <div style={{ color: 'var(--text-dim)', padding: '20px 0' }}>
                            {entries.length === 0
                                ? 'Waiting for activity...'
                                : 'No entries match the current filter.'}
                        </div>
                    ) : filtered.map((e, i) => (
                        <div key={i} style={{
                            display: 'flex', gap: '12px',
                            padding: '2px 0',
                            borderBottom: '1px solid var(--border)10',
                        }}>
                            <span style={{ color: 'var(--text-dim)', flexShrink: 0 }}>{e.ts}</span>
                            <span style={{
                                color: levelColor[e.level] || 'var(--text)',
                                flexShrink: 0, width: '56px',
                            }}>{e.level}</span>
                            <span style={{ color: 'var(--text)', wordBreak: 'break-all' }}>{e.message}</span>
                        </div>
                    ))}
                    <div ref={bottomRef} />
                </div>

                {/* Footer */}
                <div style={{
                    padding: '8px 16px',
                    borderTop: '1px solid var(--border)',
                    fontSize: '0.72rem', color: 'var(--text-dim)',
                    display: 'flex', justifyContent: 'space-between',
                }}>
                    <span>{filtered.length} entries</span>
                    <span>{paused ? '⏸ Paused' : '● Live'}</span>
                </div>
            </div>
        </div>
    );
}


// REAL-TIME LOG VIEWER COMPONENT
// ============================================================================

function LogViewerModal({ service, onClose }) {
    const [logs, setLogs] = useState([]);
    const [autoScroll, setAutoScroll] = useState(true);
    const [filter, setFilter] = useState('');
    const [loading, setLoading] = useState(true);
    const logsEndRef = useRef(null);

    useEffect(() => {
        fetchLogs();
        
        // Poll for new logs every 2 seconds
        const interval = setInterval(fetchLogs, 10000);
        return () => clearInterval(interval);
    }, [service.id]);

    useEffect(() => {
        if (autoScroll && logsEndRef.current) {
            logsEndRef.current.scrollIntoView({ behavior: 'smooth' });
        }
    }, [logs, autoScroll]);

    const fetchLogs = async () => {
        try {
            const response = await AuthFetch(`${API_URL}/services/${service.id}/logs?lines=100`);
            const data = await response.json();
            setLogs(data.logs || []);
            setLoading(false);
        } catch (error) {
            console.error('Failed to fetch logs:', error);
            setLoading(false);
        }
    };

    const filteredLogs = logs.filter(log => 
        filter === '' || log.toLowerCase().includes(filter.toLowerCase())
    );

    const getLogLevel = (line) => {
        if (line.includes('ERROR') || line.includes('error')) return 'error';
        if (line.includes('WARN') || line.includes('warn')) return 'warning';
        if (line.includes('INFO') || line.includes('info')) return 'info';
        return 'default';
    };

    return (
        <div className="modal-overlay" onClick={onClose}>
            <div className="modal-content log-viewer-modal" onClick={e => e.stopPropagation()}>
                <div className="modal-header">
                    <h2>» Logs - {service.name}</h2>
                    <button className="modal-close" onClick={onClose}>×</button>
                </div>

                <div className="log-controls">
                    <input
                        type="text"
                        className="log-filter"
                        placeholder="Filter logs..."
                        value={filter}
                        onChange={(e) => setFilter(e.target.value)}
                    />
                    <label className="log-autoscroll">
                        <input
                            type="checkbox"
                            checked={autoScroll}
                            onChange={(e) => setAutoScroll(e.target.checked)}
                        />
                        Auto-scroll
                    </label>
                    <button className="btn-sm" onClick={fetchLogs}>
                        ↻ Refresh
                    </button>
                </div>

                <div className="log-viewer">
                    {loading ? (
                        <div className="log-loading">Loading logs...</div>
                    ) : filteredLogs.length === 0 ? (
                        <div className="log-empty">No logs found</div>
                    ) : (
                        filteredLogs.map((line, idx) => (
                            <div key={idx} className={`log-line log-${getLogLevel(line)}`}>
                                {line}
                            </div>
                        ))
                    )}
                    <div ref={logsEndRef} />
                </div>

                <div className="modal-footer">
                    <span className="log-count">{filteredLogs.length} lines</span>
                    <button className="btn-secondary" onClick={onClose}>Close</button>
                </div>
            </div>
        </div>
    );
}

// ============================================================================
// SERVICE UPDATE UI COMPONENT
// ============================================================================

function UpdateManagerModal({ service, onClose, onUpdate }) {
    const [checking, setChecking] = useState(true);
    const [updateAvailable, setUpdateAvailable] = useState(false);
    const [currentDigest, setCurrentDigest] = useState('');
    const [latestDigest, setLatestDigest] = useState('');
    const [updating, setUpdating] = useState(false);

    useEffect(() => {
        checkForUpdates();
    }, [service.id]);

    const checkForUpdates = async () => {
        setChecking(true);
        try {
            const response = await AuthFetch(`${API_URL}/services/${service.id}/check-update`);
            const data = await response.json();
            
            setUpdateAvailable(data.update_available);
            setCurrentDigest(data.current_digest);
            setLatestDigest(data.latest_digest);
        } catch (error) {
            console.error('Failed to check for updates:', error);
        } finally {
            setChecking(false);
        }
    };

    const handleUpdate = async () => {
        setUpdating(true);
        try {
            const response = await AuthFetch(`${API_URL}/services/${service.id}/update`, {
                method: 'POST'
            });
            const data = await response.json();
            
            if (data.success) {
                showToast(`${service.name} updated successfully`, 'success');
                onUpdate();
                onClose();
            } else {
                showToast(data.error || 'Update failed', 'error');
            }
        } catch (error) {
            showToast('Update failed', 'error');
        } finally {
            setUpdating(false);
        }
    };

    return (
        <div className="modal-overlay" onClick={onClose}>
            <div className="modal-content update-modal" onClick={e => e.stopPropagation()}>
                <div className="modal-header">
                    <h2>↻ Update {service.name}</h2>
                    <button className="modal-close" onClick={onClose}>×</button>
                </div>

                <div className="modal-body">
                    {checking ? (
                        <div className="update-checking">
                            <div className="spinner"></div>
                            <p>Checking for updates...</p>
                        </div>
                    ) : updateAvailable ? (
                        <div className="update-available">
                            <div className="update-icon">✨</div>
                            <h3>Update Available!</h3>
                            <div className="update-details">
                                <div className="digest-info">
                                    <label>Current:</label>
                                    <code>{currentDigest.substring(0, 12)}</code>
                                </div>
                                <div className="digest-info">
                                    <label>Latest:</label>
                                    <code>{latestDigest.substring(0, 12)}</code>
                                </div>
                            </div>
                            <div className="update-warning">
                                <p>⚠️ Service will be briefly unavailable during update</p>
                                <p>✓ Automatic backup will be created before update</p>
                            </div>
                        </div>
                    ) : (
                        <div className="update-current">
                            <div className="update-icon">✓</div>
                            <h3>Up to Date</h3>
                            <p>{service.name} is running the latest version</p>
                            <div className="digest-info">
                                <label>Version:</label>
                                <code>{currentDigest.substring(0, 12)}</code>
                            </div>
                        </div>
                    )}
                </div>

                <div className="modal-footer">
                    {updateAvailable && (
                        <button 
                            className="btn-primary" 
                            onClick={handleUpdate}
                            disabled={updating}
                        >
                            {updating ? 'Updating...' : 'Update Now'}
                        </button>
                    )}
                    <button className="btn-secondary" onClick={checkForUpdates} disabled={checking}>
                        Re-check
                    </button>
                    <button className="btn-secondary" onClick={onClose}>Close</button>
                </div>
            </div>
        </div>
    );
}

// ============================================================================
// BACKUP MANAGER UI COMPONENT
// ============================================================================

function BackupManagerModal({ service, onClose }) {
    const [backups, setBackups] = useState([]);
    const [loading, setLoading] = useState(true);
    const [creating, setCreating] = useState(false);
    const [restoring, setRestoring] = useState(null);

    useEffect(() => {
        fetchBackups();
    }, [service.id]);

    const fetchBackups = async () => {
        try {
            const response = await AuthFetch(`${API_URL}/services/${service.id}/backups`);
            const data = await response.json();
            setBackups(data.backups || []);
        } catch (error) {
            console.error('Failed to fetch backups:', error);
        } finally {
            setLoading(false);
        }
    };

    const handleCreateBackup = async () => {
        setCreating(true);
        try {
            const response = await AuthFetch(`${API_URL}/services/${service.id}/backup`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ note: 'Manual backup from dashboard' })
            });
            const data = await response.json();
            
            if (data.success) {
                showToast('Backup created successfully', 'success');
                fetchBackups();
            } else {
                showToast('Backup failed', 'error');
            }
        } catch (error) {
            showToast('Backup failed', 'error');
        } finally {
            setCreating(false);
        }
    };

    const handleRestore = async (backupId) => {
        if (!confirm(`Restore ${service.name} from this backup? Current data will be replaced.`)) {
            return;
        }

        setRestoring(backupId);
        try {
            const response = await AuthFetch(`${API_URL}/services/${service.id}/restore`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ backup_id: backupId })
            });
            const data = await response.json();
            
            if (data.success) {
                showToast('Restore completed successfully', 'success');
            } else {
                showToast('Restore failed', 'error');
            }
        } catch (error) {
            showToast('Restore failed', 'error');
        } finally {
            setRestoring(null);
        }
    };

    const formatSize = (bytes) => {
        const units = ['B', 'KB', 'MB', 'GB'];
        let size = bytes;
        let unitIndex = 0;
        while (size >= 1024 && unitIndex < units.length - 1) {
            size /= 1024;
            unitIndex++;
        }
        return `${size.toFixed(2)} ${units[unitIndex]}`;
    };

    return (
        <div className="modal-overlay" onClick={onClose}>
            <div className="modal-content backup-modal" onClick={e => e.stopPropagation()}>
                <div className="modal-header">
                    <h2>▪ Backups - {service.name}</h2>
                    <button className="modal-close" onClick={onClose}>×</button>
                </div>

                <div className="backup-actions">
                    <button 
                        className="btn-primary" 
                        onClick={handleCreateBackup}
                        disabled={creating}
                    >
                        {creating ? 'Creating...' : '+ Create Backup'}
                    </button>
                </div>

                <div className="backup-list">
                    {loading ? (
                        <div className="backup-loading">Loading backups...</div>
                    ) : backups.length === 0 ? (
                        <div className="backup-empty">
                            <p>No backups found</p>
                            <p>Create your first backup to get started</p>
                        </div>
                    ) : (
                        backups.map(backup => (
                            <div key={backup.backup_id} className="backup-item">
                                <div className="backup-info">
                                    <div className="backup-id">{backup.backup_id}</div>
                                    <div className="backup-meta">
                                        <span>{new Date(backup.created_at).toLocaleString()}</span>
                                        <span>{formatSize(backup.size_bytes)}</span>
                                    </div>
                                    {backup.note && (
                                        <div className="backup-note">{backup.note}</div>
                                    )}
                                </div>
                                <div className="backup-actions">
                                    <button
                                        className="btn-sm btn-primary"
                                        onClick={() => handleRestore(backup.backup_id)}
                                        disabled={restoring === backup.backup_id}
                                    >
                                        {restoring === backup.backup_id ? 'Restoring...' : 'Restore'}
                                    </button>
                                </div>
                            </div>
                        ))
                    )}
                </div>

                <div className="modal-footer">
                    <span className="backup-count">{backups.length} backup(s)</span>
                    <button className="btn-secondary" onClick={onClose}>Close</button>
                </div>
            </div>
        </div>
    );
}


// ============================================================================
// SERVICE METRICS COMPONENT
// ============================================================================

function ServiceMetrics({ service }) {
    const [metrics, setMetrics] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        fetchMetrics();
        const interval = setInterval(fetchMetrics, 60000); // Every 10 seconds
        return () => clearInterval(interval);
    }, [service.id]);

    const fetchMetrics = async () => {
        try {
            const response = await AuthFetch(`${API_URL}/services/${service.id}/metrics`);
            const data = await response.json();
            setMetrics(data);
            setLoading(false);
        } catch (error) {
            console.error('Failed to fetch metrics:', error);
            setLoading(false);
        }
    };

    if (loading || !metrics) {
        return <div className="metrics-loading">Loading metrics...</div>;
    }

    return (
        <div className="service-metrics">
            <div className="metric-item">
                <div className="metric-icon">CPU</div>
                <div className="metric-info">
                    <label>CPU</label>
                    <div className="metric-value">{metrics.cpu?.toFixed(1) || 0}%</div>
                </div>
                <div className="metric-bar">
                    <div 
                        className="metric-fill" 
                        style={{ width: `${metrics.cpu || 0}%` }}
                    ></div>
                </div>
            </div>

            <div className="metric-item">
                <div className="metric-icon">MEM</div>
                <div className="metric-info">
                    <label>Memory</label>
                    <div className="metric-value">{metrics.memory?.toFixed(1) || 0}%</div>
                </div>
                <div className="metric-bar">
                    <div 
                        className="metric-fill" 
                        style={{ width: `${metrics.memory || 0}%` }}
                    ></div>
                </div>
            </div>

            <div className="metric-item">
                <div className="metric-icon">▪</div>
                <div className="metric-info">
                    <label>Disk</label>
                    <div className="metric-value">{metrics.disk?.used || 'N/A'}</div>
                </div>
            </div>

            <div className="metric-item">
                <div className="metric-icon">🌐</div>
                <div className="metric-info">
                    <label>Network</label>
                    <div className="metric-value">
                        ↑ {metrics.network?.tx || '0'} | ↓ {metrics.network?.rx || '0'}
                    </div>
                </div>
            </div>
        </div>
    );
}

// ============================================================================
// SYSTEM OVERVIEW COMPONENT
// ============================================================================

function SystemOverview() {
    const [stats, setStats] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        fetchStats();
        const interval = setInterval(fetchStats, 60000);
        return () => clearInterval(interval);
    }, []);

    const fetchStats = async () => {
        try {
            const response = await AuthFetch(`${API_URL}/system/stats`);
            const data = await response.json();
            setStats(data);
            setLoading(false);
        } catch (error) {
            console.error('Failed to fetch system stats:', error);
            setLoading(false);
        }
    };

    if (loading || !stats) {
        return null;
    }

    return (
        <div className="system-overview">
            <div className="overview-card">
                <div className="overview-icon">▸</div>
                <div className="overview-info">
                    <div className="overview-value">{stats.services_running || 0}</div>
                    <div className="overview-label">Services Running</div>
                </div>
            </div>

            <div className="overview-card">
                <div className="overview-icon">✓</div>
                <div className="overview-info">
                    <div className="overview-value">{stats.services_healthy || 0}</div>
                    <div className="overview-label">Healthy</div>
                </div>
            </div>

            <div className="overview-card">
                <div className="overview-icon">⏱</div>
                <div className="overview-info">
                    <div className="overview-value">{stats.uptime || '0h'}</div>
                    <div className="overview-label">Uptime</div>
                </div>
            </div>

            <div className="overview-card">
                <div className="overview-icon">▪</div>
                <div className="overview-info">
                    <div className="overview-value">{stats.disk_usage || '0%'}</div>
                    <div className="overview-label">Disk Used</div>
                </div>
            </div>
        </div>
    );
}

// ============================================================================
// SERVICE RECOMMENDATIONS PANEL
// ============================================================================

function RecommendationsPanel() {
    const [recommendations, setRecommendations] = useState([]);
    const [expanded, setExpanded] = useState(false);

    useEffect(() => {
        // fetchRecommendations(); // Disabled - causing 404
    }, []);

    const fetchRecommendations = async () => {
        try {
            const response = await AuthFetch(`${API_URL}/recommendations`);
            const data = await response.json();
            setRecommendations(data.recommendations || []);
        } catch (error) {
            console.error('Failed to fetch recommendations:', error);
        }
    };

    if (true) { // Always hidden for now
        return null;
    }

    return (
        <div className="recommendations-panel">
            <div 
                className="recommendations-header" 
                onClick={() => setExpanded(!expanded)}
            >
                <h3>▸ Recommended Services</h3>
                <span className="expand-icon">{expanded ? '▼' : '▶'}</span>
            </div>

            {expanded && (
                <div className="recommendations-list">
                    {recommendations.map(rec => (
                        <div key={rec.service_id} className="recommendation-item">
                            <div className="rec-icon">{rec.icon || '○'}</div>
                            <div className="rec-info">
                                <div className="rec-name">{rec.name}</div>
                                <div className="rec-description">{rec.why_recommended}</div>
                                <div className="rec-tags">
                                    {rec.tags?.map(tag => (
                                        <span key={tag} className="rec-tag">{tag}</span>
                                    ))}
                                </div>
                            </div>
                            <button 
                                className="btn-sm btn-primary"
                                onClick={() => window.location.href = `#install-${rec.service_id}`}
                            >
                                Install
                            </button>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}

// ============================================================================
// QUICK ACTIONS MENU
// ============================================================================

function QuickActions({ service, onAction }) {
    const [menuOpen, setMenuOpen] = useState(false);

    const actions = [
        { id: 'logs', icon: '»', label: 'View Logs', color: '#3b82f6' },
        { id: 'update', icon: '↻', label: 'Check Updates', color: '#10b981' },
        { id: 'backup', icon: '▪', label: 'Manage Backups', color: '#f59e0b' },
        { id: 'security', icon: '🔒', label: 'Security Tier', color: '#ef4444' },
        { id: 'restart', icon: '⚡', label: 'Restart', color: '#8b5cf6' },
    ];

    return (
        <div className="quick-actions">
            <button 
                className="quick-actions-btn"
                onClick={() => setMenuOpen(!menuOpen)}
            >
                ⚙️ Actions
            </button>

            {menuOpen && (
                <div className="quick-actions-menu">
                    {actions.map(action => (
                        <button
                            key={action.id}
                            className="quick-action-item"
                            style={{ borderLeft: `3px solid ${action.color}` }}
                            onClick={() => {
                                onAction(action.id);
                                setMenuOpen(false);
                            }}
                        >
                            <span className="action-icon">{action.icon}</span>
                            <span className="action-label">{action.label}</span>
                        </button>
                    ))}
                </div>
            )}
        </div>
    );
}

// ============================================================================
// NOTIFICATION SETTINGS PANEL
// ============================================================================

function NotificationSettings() {
    const [settings, setSettings] = useState({
        health_failures: true,
        backups: true,
        updates: true,
        tier_changes: true,
        rate_limits: false
    });

    const handleToggle = async (key) => {
        const newSettings = { ...settings, [key]: !settings[key] };
        setSettings(newSettings);

        try {
            await AuthFetch(`${API_URL}/settings/notifications`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(newSettings)
            });
            showToast('Notification settings updated', 'success');
        } catch (error) {
            showToast('Failed to update settings', 'error');
        }
    };

    return (
        <div className="notification-settings">
            <h3>🔔 Desktop Notifications</h3>
            <div className="settings-list">
                <label className="setting-item">
                    <input
                        type="checkbox"
                        checked={settings.health_failures}
                        onChange={() => handleToggle('health_failures')}
                    />
                    <div className="setting-info">
                        <div className="setting-name">Health Check Failures</div>
                        <div className="setting-desc">When a service goes down</div>
                    </div>
                </label>

                <label className="setting-item">
                    <input
                        type="checkbox"
                        checked={settings.backups}
                        onChange={() => handleToggle('backups')}
                    />
                    <div className="setting-info">
                        <div className="setting-name">Backup Completion</div>
                        <div className="setting-desc">When backups complete or fail</div>
                    </div>
                </label>

                <label className="setting-item">
                    <input
                        type="checkbox"
                        checked={settings.updates}
                        onChange={() => handleToggle('updates')}
                    />
                    <div className="setting-info">
                        <div className="setting-name">Updates Available</div>
                        <div className="setting-desc">When service updates are available</div>
                    </div>
                </label>

                <label className="setting-item">
                    <input
                        type="checkbox"
                        checked={settings.tier_changes}
                        onChange={() => handleToggle('tier_changes')}
                    />
                    <div className="setting-info">
                        <div className="setting-name">Tier Changes</div>
                        <div className="setting-desc">When security tiers are modified</div>
                    </div>
                </label>

                <label className="setting-item">
                    <input
                        type="checkbox"
                        checked={settings.rate_limits}
                        onChange={() => handleToggle('rate_limits')}
                    />
                    <div className="setting-info">
                        <div className="setting-name">Rate Limit Violations</div>
                        <div className="setting-desc">When IPs are blocked</div>
                    </div>
                </label>
            </div>
        </div>
    );
}