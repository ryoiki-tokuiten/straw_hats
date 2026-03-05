import { useState, useEffect, useRef, useCallback } from 'react'

/**
 * Custom hook for WebSocket connection to DSSA backend.
 * Handles reconnection, message parsing, and state distribution.
 */
export default function useWebSocket() {
    const [isConnected, setIsConnected] = useState(false)
    const [events, setEvents] = useState([])           // All raw events
    const [reconstructions, setReconstructions] = useState([])
    const [riskScores, setRiskScores] = useState([])
    const [alerts, setAlerts] = useState([])
    const [agentActivity, setAgentActivity] = useState([])
    const [pipelineStatus, setPipelineStatus] = useState(null)
    const [raceConditions, setRaceConditions] = useState([])
    const [currentChunk, setCurrentChunk] = useState(null)
    const wsRef = useRef(null)
    const reconnectTimerRef = useRef(null)

    const connect = useCallback(() => {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
        const ws = new WebSocket(`${protocol}//${window.location.host}/ws`)

        ws.onopen = () => {
            setIsConnected(true)
            console.log('[WS] Connected')
        }

        ws.onclose = () => {
            setIsConnected(false)
            console.log('[WS] Disconnected, reconnecting in 3s...')
            reconnectTimerRef.current = setTimeout(connect, 3000)
        }

        ws.onerror = (err) => {
            console.error('[WS] Error:', err)
        }

        ws.onmessage = (event) => {
            try {
                const msg = JSON.parse(event.data)

                // Deduplicate consecutive identical messages (common with React Strict Mode remounts connecting twice briefly)
                setEvents(prev => {
                    if (prev.length > 0 && JSON.stringify(prev[prev.length - 1]) === JSON.stringify(msg)) {
                        return prev;
                    }
                    return [...prev.slice(-200), msg]
                })

                // For state updates, we can use a ref to track processed message timestamps/signatures
                // Or simply rely on the fact that the backend should only send these once per valid connection.
                // A better fix for StrictMode is ensuring the WS is properly closed and nulled.

                switch (msg.type) {
                    case 'pipeline_started':
                    case 'pipeline_info':
                    case 'pipeline_completed':
                    case 'pipeline_error':
                        setPipelineStatus(msg)
                        break

                    case 'chunk_started':
                        setCurrentChunk(msg.data)
                        setAgentActivity(prev => [...prev.slice(-50), {
                            ts: msg.timestamp,
                            type: 'chunk_started',
                            text: `Processing chunk ${msg.data.chunk_index} (${msg.data.start_ts?.toFixed(0)}s - ${msg.data.end_ts?.toFixed(0)}s)${msg.data.tool_less ? ' [TOOL-LESS MODE]' : ''}`,
                            ...msg.data
                        }])
                        break

                    case 'chunk_completed':
                        setAgentActivity(prev => [...prev.slice(-50), {
                            ts: msg.timestamp,
                            type: 'chunk_completed',
                            text: `Chunk ${msg.data.chunk_index} completed in ${msg.data.elapsed_seconds?.toFixed(1)}s`,
                            ...msg.data
                        }])
                        break

                    case 'agent_status':
                        setAgentActivity(prev => [...prev.slice(-50), {
                            ts: msg.timestamp,
                            type: 'agent_status',
                            text: `[${msg.data.agent?.toUpperCase()}] ${msg.data.status}`,
                            ...msg.data
                        }])
                        break

                    case 'tool_call':
                        setAgentActivity(prev => [...prev.slice(-50), {
                            ts: msg.timestamp,
                            type: 'tool_call',
                            text: `[${msg.data.agent?.toUpperCase()}] → ${msg.data.tool}(${JSON.stringify(msg.data.args || {})})`,
                            ...msg.data
                        }])
                        break

                    case 'reconstruction_complete':
                        setReconstructions(prev => [...prev, {
                            chunk: msg.data.chunk,
                            text: msg.data.text,
                            tool_less: msg.data.tool_less,
                            ts: msg.timestamp,
                        }])
                        setAgentActivity(prev => [...prev.slice(-50), {
                            ts: msg.timestamp,
                            type: 'reconstruction',
                            text: `[NARRATIVE] Atomic reconstruction written${msg.data.tool_less ? ' (tool-less)' : ''}`,
                            reconstruction: msg.data.text,
                        }])
                        break

                    case 'risk_complete':
                        setRiskScores(prev => [...prev, {
                            chunk: msg.data.chunk,
                            ...msg.data.result,
                            tool_less: msg.data.tool_less,
                            ts: msg.timestamp,
                        }])
                        setAgentActivity(prev => [...prev.slice(-50), {
                            ts: msg.timestamp,
                            type: 'risk_complete',
                            text: `[REASONER] Risk assessment: ${(msg.data.result?.score * 100)?.toFixed(0)}% — ${msg.data.result?.classification}${msg.data.tool_less ? ' (tool-less)' : ''}`,
                            agent: 'reasoner',
                            score: msg.data.result?.score,
                            classification: msg.data.result?.classification,
                            reasoning: msg.data.result?.reasoning,
                        }])
                        break

                    case 'alert':
                        setAlerts(prev => [msg.data, ...prev])
                        break

                    case 'race_condition':
                        setRaceConditions(prev => [...prev.slice(-20), {
                            ts: msg.timestamp,
                            ...msg.data,
                        }])
                        setAgentActivity(prev => [...prev.slice(-50), {
                            ts: msg.timestamp,
                            type: 'race',
                            text: `⚡ RACE CONDITION: ${msg.data.message}`,
                            ...msg.data,
                        }])
                        break

                    case 'agent_error':
                        setAgentActivity(prev => [...prev.slice(-50), {
                            ts: msg.timestamp,
                            type: 'error',
                            text: `[${msg.data.agent?.toUpperCase()} ERROR] ${msg.data.error}`,
                            ...msg.data,
                        }])
                        break

                    case 'pipeline_waiting':
                        setPipelineStatus(msg)
                        setAgentActivity(prev => [...prev.slice(-50), {
                            ts: msg.timestamp,
                            type: 'agent_status',
                            text: `⏳ ${msg.data.message}`,
                            agent: 'pipeline',
                        }])
                        break

                    default:
                        break
                }
            } catch (e) {
                console.error('[WS] Parse error:', e)
            }
        }

        wsRef.current = ws
    }, [])

    useEffect(() => {
        connect()
        return () => {
            if (wsRef.current) {
                // Remove listeners to prevent duplicate state updates during StrictMode unmount
                wsRef.current.onmessage = null;
                wsRef.current.onclose = null;
                wsRef.current.onerror = null;
                wsRef.current.onopen = null;
                wsRef.current.close()
                wsRef.current = null;
            }
            if (reconnectTimerRef.current) {
                clearTimeout(reconnectTimerRef.current)
                reconnectTimerRef.current = null;
            }
        }
    }, [connect])

    const clearState = useCallback(() => {
        setEvents([])
        setReconstructions([])
        setRiskScores([])
        setAlerts([])
        setAgentActivity([])
        setPipelineStatus(null)
        setRaceConditions([])
        setCurrentChunk(null)
    }, [])

    return {
        isConnected,
        events,
        reconstructions,
        riskScores,
        alerts,
        agentActivity,
        pipelineStatus,
        raceConditions,
        currentChunk,
        clearState,
    }
}
