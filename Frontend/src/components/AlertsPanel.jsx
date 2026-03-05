import { useEffect, useState } from 'react'
import { AlertTriangle, ShieldCheck, AlertCircle, Zap } from 'lucide-react'

export default function AlertsPanel({ alerts, riskScores, fmtTime, compact }) {
    const [isFlashing, setIsFlashing] = useState(false)

    useEffect(() => {
        if (alerts.length > 0) {
            setIsFlashing(true)
            const timer = setTimeout(() => setIsFlashing(false), 5000)
            return () => clearTimeout(timer)
        }
    }, [alerts.length])

    const latestRisk = riskScores.length > 0 ? riskScores[riskScores.length - 1] : null

    const getScoreColor = (score) => {
        if (score >= 0.7) return 'text-brand-crimson'
        if (score >= 0.4) return 'text-brand-amber'
        return 'text-brand-emerald'
    }

    const getScoreBg = (score) => {
        if (score >= 0.7) return 'bg-brand-crimson/5'
        if (score >= 0.4) return 'bg-brand-amber/5'
        return 'bg-brand-emerald/5'
    }

    const getScoreLabel = (score) => {
        if (score >= 0.8) return 'CRITICAL'
        if (score >= 0.6) return 'SUSPICIOUS'
        if (score >= 0.4) return 'MODERATE'
        if (score >= 0.2) return 'LOW'
        return 'NORMAL'
    }

    return (
        <div className={`glass-panel rounded-2xl border border-white/5 overflow-hidden flex flex-col transition-all duration-300 bg-[#050505] shadow-xl ${compact ? '' : 'h-[calc(100vh-8rem)]'
            } ${isFlashing ? 'alert-flashing ring-2 ring-brand-crimson/50' : ''}`}>

            {/* Header */}
            <div className={`px-5 py-4 flex justify-between items-center border-b border-white/5 shrink-0 transition-colors duration-300 ${isFlashing ? 'bg-brand-crimson/10' : 'bg-[#050505]'
                }`}>
                <h3 className="text-sm font-semibold flex items-center text-white">
                    <AlertTriangle className={`mr-2 w-5 h-5 ${isFlashing ? 'text-brand-crimson animate-pulse' : 'text-brand-amber'}`} />
                    Threat Alerts
                </h3>
                <span className={`text-[10px] font-mono rounded-full ${alerts.length > 0 ? 'bg-brand-crimson/20 text-brand-crimson px-3 py-1' : 'bg-[#111111] text-slate-400 px-3 py-1'
                    }`}>
                    {alerts.length > 0 ? `${alerts.length} ALERT${alerts.length > 1 ? 'S' : ''}` : 'ALL CLEAR'}
                </span>
            </div>

            {/* Risk Gauge */}
            {latestRisk && (
                <div className="px-5 py-4 bg-[#0a0a0a] border-b border-white/5 shrink-0">
                    <div className="flex justify-between items-center mb-2">
                        <span className="text-[10px] font-mono text-slate-500">LATEST RISK ASSESSMENT — CHUNK {latestRisk.chunk}</span>
                        <span className={`text-lg font-bold font-mono ${getScoreColor(latestRisk.score)}`}>
                            {(latestRisk.score * 100).toFixed(0)}%
                        </span>
                    </div>
                    <div className="w-full bg-slate-800 rounded-full h-2 overflow-hidden">
                        <div className={`h-2 rounded-full transition-all duration-700 ${latestRisk.score >= 0.7 ? 'bg-brand-crimson' : latestRisk.score >= 0.4 ? 'bg-brand-amber' : 'bg-brand-emerald'
                            }`} style={{ width: `${latestRisk.score * 100}%` }}></div>
                    </div>
                    <div className="flex justify-between mt-1.5">
                        <span className={`text-[9px] font-mono font-bold ${getScoreColor(latestRisk.score)}`}>
                            {getScoreLabel(latestRisk.score)}
                        </span>
                        <span className="text-[9px] font-mono text-slate-500">{latestRisk.classification}</span>
                    </div>
                </div>
            )}

            {/* Alert List */}
            <div className="flex-1 overflow-y-auto p-3 space-y-2">
                {alerts.length === 0 && riskScores.length === 0 ? (
                    <div className="text-slate-600 text-center py-12">
                        <ShieldCheck className="w-10 h-10 mb-3 mx-auto opacity-20" />
                        <div className="text-sm mb-1">No threats detected</div>
                        <div className="text-[10px] text-slate-700 font-mono">System monitoring active</div>
                    </div>
                ) : (
                    <>
                        {/* Critical Alerts */}
                        {alerts.map((alert, i) => (
                            <div key={i} className="agent-entry p-4 bg-brand-crimson/10 rounded-2xl">
                                <div className="flex justify-between items-start mb-2">
                                    <div className="flex items-center space-x-2">
                                        <AlertCircle className="w-5 h-5 text-brand-crimson animate-pulse" />
                                        <span className="text-xs font-bold text-brand-crimson">CRITICAL ALERT</span>
                                    </div>
                                    <span className="text-[10px] font-mono text-slate-400">Chunk {alert.chunk_index}</span>
                                </div>
                                <div className="text-xs text-slate-300 mb-2 leading-relaxed">{alert.reasoning}</div>
                                <div className="flex justify-between items-center">
                                    <span className="text-[10px] font-mono text-brand-crimson">
                                        Score: {(alert.score * 100).toFixed(1)}% • {alert.classification}
                                    </span>
                                    {alert.action_required && (
                                        <span className="text-[9px] bg-brand-crimson/30 text-brand-crimson px-2 py-0.5 rounded font-bold animate-pulse">
                                            ACTION REQUIRED
                                        </span>
                                    )}
                                </div>
                            </div>
                        ))}

                        {/* Risk Score History */}
                        <div className="mt-3">
                            <div className="text-[10px] font-mono text-slate-500 mb-3 pb-2">RISK SCORE HISTORY</div>
                            {riskScores.slice().reverse().map((rs, i) => (
                                <div key={`rs-${i}`} className={`p-4 rounded-2xl mb-2 ${getScoreBg(rs.score)}`}>
                                    <div className="flex justify-between items-center mb-1">
                                        <div className="flex items-center gap-2">
                                            <span className="text-[10px] font-mono text-slate-400">Chunk {rs.chunk}</span>
                                            {rs.tool_less && <span className="text-[8px] font-mono bg-brand-amber/20 text-brand-amber px-1.5 py-0.5 rounded-full flex items-center gap-1"><Zap className="w-2.5 h-2.5" />TOOL-LESS</span>}
                                        </div>
                                        <span className={`text-xs font-mono font-bold ${getScoreColor(rs.score)}`}>
                                            {(rs.score * 100).toFixed(0)}%
                                        </span>
                                    </div>
                                    <div className="text-[10px] text-slate-400 font-mono">{rs.classification}</div>
                                    {!compact && rs.reasoning && (
                                        <div className="text-[10px] text-slate-500 mt-1 leading-relaxed">{rs.reasoning}</div>
                                    )}
                                </div>
                            ))}
                        </div>
                    </>
                )}
            </div>
        </div>
    )
}
