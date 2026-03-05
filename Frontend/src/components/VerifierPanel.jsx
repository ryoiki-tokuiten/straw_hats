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
        <div className="glass-panel rounded-xl border border-slate-700/50 flex-1 flex flex-col overflow-hidden">
            {/* Header */}
            <div className="bg-slate-900/80 px-4 py-2 border-b border-slate-800 flex justify-between items-center shrink-0">
                <h3 className="text-sm font-semibold flex items-center text-white">
                    <i className="ph-fill ph-magnifying-glass-plus text-brand-cyan mr-2 text-lg"></i>
                    Reasoner Verifier
                </h3>
                {showAnalyzing ? (
                    <div className="flex items-center space-x-2">
                        <i className="ph ph-spinner-gap text-brand-cyan animate-spin"></i>
                        <span className="text-[10px] font-mono text-brand-cyan tracking-widest">ANALYZING...</span>
                    </div>
                ) : (
                    <span className="text-[10px] font-mono bg-slate-800 text-slate-400 px-2 py-0.5 rounded border border-slate-700">
                        {latestRisk ? 'COMPLETE' : 'STANDBY'}
                    </span>
                )}
            </div>

            <div className="flex-1 overflow-y-auto p-4 space-y-4">
                {/* Currently Analyzing Clip */}
                {currentChunk && (
                    <div className="relative rounded-lg overflow-hidden bg-black/50 border border-slate-700">
                        <div className="aspect-video flex items-center justify-center relative">
                            {showAnalyzing ? (
                                <>
                                    {/* Scanning overlay */}
                                    <div className="absolute inset-0 video-overlay-grid opacity-20"></div>
                                    <div className="absolute inset-0 pointer-events-none">
                                        <div className="w-full h-1 bg-brand-cyan/50 absolute top-0 left-0 animate-scanline" style={{ boxShadow: '0 0 15px rgba(6,182,212,0.8)' }}></div>
                                    </div>
                                    <div className="text-center z-10">
                                        <i className="ph ph-spinner-gap text-4xl text-brand-cyan animate-spin mb-3 block"></i>
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
                                    <i className="ph ph-eye text-4xl text-slate-600 mb-2 block"></i>
                                    <span className="text-xs text-slate-600 font-mono">AWAITING FEED</span>
                                </div>
                            )}
                        </div>
                    </div>
                )}

                {/* Reasoner Tool Calls */}
                {reasonerActivity.length > 0 && (
                    <div>
                        <div className="text-[10px] font-mono text-slate-500 mb-2 border-b border-slate-800 pb-1">
                            REASONER TOOL CALLS
                        </div>
                        <div className="space-y-1 max-h-32 overflow-y-auto">
                            {reasonerActivity.slice(-6).map((entry, i) => (
                                <div key={i} className="text-[10px] font-mono text-slate-400 flex items-start gap-2 agent-entry">
                                    <i className="ph ph-terminal text-brand-cyan mt-0.5 shrink-0"></i>
                                    <span>{entry.text}</span>
                                </div>
                            ))}
                        </div>
                    </div>
                )}

                {/* Latest Result JSON */}
                {latestRisk && (
                    <div>
                        <div className="text-[10px] font-mono text-slate-500 mb-2 border-b border-slate-800 pb-1 flex justify-between">
                            <span>FINAL JSON OUTPUT</span>
                            <span className={`font-bold ${latestRisk.score >= 0.7 ? 'text-brand-crimson' : latestRisk.score >= 0.4 ? 'text-brand-amber' : 'text-brand-emerald'
                                }`}>
                                {(latestRisk.score * 100).toFixed(1)}%
                            </span>
                        </div>
                        <div className="bg-black/50 p-3 rounded border border-slate-800 font-mono text-[10px] overflow-x-auto">
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
                            <div className="mt-2 text-[10px] font-mono bg-brand-amber/10 text-brand-amber border border-brand-amber/30 rounded p-2 flex items-center gap-2">
                                <i className="ph ph-lightning"></i>
                                Generated in TOOL-LESS mode (race condition fallback)
                            </div>
                        )}
                    </div>
                )}

                {/* Empty state */}
                {!currentChunk && !latestRisk && (
                    <div className="text-slate-600 text-center py-12">
                        <i className="ph ph-eye-slash text-4xl mb-3 block opacity-30"></i>
                        <div className="text-sm">Verifier is on standby</div>
                        <div className="text-xs text-slate-700 mt-1">Upload a video to begin analysis</div>
                    </div>
                )}
            </div>
        </div>
    )
}
