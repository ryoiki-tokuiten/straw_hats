import { useEffect, useRef } from 'react'
import { Brain, Wrench, Edit3, ShieldAlert, Bot, Zap, AlertTriangle, PlayCircle, CheckCircle, Info, Loader2, FileText } from 'lucide-react'

export default function BrainPanel({ reconstructions, agentActivity, fmtTime, compact }) {
    const logRef = useRef(null)
    const recRef = useRef(null)

    useEffect(() => {
        if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight
    }, [agentActivity])

    useEffect(() => {
        if (recRef.current) recRef.current.scrollTop = recRef.current.scrollHeight
    }, [reconstructions])

    const getEntryStyle = (type) => {
        switch (type) {
            case 'tool_call': return { color: 'text-brand-cyan', bg: 'bg-brand-cyan/5', icon: Wrench, label: 'TOOL CALL' }
            case 'reconstruction': return { color: 'text-brand-emerald', bg: 'bg-brand-emerald/5', icon: Edit3, label: 'OUTPUT' }
            case 'risk_complete': return { color: 'text-brand-amber', bg: 'bg-brand-amber/5', icon: ShieldAlert, label: 'RISK SCORE' }
            case 'agent_status': return { color: 'text-brand-purple', bg: 'bg-brand-purple/5', icon: Bot, label: 'AGENT' }
            case 'race': return { color: 'text-brand-amber', bg: 'bg-brand-amber/5', icon: Zap, label: 'RACE' }
            case 'error': return { color: 'text-brand-crimson', bg: 'bg-brand-crimson/5', icon: AlertTriangle, label: 'ERROR' }
            case 'chunk_started': return { color: 'text-slate-300', bg: 'bg-slate-800/50', icon: PlayCircle, label: 'CHUNK' }
            case 'chunk_completed': return { color: 'text-brand-emerald', bg: 'bg-brand-emerald/5', icon: CheckCircle, label: 'DONE' }
            default: return { color: 'text-slate-400', bg: 'bg-slate-800/50', icon: Info, label: 'INFO' }
        }
    }

    // Parse tool call args for pretty display
    const renderToolArgs = (entry) => {
        if (entry.type !== 'tool_call' || !entry.args) return null
        return (
            <div className="mt-1.5 bg-black/40 rounded-xl p-3">
                <pre className="text-[10px] font-mono text-brand-cyan whitespace-pre-wrap">
                    {JSON.stringify(entry.args, null, 2)}
                </pre>
            </div>
        )
    }

    // Render reconstruction inline
    const renderReconstruction = (entry) => {
        if (entry.type !== 'reconstruction' || !entry.reconstruction) return null
        return (
            <div className="mt-1.5 bg-brand-emerald/5 rounded-xl p-3">
                <div className="text-[10px] font-mono text-brand-emerald/70 mb-1">ATOMIC RECONSTRUCTION OUTPUT:</div>
                <div className="text-xs text-slate-200 leading-relaxed">{entry.reconstruction}</div>
            </div>
        )
    }

    const isActive = agentActivity.length > 0 && agentActivity[agentActivity.length - 1]?.type !== 'chunk_completed'

    return (
        <div className={`glass-panel rounded-2xl border border-white/5 flex flex-col overflow-hidden bg-[#050505] shadow-xl ${compact ? 'flex-1 min-h-0' : 'h-[calc(100vh-8rem)]'}`}>
            {/* Header */}
            <div className="bg-[#050505] px-5 py-4 border-b border-white/5 flex justify-between items-center shrink-0">
                <h3 className="text-sm font-semibold flex items-center text-white">
                    <Brain className="text-brand-purple w-5 h-5 mr-2" />
                    Agent Brain
                </h3>
                <div className="flex items-center space-x-2">
                    {isActive && (
                        <div className="flex items-center space-x-1.5 bg-brand-purple/10 rounded-full px-3 py-1">
                            <div className="w-1.5 h-1.5 rounded-full bg-brand-purple animate-pulse"></div>
                            <span className="text-[10px] font-mono text-brand-purple">THINKING</span>
                        </div>
                    )}
                    <span className="text-[10px] font-mono bg-[#111111] text-slate-400 px-3 py-1 rounded-full">
                        {agentActivity.length} events
                    </span>
                </div>
            </div>

            <div className={`flex-1 ${compact ? 'grid grid-cols-1 lg:grid-cols-5' : 'grid grid-cols-1 lg:grid-cols-3'} gap-0 overflow-hidden min-h-0`}>

                {/* ── Agent Activity Stream ── */}
                <div className={`flex flex-col border-white/5 overflow-hidden ${compact ? 'lg:col-span-3' : 'lg:col-span-2 border-r'}`}>
                    <div className="text-[10px] text-slate-500 font-mono px-5 py-3 border-b border-white/5 bg-[#0a0a0a] shrink-0 flex justify-between items-center">
                        <span>AGENT ACTIVITY STREAM</span>
                        {isActive && <Loader2 className="text-brand-cyan animate-spin w-4 h-4 text-xs" />}
                    </div>
                    <div ref={logRef} className="flex-1 overflow-y-auto p-3 space-y-2">
                        {agentActivity.length === 0 ? (
                            <div className="text-slate-600 text-center py-12">
                                <Bot className="w-10 h-10 mb-3 mx-auto opacity-20" />
                                <div className="text-sm mb-1">Agents idle</div>
                                <div className="text-[10px] text-slate-700 font-mono">Upload a video to start the dual-stream pipeline</div>
                            </div>
                        ) : agentActivity.map((entry, i) => {
                            const style = getEntryStyle(entry.type)
                            return (
                                <div key={i} className={`agent-entry rounded-2xl p-4 ${style.bg} transition-all`}>
                                    {/* Header row */}
                                    <div className="flex items-center justify-between mb-1">
                                        <div className="flex items-center gap-2">
                                            <style.icon className={`w-4 h-4 ${style.color}`} />
                                            <span className={`text-[9px] font-mono font-bold ${style.color} uppercase tracking-wider`}>{style.label}</span>
                                            {entry.agent && (
                                                <span className="text-[9px] font-mono bg-slate-800/80 text-slate-400 px-1.5 py-0.5 rounded">
                                                    {entry.agent.toUpperCase()}
                                                </span>
                                            )}
                                        </div>
                                        <span className="text-[9px] font-mono text-slate-600">
                                            {entry.ts ? new Date(entry.ts).toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' }) : ''}
                                        </span>
                                    </div>
                                    {/* Content */}
                                    <div className="text-[11px] text-slate-300 leading-relaxed font-mono pl-6">
                                        {entry.type === 'tool_call' ? (
                                            <span>
                                                <span className="text-brand-cyan font-bold">{entry.tool}</span>
                                                <span className="text-slate-500">(</span>
                                                <span className="text-brand-amber">{JSON.stringify(entry.args || {})}</span>
                                                <span className="text-slate-500">)</span>
                                            </span>
                                        ) : entry.type === 'chunk_started' ? (
                                            <span>
                                                Processing chunk <span className="text-white font-bold">{entry.chunk_index}</span>
                                                {' '}({fmtTime(entry.start_ts)} → {fmtTime(entry.end_ts)})
                                                {entry.tool_less && <span className="ml-2 text-brand-amber font-bold">[TOOL-LESS MODE]</span>}
                                            </span>
                                        ) : (
                                            <span>{entry.text}</span>
                                        )}
                                    </div>
                                    {/* Tool call args */}
                                    {renderToolArgs(entry)}
                                    {/* Reconstruction output */}
                                    {renderReconstruction(entry)}
                                    {/* Reasoner reasoning */}
                                    {entry.type === 'risk_complete' && entry.reasoning && (
                                        <div className="mt-1.5 bg-brand-amber/5 rounded-xl p-3">
                                            <div className="text-[10px] font-mono text-brand-amber/70 mb-1">REASONING:</div>
                                            <div className="text-xs text-slate-200 leading-relaxed">{entry.reasoning}</div>
                                        </div>
                                    )}
                                </div>
                            )
                        })}
                        {/* Typing indicator */}
                        {isActive && (
                            <div className="flex items-center gap-2 px-3 py-2">
                                <div className="flex gap-1">
                                    <div className="w-1.5 h-1.5 rounded-full bg-brand-cyan animate-pulse" style={{ animationDelay: '0ms' }}></div>
                                    <div className="w-1.5 h-1.5 rounded-full bg-brand-cyan animate-pulse" style={{ animationDelay: '200ms' }}></div>
                                    <div className="w-1.5 h-1.5 rounded-full bg-brand-cyan animate-pulse" style={{ animationDelay: '400ms' }}></div>
                                </div>
                                <span className="text-[10px] font-mono text-slate-500">Agent thinking...</span>
                            </div>
                        )}
                    </div>
                </div>

                {/* ── Atomic Reconstructions Timeline ── */}
                <div className={`flex flex-col overflow-hidden ${compact ? 'lg:col-span-2' : 'lg:col-span-1'}`}>
                    <div className="text-[10px] text-slate-500 font-mono px-5 py-3 border-b border-white/5 bg-[#0a0a0a] shrink-0 flex justify-between">
                        <span>RECONSTRUCTIONS</span>
                        <span className="text-brand-emerald font-bold">{reconstructions.length}</span>
                    </div>
                    <div ref={recRef} className="flex-1 overflow-y-auto p-3 space-y-2">
                        {reconstructions.length === 0 ? (
                            <div className="text-slate-600 text-center py-12">
                                <FileText className="w-8 h-8 mb-2 mx-auto opacity-20" />
                                <div className="text-xs">Waiting for first reconstruction...</div>
                            </div>
                        ) : reconstructions.map((rec, i) => (
                            <div key={i} className={`agent-entry p-4 rounded-2xl transition-all ${i === reconstructions.length - 1
                                ? 'bg-brand-cyan/10'
                                : 'bg-slate-900/30'
                                }`}>
                                <div className="flex justify-between items-center mb-2">
                                    <div className="flex items-center gap-2">
                                        <div className={`w-6 h-6 rounded flex items-center justify-center text-[10px] font-bold font-mono ${i === reconstructions.length - 1 ? 'bg-brand-cyan/20 text-brand-cyan' : 'bg-slate-800 text-slate-400'
                                            }`}>
                                            {rec.chunk}
                                        </div>
                                        <span className="text-[10px] font-mono text-slate-500">CHUNK {rec.chunk}</span>
                                    </div>
                                    <div className="flex items-center gap-1">
                                        {rec.tool_less && (
                                            <span className="text-[8px] font-mono bg-brand-amber/20 text-brand-amber px-1.5 py-0.5 rounded font-bold">⚡ TOOL-LESS</span>
                                        )}
                                    </div>
                                </div>
                                <div className="text-xs text-slate-300 leading-relaxed">
                                    {rec.text}
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            </div>
        </div>
    )
}
