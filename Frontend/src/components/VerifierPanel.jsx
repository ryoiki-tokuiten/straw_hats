import { SearchCode, Loader2, Eye, EyeOff, Terminal, Zap } from 'lucide-react'

export default function VerifierPanel({ currentChunk, riskScores, agentActivity, fmtTime }) {
    // Get reasoner-specific activity
    const reasonerActivity = agentActivity.filter(a =>
        a.agent === 'reasoner' || a.text?.includes('[REASONER]')
    )

    const latestRisk = riskScores.length > 0 ? riskScores[riskScores.length - 1] : null
    const isAnalyzing = reasonerActivity.length > 0 &&
        currentChunk && !latestRisk

    // Check if reasoner is actively working (no risk_complete for current chunk)
    const currentChunkHasResult = latestRisk && currentChunk &&
        latestRisk.chunk === currentChunk.chunk_index

    const showAnalyzing = currentChunk && !currentChunkHasResult

    return (
        <div className="glass-panel rounded-2xl border border-white/5 bg-[#050505] shadow-xl flex-1 flex flex-col overflow-hidden">
            {/* Header */}
            <div className="bg-[#050505] border-b border-white/5 px-5 py-4 flex justify-between items-center shrink-0">
                <h3 className="text-sm font-semibold flex items-center text-white">
                    <SearchCode className="text-brand-cyan mr-2 w-5 h-5" />
                    Reasoner Verifier
                </h3>
                {showAnalyzing ? (
                    <div className="flex items-center space-x-2">
                        <Loader2 className="text-brand-cyan animate-spin w-4 h-4" />
                        <span className="text-[10px] font-mono text-brand-cyan tracking-widest">ANALYZING...</span>
                    </div>
                ) : (
                    <span className="text-[10px] font-mono bg-[#2a2a2a] text-slate-400 px-3 py-1 rounded-full">
                        {latestRisk ? 'COMPLETE' : 'STANDBY'}
                    </span>
                )}
            </div>

            <div className="flex-1 overflow-y-auto p-5 space-y-4">
                {/* Currently Analyzing Clip */}
                {currentChunk && (
                    <div className="relative rounded-2xl border border-white/5 overflow-hidden bg-[#0a0a0a]">
                        {isAnalyzing && (
                            <div className="absolute inset-0 video-overlay-grid pointer-events-none opacity-30"></div>
                        )}
                        <div className="aspect-video flex items-center justify-center relative">
                            {showAnalyzing ? (
                                <>
                                    {/* Scanning overlay */}
                                    <div className="absolute inset-0 video-overlay-grid opacity-20"></div>
                                    <div className="absolute inset-0 pointer-events-none">
                                        <div className="w-full h-1 bg-brand-cyan/50 absolute top-0 left-0 animate-scanline" style={{ boxShadow: '0 0 15px rgba(6,182,212,0.8)' }}></div>
                                    </div>
                                    <div className="text-center z-10">
                                        <Loader2 className="w-10 h-10 text-brand-cyan animate-spin mb-3 mx-auto" />
                                        <span className="text-sm font-mono text-brand-cyan tracking-widest">ANALYZING FEED</span>
                                        <div className="text-[10px] font-mono text-slate-500 mt-1">
                                            {fmtTime(currentChunk.start_ts)} → {fmtTime(currentChunk.end_ts)}
                                        </div>
                                    </div>
                                </>
                            ) : latestRisk ? (
                                <div className="text-center z-10 p-6 w-full">
                                    <div className={`text-5xl font-bold font-mono mb-2 ${latestRisk.score >= 0.7 ? 'text-brand-crimson' :
                                        latestRisk.score >= 0.4 ? 'text-brand-amber' : 'text-brand-emerald'
                                        }`}>
                                        {(latestRisk.score * 100).toFixed(0)}%
                                    </div>
                                    <div className="text-xs font-mono text-slate-400">{latestRisk.classification}</div>
                                </div>
                            ) : (
                                <div className="text-center">
                                    <Eye className="w-10 h-10 text-slate-600 mb-2 mx-auto" />
                                    <span className="text-xs text-slate-600 font-mono">AWAITING FEED</span>
                                </div>
                            )}
                        </div>
                    </div>
                )}

                {/* Reasoner Tool Calls */}
                {reasonerActivity.length > 0 && (
                    <div>
                        <div className="text-[10px] font-mono text-slate-500 mb-2 pb-2">
                            REASONER TOOL CALLS
                        </div>
                        <div className="space-y-1 max-h-32 overflow-y-auto">
                            {reasonerActivity.slice(-6).map((entry, i) => (
                                <div key={i} className="text-[10px] font-mono text-slate-400 flex items-start gap-2 agent-entry">
                                    <Terminal className="text-brand-cyan w-3 h-3 mt-0.5 shrink-0" />
                                    <span>{entry.text}</span>
                                </div>
                            ))}
                        </div>
                    </div>
                )}

                {/* Latest Result JSON */}
                {latestRisk && (
                    <div>
                        <div className="text-[10px] font-mono text-slate-500 mb-2 pb-2 flex justify-between">
                            <span>FINAL JSON OUTPUT</span>
                            <span className={`font-bold ${latestRisk.score >= 0.7 ? 'text-brand-crimson' : latestRisk.score >= 0.4 ? 'text-brand-amber' : 'text-brand-emerald'
                                }`}>
                                {(latestRisk.score * 100).toFixed(1)}%
                            </span>
                        </div>
                        <div className="bg-black/50 p-4 rounded-xl font-mono text-[10px] overflow-x-auto">
                            <pre className="text-brand-cyan whitespace-pre-wrap">
                                {JSON.stringify({
                                    score: latestRisk.score,
                                    classification: latestRisk.classification,
                                    reasoning: latestRisk.reasoning,
                                    action_required: latestRisk.action_required,
                                }, null, 2)}
                            </pre>
                        </div>
                        {latestRisk.tool_less && (
                            <div className="mt-2 text-[10px] font-mono bg-brand-amber/10 text-brand-amber rounded-xl p-3 flex items-center gap-2">
                                <Zap className="w-4 h-4" />
                                Generated in TOOL-LESS mode (race condition fallback)
                            </div>
                        )}
                    </div>
                )}

                {/* Empty state */}
                {!currentChunk && !latestRisk && (
                    <div className="text-slate-600 text-center py-12">
                        <EyeOff className="w-10 h-10 mb-3 mx-auto opacity-30" />
                        <div className="text-sm">Verifier is on standby</div>
                        <div className="text-xs text-slate-700 mt-1">Upload a video to begin analysis</div>
                    </div>
                )}
            </div>
        </div>
    )
}
