import { useState, useCallback, useEffect, useRef } from 'react'
import { Search, Play, Video, Database, X, Loader2, Edit3 } from 'lucide-react'

export default function SearchPanel() {
    const [query, setQuery] = useState('')
    const [results, setResults] = useState([])
    const [searching, setSearching] = useState(false)
    const [searched, setSearched] = useState(false)
    const [recentRecs, setRecentRecs] = useState([])
    const [loadingRecent, setLoadingRecent] = useState(true)
    const [modalItem, setModalItem] = useState(null)
    const videoRef = useRef(null)

    // Fetch recent reconstructions on mount
    useEffect(() => {
        async function fetchRecent() {
            try {
                const res = await fetch('/api/reconstructions/recent?limit=10')
                const data = await res.json()
                setRecentRecs(data.reconstructions || [])
            } catch (err) {
                console.error('Failed to load recent reconstructions:', err)
            } finally {
                setLoadingRecent(false)
            }
        }
        fetchRecent()
    }, [])

    // Close modal on Escape
    useEffect(() => {
        const onKey = (e) => { if (e.key === 'Escape') setModalItem(null) }
        window.addEventListener('keydown', onKey)
        return () => window.removeEventListener('keydown', onKey)
    }, [])

    const handleSearch = useCallback(async () => {
        if (!query.trim()) return
        setSearching(true)
        setSearched(true)

        try {
            const res = await fetch(`/api/search?q=${encodeURIComponent(query)}`)
            const data = await res.json()
            setResults(data.results || [])
        } catch (err) {
            console.error('Search failed:', err)
            setResults([])
        } finally {
            setSearching(false)
        }
    }, [query])

    const handleKeyPress = (e) => {
        if (e.key === 'Enter') handleSearch()
    }

    const handleClear = () => {
        setQuery('')
        setResults([])
        setSearched(false)
    }

    const fmtTs = (ts) => {
        if (ts === null || ts === undefined) return '--:--'
        const m = Math.floor(ts / 60)
        const s = Math.floor(ts % 60)
        return `${m}:${s.toString().padStart(2, '0')}`
    }

    // Cards used for both recent and search results
    const ResultCard = ({ item, showSimilarity }) => (
        <div
            onClick={() => setModalItem(item)}
            className="bg-[#0a0a0a] border border-white/5 p-5 rounded-3xl transition-all cursor-pointer group hover:shadow-2xl hover:shadow-brand-cyan/10"
        >
            {/* Thumbnail / play hint */}
            <div className="relative w-full aspect-video bg-black/60 rounded-md mb-3 overflow-hidden flex items-center justify-center group-hover:ring-1 group-hover:ring-brand-cyan/40 transition-all">
                <video
                    src={item.chunk_video_url}
                    className="w-full h-full object-cover opacity-70 group-hover:opacity-100 transition-opacity"
                    muted
                    preload="metadata"
                />
                <div className="absolute inset-0 flex items-center justify-center">
                    <div className="w-12 h-12 rounded-full bg-black/60 backdrop-blur-sm flex items-center justify-center group-hover:bg-brand-cyan/20 transition-all group-hover:scale-110">
                        <Play className="text-white w-6 h-6 ml-1" fill="currentColor" />
                    </div>
                </div>
                <div className="absolute bottom-2 right-2 text-[9px] font-mono bg-black/70 text-white px-1.5 py-0.5 rounded">
                    {fmtTs(item.start_ts)} — {fmtTs(item.end_ts)}
                </div>
            </div>

            <div className="flex justify-between items-start mb-2">
                <div className="flex items-center space-x-3">
                    <div className="p-2 bg-slate-800 rounded-xl text-brand-cyan group-hover:bg-brand-cyan/20 transition-colors">
                        <Video className="w-4 h-4" />
                    </div>
                    <div>
                        <div className="text-sm font-semibold text-white">Chunk {item.chunk_index}</div>
                        <div className="text-xs text-slate-400 font-mono">
                            {fmtTs(item.start_ts)} — {fmtTs(item.end_ts)}
                        </div>
                    </div>
                </div>
                {showSimilarity ? (
                    <div className="text-xs font-mono bg-slate-800 px-3 py-1 rounded-full text-brand-cyan">
                        {(item.similarity * 100).toFixed(0)}% match
                    </div>
                ) : (
                    <div className="flex items-center gap-1.5 text-[10px] font-mono bg-brand-emerald/10 text-brand-emerald px-3 py-1 rounded-full">
                        <Database className="w-3 h-3" />
                        EMBEDDED
                    </div>
                )}
            </div>
            <p className="text-[11px] text-slate-400 leading-relaxed line-clamp-3">
                {item.text}
            </p>
        </div>
    )

    return (
        <div className="h-full flex flex-col max-w-5xl mx-auto w-full">
            {/* Hero */}
            <div className="mb-8 mt-4 text-center">
                <h2 className="text-3xl font-bold mb-2 text-white">
                    Semantic <span className="text-brand-cyan">Multi-Modal</span> Search
                </h2>
                <p className="text-slate-400 max-w-2xl mx-auto text-sm">
                    Query the historical database using natural language. The system maps your query to atomic reconstructions
                    using Gemini embeddings and retrieves matching video segments.
                </p>
            </div>

            {/* Search Bar */}
            <div className="relative w-full max-w-3xl mx-auto mb-8 group">
                <div className="absolute -inset-1 bg-gradient-to-r from-brand-cyan to-brand-purple rounded-2xl blur opacity-25 group-hover:opacity-50 transition duration-1000 group-hover:duration-200"></div>
                <div className="relative bg-[#0a0a0a] border border-white/5 flex items-center rounded-2xl p-3 shadow-2xl">
                    <Search className="text-slate-400 ml-3 mr-2 w-5 h-5" />
                    <input
                        type="text"
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                        onKeyPress={handleKeyPress}
                        placeholder="e.g., 'Person lingering near the restricted zone'"
                        className="flex-1 bg-transparent border-none outline-none text-white placeholder-slate-500 text-lg px-2"
                    />
                    {searched && (
                        <button
                            onClick={handleClear}
                            className="text-slate-400 hover:text-white px-2 transition-colors cursor-pointer"
                            title="Clear search"
                        >
                            <X className="w-5 h-5" />
                        </button>
                    )}
                    <button
                        onClick={handleSearch}
                        disabled={searching}
                        className="bg-brand-cyan hover:bg-cyan-500 text-slate-900 font-bold px-8 py-3 rounded-xl transition-colors disabled:opacity-50 cursor-pointer"
                    >
                        {searching ? <Loader2 className="animate-spin w-5 h-5 mx-auto" /> : 'Search'}
                    </button>
                </div>
            </div>

            {/* Results / Recent Embeddings */}
            <div className="flex-1 bg-black/20 rounded-3xl p-8 overflow-y-auto">
                {searched ? (
                    <>
                        <h3 className="text-sm font-semibold text-slate-400 mb-4 uppercase tracking-wider flex items-center justify-between">
                            <span>{results.length} Result{results.length !== 1 ? 's' : ''}</span>
                            <button onClick={handleClear} className="text-[10px] text-brand-cyan hover:text-white transition-colors cursor-pointer font-mono">
                                ← BACK TO INDEX
                            </button>
                        </h3>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            {results.length === 0 ? (
                                <div className="col-span-2 flex flex-col items-center justify-center py-20 text-slate-500">
                                    <Search className="w-10 h-10 mb-4 opacity-30" />
                                    <p>No matching events found.</p>
                                </div>
                            ) : results.map((res, i) => (
                                <ResultCard key={i} item={res} showSimilarity={true} />
                            ))}
                        </div>
                    </>
                ) : (
                    <>
                        <h3 className="text-sm font-semibold text-slate-400 mb-1 uppercase tracking-wider flex items-center gap-2">
                            <Database className="text-brand-emerald w-4 h-4" />
                            Embedding Index
                        </h3>
                        <p className="text-[11px] text-slate-600 mb-4 font-mono">
                            Recent atomic reconstructions with stored vector embeddings — click to play
                        </p>
                        {loadingRecent ? (
                            <div className="flex flex-col items-center justify-center py-20 text-slate-500">
                                <Loader2 className="w-8 h-8 animate-spin mb-3 text-brand-cyan" />
                                <span className="text-xs font-mono">Loading embedding index...</span>
                            </div>
                        ) : recentRecs.length === 0 ? (
                            <div className="flex flex-col items-center justify-center py-20 text-slate-500">
                                <Database className="w-10 h-10 mb-4 opacity-30" />
                                <p className="text-sm mb-1">No embeddings stored yet</p>
                                <p className="text-[10px] text-slate-700 font-mono">Process a video to populate the behavioral index</p>
                            </div>
                        ) : (
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                {recentRecs.map((rec, i) => (
                                    <ResultCard key={i} item={rec} showSimilarity={false} />
                                ))}
                            </div>
                        )}
                    </>
                )}
            </div>

            {/* ═══ FULLSCREEN VIDEO MODAL ═══ */}
            {modalItem && (
                <div
                    className="fixed inset-0 z-[100] bg-black/90 backdrop-blur-md flex items-center justify-center p-4 animate-fade-in"
                    onClick={(e) => { if (e.target === e.currentTarget) setModalItem(null) }}
                >
                    <div className="relative w-full max-w-5xl bg-[#050505] border border-white/10 rounded-3xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">

                        {/* Modal Header */}
                        <div className="flex items-center justify-between border-b border-white/5 px-6 py-5 shrink-0">
                            <div className="flex items-center gap-4">
                                <div className="p-3 bg-brand-cyan/10 rounded-2xl">
                                    <Video className="text-brand-cyan w-6 h-6" />
                                </div>
                                <div>
                                    <div className="text-white font-semibold">
                                        Chunk {modalItem.chunk_index} — Video Feed
                                    </div>
                                    <div className="text-xs font-mono text-slate-400">
                                        {fmtTs(modalItem.start_ts)} → {fmtTs(modalItem.end_ts)}
                                        <span className="mx-2 text-slate-600">•</span>
                                        <span className="text-slate-500">{modalItem.video_id?.slice(0, 8)}...</span>
                                    </div>
                                </div>
                            </div>
                            <button
                                onClick={() => setModalItem(null)}
                                className="w-10 h-10 rounded-full bg-slate-800 hover:bg-slate-700 flex items-center justify-center text-slate-400 hover:text-white transition-colors cursor-pointer"
                            >
                                <X className="w-5 h-5" />
                            </button>
                        </div>

                        {/* Video Player */}
                        <div className="bg-black flex items-center justify-center">
                            <video
                                ref={videoRef}
                                src={modalItem.chunk_video_url}
                                className="w-full max-h-[60vh] object-contain"
                                controls
                                autoPlay
                            />
                        </div>

                        {/* Reconstruction Text */}
                        <div className="px-6 py-5 shrink-0 overflow-y-auto max-h-40">
                            <div className="flex items-center gap-2 mb-3">
                                <Edit3 className="text-brand-emerald w-4 h-4" />
                                <span className="text-[10px] font-mono text-brand-emerald font-bold tracking-wider">ATOMIC RECONSTRUCTION</span>
                            </div>
                            <p className="text-sm text-slate-300 leading-relaxed">
                                {modalItem.text}
                            </p>
                        </div>
                    </div>
                </div>
            )}
        </div>
    )
}
