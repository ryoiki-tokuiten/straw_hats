import { useState, useEffect, useRef, useCallback } from 'react'

export default function FacesPanel() {
    // ── Familiar Faces State ──
    const [faces, setFaces] = useState([])
    const [faceName, setFaceName] = useState('')
    const [faceFile, setFaceFile] = useState(null)
    const [facePreview, setFacePreview] = useState(null)
    const [faceUploading, setFaceUploading] = useState(false)
    const [faceError, setFaceError] = useState(null)
    const [faceSuccess, setFaceSuccess] = useState(null)
    const faceInputRef = useRef(null)

    // ── Danger Zone State ──
    const [dzDescription, setDzDescription] = useState('')
    const [dzFiles, setDzFiles] = useState([])
    const [dzPreviews, setDzPreviews] = useState([])
    const [dzExistingImages, setDzExistingImages] = useState([])
    const [dzSaving, setDzSaving] = useState(false)
    const [dzError, setDzError] = useState(null)
    const [dzSuccess, setDzSuccess] = useState(null)
    const [dzLoaded, setDzLoaded] = useState(false)
    const dzInputRef = useRef(null)

    // ── Image Lightbox State ──
    const [lightboxImage, setLightboxImage] = useState(null) // { url, title }

    // ── Load data on mount ──
    useEffect(() => {
        fetchFaces()
        fetchDangerZone()
    }, [])

    // Close lightbox on Escape
    useEffect(() => {
        const onKey = (e) => { if (e.key === 'Escape') setLightboxImage(null) }
        window.addEventListener('keydown', onKey)
        return () => window.removeEventListener('keydown', onKey)
    }, [])

    // ── Familiar Faces API ──
    const fetchFaces = async () => {
        try {
            const res = await fetch('/api/faces')
            const data = await res.json()
            setFaces(data.faces || [])
        } catch (e) { console.error('Failed to fetch faces:', e) }
    }

    const handleFaceFileChange = (e) => {
        const file = e.target.files?.[0]
        if (file) {
            setFaceFile(file)
            setFacePreview(URL.createObjectURL(file))
            setFaceError(null)
        }
    }

    const handleFaceUpload = async () => {
        if (!faceName.trim()) { setFaceError('Please enter a name'); return }
        if (!faceFile) { setFaceError('Please select an image'); return }

        setFaceUploading(true)
        setFaceError(null)
        setFaceSuccess(null)

        const formData = new FormData()
        formData.append('file', faceFile)

        try {
            const res = await fetch(`/api/faces?name=${encodeURIComponent(faceName.trim())}`, {
                method: 'POST',
                body: formData,
            })
            const data = await res.json()
            if (!res.ok) throw new Error(data.error || 'Upload failed')

            setFaceSuccess(`"${faceName}" registered successfully!`)
            setFaceName('')
            setFaceFile(null)
            setFacePreview(null)
            if (faceInputRef.current) faceInputRef.current.value = ''
            fetchFaces()
            setTimeout(() => setFaceSuccess(null), 3000)
        } catch (e) {
            setFaceError(e.message)
        } finally {
            setFaceUploading(false)
        }
    }

    const handleFaceDelete = async (id, name) => {
        if (!confirm(`Remove "${name}" from familiar faces?`)) return
        try {
            await fetch(`/api/faces/${id}`, { method: 'DELETE' })
            fetchFaces()
        } catch (e) { console.error('Delete failed:', e) }
    }

    const handleFaceDrop = useCallback((e) => {
        e.preventDefault()
        e.stopPropagation()
        const file = e.dataTransfer?.files?.[0]
        if (file && file.type.startsWith('image/')) {
            setFaceFile(file)
            setFacePreview(URL.createObjectURL(file))
            setFaceError(null)
        }
    }, [])

    // ── Danger Zone API ──
    const fetchDangerZone = async () => {
        try {
            const res = await fetch('/api/danger-zone')
            const data = await res.json()
            if (data.config) {
                setDzDescription(data.config.description || '')
                setDzExistingImages(data.config.image_urls || [])
            }
            setDzLoaded(true)
        } catch (e) { console.error('Failed to fetch danger zone:', e) }
    }

    const handleDzFileChange = (e) => {
        const newFiles = Array.from(e.target.files || [])
        const totalCount = dzFiles.length + dzExistingImages.length + newFiles.length
        if (totalCount > 3) {
            setDzError('Maximum 3 images allowed')
            return
        }
        const combined = [...dzFiles, ...newFiles]
        setDzFiles(combined)
        setDzPreviews(combined.map(f => URL.createObjectURL(f)))
        setDzError(null)
    }

    const removeDzNewImage = (index) => {
        const updated = dzFiles.filter((_, i) => i !== index)
        setDzFiles(updated)
        setDzPreviews(updated.map(f => URL.createObjectURL(f)))
    }

    const handleDzSave = async () => {
        setDzSaving(true)
        setDzError(null)
        setDzSuccess(null)

        const formData = new FormData()
        dzFiles.forEach(f => formData.append('files', f))

        try {
            const res = await fetch(`/api/danger-zone?description=${encodeURIComponent(dzDescription)}`, {
                method: 'POST',
                body: formData,
            })
            const data = await res.json()
            if (!res.ok) throw new Error(data.error || 'Save failed')

            setDzSuccess('Danger zone configuration saved!')
            setDzFiles([])
            setDzPreviews([])
            if (dzInputRef.current) dzInputRef.current.value = ''
            fetchDangerZone()
            setTimeout(() => setDzSuccess(null), 3000)
        } catch (e) {
            setDzError(e.message)
        } finally {
            setDzSaving(false)
        }
    }

    const handleDzClear = async () => {
        if (!confirm('Clear all danger zone configuration? This cannot be undone.')) return
        try {
            await fetch('/api/danger-zone', { method: 'DELETE' })
            setDzDescription('')
            setDzFiles([])
            setDzPreviews([])
            setDzExistingImages([])
            setDzSuccess('Danger zone cleared')
            setTimeout(() => setDzSuccess(null), 3000)
        } catch (e) { console.error('Clear failed:', e) }
    }

    return (
        <div className="space-y-6 max-w-6xl mx-auto">
            {/* ═══ SECTION HEADER ═══ */}
            <div className="flex items-center gap-3 mb-2">
                <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-brand-cyan/30 to-brand-purple/30 border border-brand-cyan/20 flex items-center justify-center">
                    <i className="ph ph-user-focus text-xl text-brand-cyan"></i>
                </div>
                <div>
                    <h2 className="text-xl font-bold text-white">Familiar Faces & Danger Zone</h2>
                    <p className="text-xs text-slate-400">Register known faces for automatic recognition • Define danger zone criteria for threat detection</p>
                </div>
            </div>

            {/* ═══ FAMILIAR FACES SECTION ═══ */}
            <div className="glass-panel rounded-xl p-6">
                <div className="flex items-center gap-2 mb-5">
                    <i className="ph ph-users-three text-brand-cyan text-lg"></i>
                    <h3 className="text-lg font-semibold text-white">Familiar Faces</h3>
                    <span className="ml-auto text-xs text-slate-500 font-mono">{faces.length} registered</span>
                </div>

                {/* Upload Form */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
                    {/* Image Upload */}
                    <div
                        className="relative group cursor-pointer border-2 border-dashed border-slate-700 hover:border-brand-cyan rounded-xl flex flex-col items-center justify-center p-6 transition-all duration-300 min-h-[180px]"
                        onClick={() => faceInputRef.current?.click()}
                        onDragOver={(e) => e.preventDefault()}
                        onDrop={handleFaceDrop}
                    >
                        {facePreview ? (
                            <div className="relative w-full h-full flex items-center justify-center">
                                <img src={facePreview} alt="Preview" className="max-h-40 rounded-lg object-cover shadow-lg shadow-brand-cyan/10" />
                                <button
                                    onClick={(e) => {
                                        e.stopPropagation()
                                        setFaceFile(null)
                                        setFacePreview(null)
                                        if (faceInputRef.current) faceInputRef.current.value = ''
                                    }}
                                    className="absolute top-1 right-1 w-6 h-6 bg-slate-800 hover:bg-brand-crimson rounded-full flex items-center justify-center transition-colors"
                                >
                                    <i className="ph ph-x text-xs text-white"></i>
                                </button>
                            </div>
                        ) : (
                            <>
                                <div className="w-14 h-14 rounded-full bg-slate-800 group-hover:bg-brand-cyan/20 border border-slate-700 group-hover:border-brand-cyan/40 flex items-center justify-center transition-all duration-300 mb-3">
                                    <i className="ph ph-camera text-2xl text-slate-400 group-hover:text-brand-cyan transition-colors"></i>
                                </div>
                                <p className="text-sm text-slate-400 group-hover:text-slate-300 transition-colors">Drop photo or click to browse</p>
                                <p className="text-xs text-slate-600 mt-1">Clear frontal face photo works best</p>
                            </>
                        )}
                        <input ref={faceInputRef} type="file" accept="image/*" onChange={handleFaceFileChange} className="hidden" />
                    </div>

                    {/* Name + Submit */}
                    <div className="flex flex-col justify-center gap-4">
                        <div>
                            <label className="block text-xs text-slate-400 mb-1.5 font-medium uppercase tracking-wider">Person's Name</label>
                            <input
                                type="text"
                                value={faceName}
                                onChange={(e) => setFaceName(e.target.value)}
                                placeholder="e.g. John Doe"
                                className="w-full bg-slate-800/80 border border-slate-700 rounded-lg px-4 py-3 text-white placeholder-slate-500 focus:outline-none focus:border-brand-cyan focus:ring-1 focus:ring-brand-cyan/30 transition-all"
                                onKeyDown={(e) => e.key === 'Enter' && handleFaceUpload()}
                            />
                        </div>
                        <button
                            onClick={handleFaceUpload}
                            disabled={faceUploading || !faceFile || !faceName.trim()}
                            className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-gradient-to-r from-brand-cyan to-brand-cyan/80 hover:from-brand-cyan/90 hover:to-brand-cyan/70 disabled:from-slate-700 disabled:to-slate-700 disabled:text-slate-500 text-white font-semibold rounded-lg transition-all duration-300 shadow-lg shadow-brand-cyan/20 disabled:shadow-none cursor-pointer disabled:cursor-not-allowed"
                        >
                            {faceUploading ? (
                                <>
                                    <i className="ph ph-spinner-gap animate-spin"></i>
                                    Processing with ArcFace...
                                </>
                            ) : (
                                <>
                                    <i className="ph ph-user-plus"></i>
                                    Register Face
                                </>
                            )}
                        </button>

                        {/* Status Messages */}
                        {faceError && (
                            <div className="flex items-center gap-2 text-brand-crimson text-sm bg-brand-crimson/10 border border-brand-crimson/20 rounded-lg px-3 py-2">
                                <i className="ph ph-warning-circle"></i> {faceError}
                            </div>
                        )}
                        {faceSuccess && (
                            <div className="flex items-center gap-2 text-brand-emerald text-sm bg-brand-emerald/10 border border-brand-emerald/20 rounded-lg px-3 py-2 animate-fade-in">
                                <i className="ph ph-check-circle"></i> {faceSuccess}
                            </div>
                        )}
                    </div>
                </div>

                {/* Registered Faces Grid */}
                {faces.length > 0 ? (
                    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3">
                        {faces.map((face) => (
                            <div
                                key={face.id}
                                className="group relative bg-slate-800/60 hover:bg-slate-800 border border-slate-700/50 hover:border-brand-cyan/30 rounded-xl p-3 transition-all duration-300"
                            >
                                <div
                                    className="aspect-square rounded-lg overflow-hidden mb-2 bg-slate-900 cursor-pointer"
                                    onClick={() => face.image_url && setLightboxImage({ url: face.image_url, title: face.name })}
                                >
                                    {face.image_url ? (
                                        <img
                                            src={face.image_url}
                                            alt={face.name}
                                            className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
                                        />
                                    ) : (
                                        <div className="w-full h-full flex items-center justify-center">
                                            <i className="ph ph-user text-3xl text-slate-600"></i>
                                        </div>
                                    )}
                                </div>
                                <p className="text-sm font-medium text-white truncate" title={face.name}>{face.name}</p>
                                <p className="text-[10px] text-slate-500 font-mono mt-0.5">
                                    {new Date(face.created_at).toLocaleDateString()}
                                </p>

                                {/* Delete button */}
                                <button
                                    onClick={() => handleFaceDelete(face.id, face.name)}
                                    className="absolute top-2 right-2 w-6 h-6 bg-slate-900/80 hover:bg-brand-crimson rounded-full flex items-center justify-center opacity-0 group-hover:opacity-100 transition-all duration-200 cursor-pointer"
                                    title="Remove face"
                                >
                                    <i className="ph ph-trash text-xs text-white"></i>
                                </button>
                            </div>
                        ))}
                    </div>
                ) : (
                    <div className="text-center py-10 text-slate-500">
                        <i className="ph ph-user-circle-dashed text-4xl mb-2 block"></i>
                        <p className="text-sm">No familiar faces registered yet</p>
                        <p className="text-xs text-slate-600 mt-1">Upload photos above to enable face recognition in the pipeline</p>
                    </div>
                )}
            </div>

            {/* ═══ DANGER ZONE SECTION ═══ */}
            <div className="glass-panel rounded-xl p-6 border-t-2 border-brand-crimson/40">
                <div className="flex items-center gap-2 mb-5">
                    <i className="ph ph-warning-diamond text-brand-crimson text-lg"></i>
                    <h3 className="text-lg font-semibold text-white">Danger Zone</h3>
                    <span className="ml-2 text-[10px] bg-brand-crimson/20 text-brand-crimson px-2 py-0.5 rounded-full font-medium uppercase tracking-wider">
                        High Priority
                    </span>
                </div>
                <p className="text-sm text-slate-400 mb-5">
                    Define what constitutes a danger zone or dangerous behavior. This context is injected into the AI agent's system prompt with highest priority.
                </p>

                {/* Description */}
                <div className="mb-5">
                    <label className="block text-xs text-slate-400 mb-1.5 font-medium uppercase tracking-wider">
                        Danger Zone Description
                    </label>
                    <textarea
                        value={dzDescription}
                        onChange={(e) => setDzDescription(e.target.value)}
                        placeholder="Describe what should be considered dangerous. Example: 'Any person entering the restricted area marked by yellow tape near the warehouse door. Any person carrying weapons or sharp objects. Vehicles parked in the no-parking zone near the main entrance.'"
                        rows={4}
                        className="w-full bg-slate-800/80 border border-slate-700 rounded-lg px-4 py-3 text-white placeholder-slate-500 focus:outline-none focus:border-brand-crimson focus:ring-1 focus:ring-brand-crimson/30 transition-all resize-none text-sm"
                    />
                </div>

                {/* Image Upload */}
                <div className="mb-5">
                    <label className="block text-xs text-slate-400 mb-1.5 font-medium uppercase tracking-wider">
                        Reference Images <span className="text-slate-600">(max 3)</span>
                    </label>

                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-3">
                        {/* Existing images */}
                        {dzExistingImages.map((url, i) => (
                            <div
                                key={`existing-${i}`}
                                className="relative aspect-video rounded-lg overflow-hidden bg-slate-900 border border-slate-700 group cursor-pointer"
                                onClick={() => setLightboxImage({ url, title: `Danger Zone Reference ${i + 1}` })}
                            >
                                <img src={url} alt={`Danger zone ${i + 1}`} className="w-full h-full object-cover" />
                                <div className="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
                                <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
                                    <div className="w-8 h-8 rounded-full bg-black/50 backdrop-blur-sm flex items-center justify-center border border-white/20">
                                        <i className="ph ph-arrows-out text-white text-sm"></i>
                                    </div>
                                </div>
                                <span className="absolute bottom-1 left-2 text-[10px] text-slate-300 font-mono opacity-0 group-hover:opacity-100 transition-opacity">Saved</span>
                            </div>
                        ))}

                        {/* New preview images */}
                        {dzPreviews.map((url, i) => (
                            <div
                                key={`new-${i}`}
                                className="relative aspect-video rounded-lg overflow-hidden bg-slate-900 border border-brand-amber/30 group cursor-pointer"
                                onClick={() => setLightboxImage({ url, title: `New Reference ${i + 1}` })}
                            >
                                <img src={url} alt={`New ${i + 1}`} className="w-full h-full object-cover" />
                                <button
                                    onClick={(e) => { e.stopPropagation(); removeDzNewImage(i) }}
                                    className="absolute top-1 right-1 w-5 h-5 bg-slate-900/80 hover:bg-brand-crimson rounded-full flex items-center justify-center opacity-0 group-hover:opacity-100 transition-all cursor-pointer"
                                >
                                    <i className="ph ph-x text-[10px] text-white"></i>
                                </button>
                                <span className="absolute bottom-1 left-2 text-[10px] text-brand-amber font-mono opacity-0 group-hover:opacity-100 transition-opacity">New</span>
                            </div>
                        ))}

                        {/* Add more button */}
                        {(dzExistingImages.length + dzFiles.length) < 3 && (
                            <button
                                onClick={() => dzInputRef.current?.click()}
                                className="aspect-video rounded-lg border-2 border-dashed border-slate-700 hover:border-brand-crimson/50 flex flex-col items-center justify-center gap-1 transition-all cursor-pointer group"
                            >
                                <i className="ph ph-plus text-xl text-slate-500 group-hover:text-brand-crimson transition-colors"></i>
                                <span className="text-xs text-slate-500 group-hover:text-brand-crimson transition-colors">Add Image</span>
                            </button>
                        )}
                    </div>
                    <input ref={dzInputRef} type="file" accept="image/*" multiple onChange={handleDzFileChange} className="hidden" />
                </div>

                {/* Status Messages */}
                {dzError && (
                    <div className="flex items-center gap-2 text-brand-crimson text-sm bg-brand-crimson/10 border border-brand-crimson/20 rounded-lg px-3 py-2 mb-4">
                        <i className="ph ph-warning-circle"></i> {dzError}
                    </div>
                )}
                {dzSuccess && (
                    <div className="flex items-center gap-2 text-brand-emerald text-sm bg-brand-emerald/10 border border-brand-emerald/20 rounded-lg px-3 py-2 mb-4 animate-fade-in">
                        <i className="ph ph-check-circle"></i> {dzSuccess}
                    </div>
                )}

                {/* Actions */}
                <div className="flex items-center gap-3">
                    <button
                        onClick={handleDzSave}
                        disabled={dzSaving || (!dzDescription.trim() && dzFiles.length === 0)}
                        className="flex items-center gap-2 px-5 py-2.5 bg-gradient-to-r from-brand-crimson to-brand-crimson/80 hover:from-brand-crimson/90 hover:to-brand-crimson/70 disabled:from-slate-700 disabled:to-slate-700 disabled:text-slate-500 text-white font-semibold rounded-lg transition-all duration-300 shadow-lg shadow-brand-crimson/20 disabled:shadow-none cursor-pointer disabled:cursor-not-allowed"
                    >
                        {dzSaving ? (
                            <>
                                <i className="ph ph-spinner-gap animate-spin"></i>
                                Saving...
                            </>
                        ) : (
                            <>
                                <i className="ph ph-floppy-disk"></i>
                                Save Configuration
                            </>
                        )}
                    </button>
                    {(dzDescription || dzExistingImages.length > 0) && (
                        <button
                            onClick={handleDzClear}
                            className="flex items-center gap-2 px-4 py-2.5 bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white rounded-lg transition-all border border-slate-700 cursor-pointer"
                        >
                            <i className="ph ph-trash"></i>
                            Clear All
                        </button>
                    )}
                </div>
            </div>
            {/* ═══ FULLSCREEN IMAGE LIGHTBOX ═══ */}
            {lightboxImage && (
                <div
                    className="fixed inset-0 z-[100] bg-black/90 backdrop-blur-md flex items-center justify-center p-4 animate-fade-in"
                    onClick={(e) => { if (e.target === e.currentTarget) setLightboxImage(null) }}
                >
                    <div className="relative w-full max-w-4xl bg-slate-900 rounded-2xl border border-slate-700 shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">

                        {/* Modal Header */}
                        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800 shrink-0">
                            <div className="flex items-center gap-4">
                                <div className="p-2 bg-brand-cyan/10 rounded-lg">
                                    <i className="ph-fill ph-image text-brand-cyan text-xl"></i>
                                </div>
                                <div>
                                    <div className="text-white font-semibold">{lightboxImage.title}</div>
                                    <div className="text-xs font-mono text-slate-400">Full resolution preview</div>
                                </div>
                            </div>
                            <button
                                onClick={() => setLightboxImage(null)}
                                className="w-10 h-10 rounded-full bg-slate-800 hover:bg-slate-700 flex items-center justify-center text-slate-400 hover:text-white transition-colors cursor-pointer border border-slate-700"
                            >
                                <i className="ph ph-x text-xl"></i>
                            </button>
                        </div>

                        {/* Image */}
                        <div className="bg-black/50 flex items-center justify-center p-4 overflow-auto">
                            <img
                                src={lightboxImage.url}
                                alt={lightboxImage.title}
                                className="max-w-full max-h-[70vh] object-contain rounded-lg"
                            />
                        </div>
                    </div>
                </div>
            )}
        </div>
    )
}
