import { Zap } from 'lucide-react'

export default function RaceConditionBar({ raceConditions, currentChunk }) {
    const latest = raceConditions[raceConditions.length - 1]
    if (!latest) return null

    const pendingCount = latest.pending_count || 0
    const isToolLess = latest.tool_less || false

    return (
        <div className={`px-6 py-3 flex items-center justify-between shrink-0 transition-all duration-300 ${isToolLess
            ? 'bg-brand-crimson/10'
            : 'bg-brand-amber/10'
            }`}>
            <div className="flex items-center space-x-3">
                <Zap className={`w-5 h-5 race-indicator ${isToolLess ? 'text-brand-crimson' : 'text-brand-amber'}`} />
                <div>
                    <div className={`text-xs font-bold ${isToolLess ? 'text-brand-crimson' : 'text-brand-amber'}`}>
                        {isToolLess ? 'TOOL-LESS MODE ACTIVE' : 'RACE CONDITION DETECTED'}
                    </div>
                    <div className="text-[10px] font-mono text-slate-400">
                        {latest.message}
                    </div>
                </div>
            </div>

            <div className="flex items-center space-x-4">
                {/* Pending count */}
                <div className="flex items-center space-x-2">
                    <span className="text-[10px] font-mono text-slate-500">PENDING</span>
                    <div className="flex gap-1">
                        {Array.from({ length: 3 }, (_, i) => (
                            <div
                                key={i}
                                className={`w-3 h-3 rounded-sm transition-all ${i < pendingCount
                                    ? (isToolLess ? 'bg-brand-crimson' : 'bg-brand-amber')
                                    : 'bg-slate-700'
                                    }`}
                            ></div>
                        ))}
                    </div>
                </div>

                {/* Max indicator */}
                {isToolLess && (
                    <span className="text-[9px] font-mono bg-brand-crimson/30 text-brand-crimson px-2 py-0.5 rounded font-bold animate-pulse">
                        6 MIN BEHIND — FORCING OUTPUT
                    </span>
                )}
            </div>
        </div>
    )
}
