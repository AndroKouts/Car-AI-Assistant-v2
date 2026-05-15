import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

// Sessions
export const getSessions = (limit = 20) => api.get(`/sessions?limit=${limit}`)
export const getSession = (id) => api.get(`/sessions/${id}`)
export const getSessionTurns = (id) => api.get(`/sessions/${id}/turns`)
export const getSessionSpotify = (id) => api.get(`/sessions/${id}/spotify`)
export const getSessionEmail = (id) => api.get(`/sessions/${id}/email`)

// Preferences
export const getPreferences = () => api.get('/preferences')
export const updatePreferences = (data) => api.put('/preferences', data)

// Assistant
export const getStatus = () => api.get('/assistant/status')
export const startAssistant = () => api.post('/assistant/start')
export const stopAssistant = () => api.post('/assistant/stop')
