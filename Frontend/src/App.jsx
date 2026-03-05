import { useState, useRef, useCallback, useEffect } from 'react'
import useWebSocket from './hooks/useWebSocket'
import { ShieldCheck, MonitorPlay, Brain, AlertTriangle, Search, Users, Video, AlertCircle, Loader2 } from 'lucide-react'
import LiveFeed from './components/LiveFeed'
import BrainPanel from './components/BrainPanel'
import AlertsPanel from './components/AlertsPanel'
import VerifierPanel from './components/VerifierPanel'
import RaceConditionBar from './components/RaceConditionBar'
import SearchPanel from './components/SearchPanel'
import FacesPanel from './components/FacesPanel'

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
        { id: 'dashboard', icon: MonitorPlay, label: 'Dashboard' },
        { id: 'brain', icon: Brain, label: 'Brain View' },
        { id: 'alerts', icon: AlertTriangle, label: 'Alerts' },
        { id: 'search', icon: Search, label: 'Search' },
        { id: 'faces', icon: Users, label: 'Faces & Zones' },
    ]

    return (
        <div className="flex h-screen overflow-hidden font-sans antialiased bg-[#000000] text-slate-300" style={{ fontFamily: "'Inter', sans-serif" }}>

            {/* ═══ SIDEBAR ═══ */}
            <nav className="w-16 lg:w-64 bg-[#050505] border-r border-white/5 flex flex-col justify-between shrink-0 transition-all duration-300 z-50">
                <div>
                    <div className="h-16 flex items-center justify-center lg:justify-start lg:px-6">
                        <ShieldCheck className="text-brand-cyan w-6 h-6" />
                        <span className="ml-3 font-bold text-white hidden lg:block tracking-wide">
                            Agentic CCTV Survillence
                        </span>
                    </div>

                    <div className="p-4 space-y-2 mt-4">
                        {navItems.map((item) => (
                            <button
                                key={item.id}
                                onClick={() => setActiveView(item.id)}
                                className={`w-full flex items-center justify-center lg:justify-start px-3 py-3 rounded-2xl transition-all group relative cursor-pointer
                ${activeView === item.id ? 'bg-[#111111] border border-white/5 text-white' : 'text-slate-400 hover:text-white hover:bg-[#111111]'}`}
                            >
                                <item.icon className={`w-5 h-5 ${activeView === item.id ? 'text-brand-cyan' : 'group-hover:text-brand-cyan'} transition-colors`} />
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

            </nav>

            {/* ═══ MAIN ═══ */}
            <main className="flex-1 flex flex-col h-screen overflow-hidden relative">

                {/* Header */}
                <header className="h-14 bg-[#050505]/80 backdrop-blur-md border-b border-white/5 flex items-center justify-between px-6 z-40 shrink-0">
                    <div className="flex items-center space-x-4">
                        <h1 className="text-lg font-semibold text-white">
                            {navItems.find(n => n.id === activeView)?.label || 'Dashboard'}
                        </h1>
                        {videoInfo && (
                            <div className="hidden md:flex items-center px-4 py-1.5 bg-[#111111] border border-white/5 rounded-2xl text-xs font-mono text-slate-300">
                                <Video className="text-brand-cyan mr-2 w-4 h-4" />
                                {videoInfo.filename} • {fmtTime(videoInfo.duration)}
                                {isProcessing && <Loader2 className="text-brand-cyan animate-spin w-4 h-4 ml-2" />}
                            </div>
                        )}
                        {uploadError && (
                            <div className="flex items-center px-4 py-1.5 bg-brand-crimson/10 rounded-2xl text-xs text-brand-crimson">
                                <AlertCircle className="w-4 h-4 mr-1" /> {uploadError}
                            </div>
                        )}
                    </div>
                    <div className="flex items-center space-x-4">
                        <div className="text-right hidden sm:block">
                            <div className="text-sm font-mono text-white">{clock.toLocaleTimeString('en-US', { hour12: false })}</div>
                            <div className="text-xs text-slate-500 font-mono">{clock.toISOString().split('T')[0]}</div>
                        </div>
                    </div>
                </header>

                {/* Race Condition Bar */}
                {hasActiveRace && <RaceConditionBar raceConditions={ws.raceConditions} currentChunk={ws.currentChunk} />}

                {/* ═══ VIEW ROUTER ═══ */}
                <div className="flex-1 overflow-y-auto overflow-x-hidden p-4 lg:p-6 bg-[#000000]">

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

                    {/* ── FACES & DANGER ZONE VIEW ── */}
                    {activeView === 'faces' && <FacesPanel />}
                </div>
            </main>
        </div>
    )
}
