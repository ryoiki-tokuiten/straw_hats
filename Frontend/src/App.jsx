import { useState, useRef, useCallback, useEffect } from 'react'
import useWebSocket from './hooks/useWebSocket'
import LiveFeed from './components/LiveFeed'
import BrainPanel from './components/BrainPanel'
import AlertsPanel from './components/AlertsPanel'
import VerifierPanel from './components/VerifierPanel'
import RaceConditionBar from './components/RaceConditionBar'
import SearchPanel from './components/SearchPanel'

export default function App() {
    const ws = useWebSocket()
    const [activeView, setActiveView] = useState('dashboard')
    const [videoId, setVideoId] = useState(null)
    const [videoUrl, setVideoUrl] = useState(null)
    const [videoInfo, setVideoInfo] = useState(null)
    const [uploading, setUploading] = useState(false)
    const [uploadError, setUploadError] = useState(null)
    const fileInputRef = useRef(null)

    const handleUpload = useCallback(async (file) => {
        if (!file) return
        setUploading(true)
        setUploadError(null)
        ws.clearState()

        const formData = new FormData()
        formData.append('file', file)

        try {
            const res = await fetch('/api/upload', { method: 'POST', body: formData })
            if (!res.ok) throw new Error(`Upload failed: ${res.status}`)
            const data = await res.json()
            setVideoId(data.video_id)
            setVideoUrl(data.video_url)
            setVideoInfo(data)
            setActiveView('dashboard') // Switch to dashboard view on upload
        } catch (err) {
            console.error('Upload failed:', err)
            setUploadError(err.message)
        } finally {
            setUploading(false)
        }
    }, [ws])

    const handleDrop = useCallback((e) => {
        e.preventDefault()
        const file = e.dataTransfer?.files?.[0]
        if (file && file.type.startsWith('video/')) handleUpload(file)
    }, [handleUpload])

    const handleFileChange = useCallback((e) => {
        const file = e.target.files?.[0]
        if (file) handleUpload(file)
    }, [handleUpload])

    const fmtTime = (ts) => {
        if (ts === null || ts === undefined) return '--:--'
        const m = Math.floor(ts / 60)
        const s = Math.floor(ts % 60)
        return `${m}:${s.toString().padStart(2, '0')}`
    }

    const [clock, setClock] = useState(new Date())
    useEffect(() => {
        const t = setInterval(() => setClock(new Date()), 1000)
        return () => clearInterval(t)
    }, [])

    const hasActiveRace = ws.raceConditions.length > 0 && ws.pipelineStatus?.type !== 'pipeline_completed'
    const totalChunks = videoInfo?.total_chunks || ws.pipelineStatus?.data?.total_chunks || 0
    const completedChunks = ws.reconstructions.length
    const isProcessing = ws.pipelineStatus && ws.pipelineStatus.type !== 'pipeline_completed' && ws.pipelineStatus.type !== 'pipeline_error'
    const pipelineComplete = ws.pipelineStatus?.type === 'pipeline_completed'

    const navItems = [
        { id: 'dashboard', icon: 'ph-monitor-play', label: 'Dashboard' },
        { id: 'brain', icon: 'ph-brain', label: 'Brain View' },
        { id: 'alerts', icon: 'ph-warning-diamond', label: 'Alerts' },
        { id: 'search', icon: 'ph-magnifying-glass', label: 'Search' },
    ]

    return (
        <div className="flex h-screen overflow-hidden font-sans antialiased bg-[#020617] text-slate-300" style={{ fontFamily: "'Inter', sans-serif" }}>

            {/* ═══ SIDEBAR ═══ */}
            <nav className="w-16 lg:w-64 bg-slate-900 border-r border-slate-800 flex flex-col justify-between shrink-0 transition-all duration-300 z-50">
                <div>
                    <div className="h-16 flex items-center justify-center lg:justify-start lg:px-6 border-b border-slate-800">
                        <i className="ph-fill ph-shield-check text-brand-cyan text-2xl"></i>
                        <span className="ml-3 font-bold text-white hidden lg:block tracking-wide">
                            DSSA<span className="text-brand-cyan">.AI</span>
                        </span>
                    </div>

                    <div className="p-4 space-y-2 mt-4">
                        {navItems.map((item) => (
                            <button
                                key={item.id}
                                onClick={() => setActiveView(item.id)}
                                className={`w-full flex items-center justify-center lg:justify-start px-3 py-3 rounded transition-all group relative cursor-pointer
                ${activeView === item.id ? 'bg-slate-800 text-white border-l-2 border-brand-cyan' : 'text-slate-400 hover:text-white hover:bg-slate-800'}`}
                            >
                                <i className={`ph ${item.icon} text-xl ${activeView === item.id ? 'text-brand-cyan' : 'group-hover:text-brand-cyan'} transition-colors`}></i>
                                <span className="ml-3 text-sm font-medium hidden lg:block">{item.label}</span>
                                {/* Badge for alerts */}
                                {item.id === 'alerts' && ws.alerts.length > 0 && (
                                    <span className="ml-auto hidden lg:flex w-5 h-5 bg-brand-crimson text-[10px] font-bold text-white rounded-full items-center justify-center">
                                        {ws.alerts.length}
                                    </span>
                                )}
                            </button>
                        ))}
                    </div>
                </div>

                <div className="p-4 border-t border-slate-800">
                    <div className="flex items-center justify-center lg:justify-start mb-3">
                        <div className={`w-2 h-2 rounded-full ${ws.isConnected ? 'bg-brand-emerald animate-pulse' : 'bg-red-500'}`}></div>
                        <span className="ml-2 text-xs font-mono text-slate-400 hidden lg:block">
                            {ws.isConnected ? 'WS.CONNECTED' : 'WS.OFFLINE'}
                        </span>
                    </div>
                    {(isProcessing || pipelineComplete) && (
                        <div className="hidden lg:block bg-brand-cyan/10 border border-brand-cyan/30 rounded p-2 mb-2">
                            <div className={`text-[10px] font-mono mb-1 ${pipelineComplete ? 'text-brand-emerald' : 'text-brand-cyan'}`}>
                                {pipelineComplete ? '✓ COMPLETE' : 'PROCESSING'}
                            </div>
                            <div className="w-full bg-slate-800 rounded-full h-1.5">
                                <div className={`h-1.5 rounded-full transition-all duration-500 ${pipelineComplete ? 'bg-brand-emerald' : 'bg-brand-cyan'}`}
                                    style={{ width: `${totalChunks > 0 ? (completedChunks / totalChunks * 100) : 0}%` }}
                                ></div>
                            </div>
                            <div className="text-[10px] font-mono text-slate-400 mt-1">{completedChunks}/{totalChunks} chunks</div>
                        </div>
                    )}
                    {/* Upload button in sidebar */}
                    <button
                        onClick={() => fileInputRef.current?.click()}
                        className="w-full flex items-center justify-center lg:justify-start px-3 py-2 bg-brand-cyan/10 text-brand-cyan hover:bg-brand-cyan/20 rounded border border-brand-cyan/30 transition-colors group"
                    >
                        <i className="ph ph-upload-simple text-lg"></i>
                        <span className="ml-2 text-sm font-semibold hidden lg:block">Upload Video</span>
                    </button>
                    <input ref={fileInputRef} type="file" accept="video/*" onChange={handleFileChange} className="hidden" />
                </div>
            </nav>

            {/* ═══ MAIN ═══ */}
            <main className="flex-1 flex flex-col h-screen overflow-hidden relative">

                {/* Header */}
                <header className="h-14 bg-slate-900/50 backdrop-blur-md border-b border-slate-800 flex items-center justify-between px-6 z-40 shrink-0">
                    <div className="flex items-center space-x-4">
                        <h1 className="text-lg font-semibold text-white">
                            {navItems.find(n => n.id === activeView)?.label || 'Dashboard'}
                        </h1>
                        {videoInfo && (
                            <div className="hidden md:flex items-center px-3 py-1 bg-slate-800 rounded-full border border-slate-700 text-xs font-mono text-slate-300">
                                <i className="ph ph-video-camera text-brand-cyan mr-2"></i>
                                {videoInfo.filename} • {fmtTime(videoInfo.duration)}
                                {isProcessing && <i className="ph ph-spinner-gap text-brand-cyan animate-spin ml-2"></i>}
                            </div>
                        )}
                        {uploadError && (
                            <div className="flex items-center px-3 py-1 bg-brand-crimson/20 rounded-full border border-brand-crimson/30 text-xs text-brand-crimson">
                                <i className="ph ph-warning mr-1"></i> {uploadError}
                            </div>
                        )}
                    </div>
                    <div className="flex items-center space-x-4">
                        <div className="text-right hidden sm:block">
                            <div className="text-sm font-mono text-white">{clock.toLocaleTimeString('en-US', { hour12: false })}</div>
                            <div className="text-xs text-slate-500 font-mono">{clock.toISOString().split('T')[0]}</div>
                        </div>
                        <div className="relative">
                            <button
                                onClick={() => setActiveView('alerts')}
                                className={`transition-colors relative cursor-pointer ${ws.alerts.length > 0 ? 'text-brand-crimson animate-pulse' : 'text-slate-400 hover:text-white'}`}
                            >
                                <i className="ph ph-bell text-xl"></i>
                                {ws.alerts.length > 0 && (
                                    <span className="absolute -top-1 -right-1 w-4 h-4 bg-brand-crimson text-[9px] font-bold text-white rounded-full flex items-center justify-center border-2 border-slate-900">
                                        {ws.alerts.length}
                                    </span>
                                )}
                            </button>
                        </div>
                    </div>
                </header>

                {/* Race Condition Bar */}
                {hasActiveRace && <RaceConditionBar raceConditions={ws.raceConditions} currentChunk={ws.currentChunk} />}

                {/* ═══ VIEW ROUTER ═══ */}
                <div className="flex-1 overflow-y-auto overflow-x-hidden p-4 lg:p-6 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-slate-900 via-slate-950 to-slate-950">

                    {/* ── DASHBOARD VIEW ── */}
                    {activeView === 'dashboard' && (
                        <div className="grid grid-cols-1 xl:grid-cols-12 gap-5 h-full min-h-0">
                            <div className="xl:col-span-7 flex flex-col gap-5 min-h-0">
                                <LiveFeed
                                    videoUrl={videoUrl} videoInfo={videoInfo} currentChunk={ws.currentChunk}
                                    uploading={uploading} onUpload={handleUpload} fileInputRef={fileInputRef}
                                    onFileChange={handleFileChange} onDrop={handleDrop}
                                    isProcessing={isProcessing} completedChunks={completedChunks}
                                    totalChunks={totalChunks} fmtTime={fmtTime}
                                />
                                <BrainPanel
                                    reconstructions={ws.reconstructions} agentActivity={ws.agentActivity}
                                    fmtTime={fmtTime} compact={true}
                                />
                            </div>
                            <div className="xl:col-span-5 flex flex-col gap-5 min-h-0">
                                <AlertsPanel alerts={ws.alerts} riskScores={ws.riskScores} fmtTime={fmtTime} compact={true} />
                                <VerifierPanel
                                    currentChunk={ws.currentChunk} riskScores={ws.riskScores}
                                    agentActivity={ws.agentActivity} fmtTime={fmtTime}
                                />
                            </div>
                        </div>
                    )}

                    {/* ── BRAIN VIEW (Full) ── */}
                    {activeView === 'brain' && (
                        <BrainPanel
                            reconstructions={ws.reconstructions} agentActivity={ws.agentActivity}
                            fmtTime={fmtTime} compact={false}
                        />
                    )}

                    {/* ── ALERTS VIEW (Full) ── */}
                    {activeView === 'alerts' && (
                        <AlertsPanel alerts={ws.alerts} riskScores={ws.riskScores} fmtTime={fmtTime} compact={false} />
                    )}

                    {/* ── SEARCH VIEW ── */}
                    {activeView === 'search' && <SearchPanel />}
                </div>
            </main>
        </div>
    )
}
