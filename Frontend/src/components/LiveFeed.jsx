import { useRef, useState, useCallback } from 'react'
import { Video, Loader2, UploadCloud } from 'lucide-react'

export default function LiveFeed({
    videoUrl, videoInfo, currentChunk, uploading,
    onUpload, fileInputRef, onFileChange, onDrop,
    isProcessing, completedChunks, totalChunks, fmtTime
}) {
    const [dragOver, setDragOver] = useState(false)

    const handleDragOver = useCallback((e) => {
        e.preventDefault()
        setDragOver(true)
    }, [])

    const handleDragLeave = useCallback(() => setDragOver(false), [])

    const handleDrop = useCallback((e) => {
        setDragOver(false)
        onDrop(e)
    }, [onDrop])

    return (
        <div className="glass-panel rounded-2xl overflow-hidden shadow-2xl flex flex-col bg-[#050505] border border-white/5">
            {/* Header */}
            <div className="bg-[#050505] px-5 py-4 border-b border-white/5 flex justify-between items-center">
                <div className="flex items-center space-x-2">
                    <div className={`w-2 h-2 rounded-full ${isProcessing ? 'bg-brand-cyan animate-pulse' : videoUrl ? 'bg-brand-emerald' : 'bg-slate-600'}`}></div>
                    <span className="text-xs font-semibold tracking-wider text-slate-300 flex items-center">
                        <Video className="w-4 h-4 mr-2" />
                        LIVE FEED
                    </span>
                    {currentChunk && (
                        <span className="text-[10px] font-mono bg-brand-cyan/20 text-brand-cyan px-3 py-1 rounded-full">
                            CHUNK {currentChunk.chunk_index} • {fmtTime(currentChunk.start_ts)} → {fmtTime(currentChunk.end_ts)}
                        </span>
                    )}
                </div>
                {isProcessing && (
                    <div className="flex items-center space-x-2">
                        <Loader2 className="w-4 h-4 text-brand-cyan animate-spin" />
                        <span className="text-[10px] font-mono text-brand-cyan">PROCESSING</span>
                    </div>
                )}
            </div>

            {/* Video Area */}
            <div className="relative bg-black aspect-video w-full overflow-hidden flex items-center justify-center">
                {videoUrl ? (
                    <>
                        <video
                            src={videoUrl}
                            className="w-full h-full object-cover"
                            controls
                            muted
                            autoPlay
                        />
                        {/* Grid Overlay */}
                        <div className="absolute inset-0 video-overlay-grid opacity-15 pointer-events-none"></div>
                        {/* Scanline */}
                        {isProcessing && (
                            <div className="absolute inset-0 pointer-events-none">
                                <div className="w-full h-1 bg-brand-cyan/50 absolute top-0 left-0 animate-scanline" style={{ boxShadow: '0 0 15px rgba(6,182,212,0.8)' }}></div>
                            </div>
                        )}
                        {/* Status Overlay */}
                        {currentChunk && (
                            <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/80 to-transparent p-4 pointer-events-none">
                                <div className="flex justify-between items-end">
                                    <div>
                                        <div className="text-[10px] font-mono text-slate-400">ANALYZING SEGMENT</div>
                                        <div className="text-sm font-mono text-white">
                                            {fmtTime(currentChunk.start_ts)} → {fmtTime(currentChunk.end_ts)}
                                        </div>
                                    </div>
                                    <div className="text-right">
                                        <div className="text-[10px] font-mono text-slate-400">PROGRESS</div>
                                        <div className="text-sm font-mono text-brand-cyan">
                                            {completedChunks}/{totalChunks}
                                        </div>
                                    </div>
                                </div>
                                {/* Progress bar */}
                                <div className="w-full bg-slate-800/80 rounded-full h-1 mt-2">
                                    <div className="bg-brand-cyan h-1 rounded-full transition-all duration-500"
                                        style={{ width: `${totalChunks > 0 ? (completedChunks / totalChunks * 100) : 0}%` }}
                                    ></div>
                                </div>
                            </div>
                        )}
                        {/* Recording indicator */}
                        <div className="absolute top-3 right-3 flex items-center space-x-2 pointer-events-none">
                            <div className="w-3 h-3 rounded-full bg-brand-crimson animate-blink"></div>
                            <span className="text-[10px] font-mono text-white/80">REC</span>
                        </div>
                    </>
                ) : (
                    /* Upload Zone */
                    <div
                        className={`upload-zone w-full h-full flex flex-col items-center justify-center cursor-pointer ${dragOver ? 'drag-over' : ''}`}
                        onDragOver={handleDragOver}
                        onDragLeave={handleDragLeave}
                        onDrop={handleDrop}
                        onClick={() => fileInputRef.current?.click()}
                    >
                        {uploading ? (
                            <>
                                <Loader2 className="w-12 h-12 text-brand-cyan animate-spin mb-4" />
                                <span className="text-sm font-mono text-brand-cyan tracking-widest">UPLOADING...</span>
                            </>
                        ) : (
                            <>
                                <UploadCloud className="w-12 h-12 text-slate-500 mb-4" />
                                <span className="text-sm font-medium text-slate-400">Drop video file or click to upload</span>
                                <span className="text-xs text-slate-600 mt-2 font-mono">Supports MP4, AVI, MKV, MOV</span>
                            </>
                        )}
                        <input
                            ref={fileInputRef}
                            type="file"
                            accept="video/*"
                            onChange={onFileChange}
                            className="hidden"
                        />
                    </div>
                )}
            </div>

            {/* Chunk Timeline */}
            {totalChunks > 0 && (
                <div className="bg-[#050505] border-t border-white/5 p-5">
                    <div className="text-[10px] font-mono text-slate-500 mb-2">CHUNK TIMELINE</div>
                    <div className="flex gap-1 flex-wrap">
                        {Array.from({ length: totalChunks }, (_, i) => {
                            const isComplete = i < completedChunks
                            const isCurrent = currentChunk?.chunk_index === i
                            return (
                                <div
                                    key={i}
                                    className={`h-2 rounded-full transition-all duration-300 ${isCurrent ? 'bg-brand-cyan animate-pulse w-6' :
                                        isComplete ? 'bg-brand-emerald w-4' :
                                            'bg-slate-700 w-4'
                                        }`}
                                    title={`Chunk ${i}`}
                                ></div>
                            )
                        })}
                    </div>
                </div>
            )}
        </div>
    )
}
