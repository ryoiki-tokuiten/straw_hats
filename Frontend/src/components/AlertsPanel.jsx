import { useEffect, useState } from 'react'

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
        if (score >= 0.7) return 'bg-brand-crimson/5 border-brand-crimson/20'
        if (score >= 0.4) return 'bg-brand-amber/5 border-brand-amber/20'
        return 'bg-brand-emerald/5 border-brand-emerald/20'
    }

    const getScoreLabel = (score) => {
        if (score >= 0.8) return 'CRITICAL'
        if (score >= 0.6) return 'SUSPICIOUS'
        if (score >= 0.4) return 'MODERATE'
        if (score >= 0.2) return 'LOW'
        return 'NORMAL'
    }

    return (
        <div className={`glass-panel rounded-xl border overflow-hidden flex flex-col transition-all duration-300 ${compact ? '' : 'h-[calc(100vh-8rem)]'
            } ${isFlashing ? 'alert-flashing border-brand-crimson/50' : 'border-slate-700/50'}`}>

            {/* Header */}
            <div className={`px-4 py-2.5 border-b flex justify-between items-center shrink-0 transition-colors duration-300 ${isFlashing ? 'bg-brand-crimson/10 border-brand-crimson/20' : 'bg-slate-900/80 border-slate-800'
                }`}>
                <h3 className="text-sm font-semibold flex items-center text-white">
                    <i className={`ph-fill ph-warning-diamond mr-2 text-lg ${isFlashing ? 'text-brand-crimson animate-pulse' : 'text-brand-amber'}`}></i>
                    Threat Alerts
                </h3>
                <span className={`text-[10px] font-mono px-2 py-0.5 rounded border ${alerts.length > 0 ? 'bg-brand-crimson/20 text-brand-crimson border-brand-crimson/30' : 'bg-slate-800 text-slate-400 border-slate-700'
                    }`}>
                    {alerts.length > 0 ? `${alerts.length} ALERT${alerts.length > 1 ? 'S' : ''}` : 'ALL CLEAR'}
                </span>
            </div>

            {/* Risk Gauge */}
            {latestRisk && (
                <div className="px-4 py-3 border-b border-slate-800 bg-slate-900/50 shrink-0">
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
                        <i className="ph ph-shield-check text-4xl mb-3 block opacity-20"></i>
                        <div className="text-sm mb-1">No threats detected</div>
                        <div className="text-[10px] text-slate-700 font-mono">System monitoring active</div>
                    </div>
                ) : (
                    <>
                        {/* Critical Alerts */}
                        {alerts.map((alert, i) => (
                            <div key={i} className="agent-entry p-3 border border-brand-crimson/30 bg-brand-crimson/5 rounded-lg">
                                <div className="flex justify-between items-start mb-2">
                                    <div className="flex items-center space-x-2">
                                        <i className="ph-fill ph-siren text-brand-crimson animate-pulse"></i>
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
                            <div className="text-[10px] font-mono text-slate-500 mb-2 border-b border-slate-800 pb-1">RISK SCORE HISTORY</div>
                            {riskScores.slice().reverse().map((rs, i) => (
                                <div key={`rs-${i}`} className={`p-2.5 border rounded-lg mb-1.5 ${getScoreBg(rs.score)}`}>
                                    <div className="flex justify-between items-center mb-1">
                                        <div className="flex items-center gap-2">
                                            <span className="text-[10px] font-mono text-slate-400">Chunk {rs.chunk}</span>
                                            {rs.tool_less && <span className="text-[8px] font-mono bg-brand-amber/20 text-brand-amber px-1 rounded">⚡</span>}
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
