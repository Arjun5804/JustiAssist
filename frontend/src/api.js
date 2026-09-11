/**
 * JustiAssist API Utilities v2.0
 * Includes auth-aware fetching, SSE, and chat memory APIs.
 */

// ==================== Auth Helpers ====================

/**
 * Get stored JWT token
 */
export const getToken = () => localStorage.getItem('justiassist_token')

/**
 * Auth-aware fetch wrapper — automatically includes JWT token
 */
export const authFetch = (url, options = {}) => {
    const token = getToken()
    const headers = {
        'Content-Type': 'application/json',
        ...(options.headers || {}),
    }
    if (token) {
        headers['Authorization'] = `Bearer ${token}`
    }
    return fetch(url, { ...options, headers })
}

/**
 * Login API call
 */
export const apiLogin = async (email, password) => {
    try {
        const res = await fetch('/api/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password }),
        })
        return await res.json()
    } catch (err) {
        return { detail: 'Connection error' }
    }
}

/**
 * Signup API call
 */
export const apiSignup = async (email, password, display_name) => {
    try {
        const res = await fetch('/api/auth/signup', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password, display_name }),
        })
        return await res.json()
    } catch (err) {
        return { detail: 'Connection error' }
    }
}

// ==================== SSE Connection ====================

/**
 * Connect to SSE query stream (v2.0 — uses CrewAI pipeline)
 * @param {string} query The user question
 * @param {object} options Configuration (mode, sessionId, etc.)
 * @param {object} callbacks Event handlers (onStage, onComplete, onError)
 * @returns {EventSource} The established EventSource
 */
export const connectSSE = (query, options = {}, callbacks = {}) => {
    const { mode = 'auto', sessionId = null, custodyDays = null, offenseSections = null } = options;
    const { onStage, onComplete, onError, onMessage } = callbacks;

    const params = new URLSearchParams({
        query: query,
        mode: mode
    });

    if (sessionId) params.append('session_id', sessionId);
    if (custodyDays) params.append('custody_days', custodyDays);
    if (offenseSections) params.append('offense_sections', offenseSections);

    // Use v2 endpoint if available, with token in query string
    const token = getToken();
    if (token) params.append('token', token);

    const eventSource = new EventSource(`/api/v2/query/stream?${params.toString()}`);

    eventSource.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            if (onMessage) onMessage(data);

            if (data.type === 'stage') {
                if (onStage) onStage(data.stage, data.status, data.data);
            } else if (data.type === 'complete') {
                if (onComplete) onComplete(data.data.response || data.response);
                eventSource.close();
            } else if (data.type === 'error') {
                if (onError) onError(data.message);
                eventSource.close();
            }
        } catch (err) {
            console.error('Error parsing SSE message:', err);
            if (onError) onError('Error parsing response from server');
            eventSource.close();
        }
    };

    eventSource.onerror = (err) => {
        console.error('EventSource failed:', err);
        if (onError) onError('Connection to server lost. Please try again.');
        eventSource.close();
    };

    return eventSource;
};

// ==================== Chat Memory API ====================

/**
 * Get chat history
 */
export const getChatHistory = async (conversationId = null, limit = 20) => {
    const params = new URLSearchParams({ limit: limit.toString() })
    if (conversationId) params.append('conversation_id', conversationId)
    const res = await authFetch(`/api/chat/history?${params.toString()}`)
    return res.json()
}

/**
 * Get recent conversations list
 */
export const getConversations = async (limit = 10) => {
    const res = await authFetch(`/api/chat/conversations?limit=${limit}`)
    return res.json()
}

/**
 * Clear chat history
 */
export const clearChatHistory = async (conversationId = null) => {
    const params = conversationId ? `?conversation_id=${conversationId}` : ''
    const res = await authFetch(`/api/chat/history${params}`, { method: 'DELETE' })
    return res.json()
}
