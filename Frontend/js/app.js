// Authentication utilities
function getAuthToken() {
    return localStorage.getItem('token');
}

function getUser() {
    const userStr = localStorage.getItem('user');
    return userStr ? JSON.parse(userStr) : null;
}

function logout() {
    const token = getAuthToken();
    
    if (token) {
        fetch('/api/auth/logout', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`
            }
        }).finally(() => {
            localStorage.removeItem('token');
            localStorage.removeItem('user');
            window.location.href = '/login.html';
        });
    } else {
        localStorage.removeItem('token');
        localStorage.removeItem('user');
        window.location.href = '/login.html';
    }
}

function checkAuth() {
    const token = getAuthToken();
    
    if (!token) {
        window.location.href = '/login.html';
        return false;
    }
    
    // Verify token is still valid
    fetch('/api/auth/me', {
        headers: {
            'Authorization': `Bearer ${token}`
        }
    })
    .then(response => {
        if (!response.ok) {
            throw new Error('Invalid token');
        }
        return response.json();
    })
    .then(data => {
        if (data.success) {
            updateUserInfo(data.user);
        } else {
            throw new Error('Auth failed');
        }
    })
    .catch(() => {
        localStorage.removeItem('token');
        localStorage.removeItem('user');
        window.location.href = '/login.html';
    });
    
    return true;
}

function updateUserInfo(user) {
    const userElements = document.querySelectorAll('.user-name');
    userElements.forEach(el => {
        el.textContent = user.full_name || user.username;
    });
    
    const userEmailElements = document.querySelectorAll('.user-email');
    userEmailElements.forEach(el => {
        el.textContent = user.email;
    });
}

// API request helper with authentication
async function apiRequest(url, options = {}) {
    const token = getAuthToken();
    
    const headers = {
        'Content-Type': 'application/json',
        ...options.headers
    };
    
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }
    
    const response = await fetch(url, {
        ...options,
        headers
    });
    
    if (response.status === 401) {
        localStorage.removeItem('token');
        localStorage.removeItem('user');
        window.location.href = '/login.html';
        throw new Error('Unauthorized');
    }
    
    return response;
}

// Initialize page
document.addEventListener('DOMContentLoaded', () => {
    // Check authentication for protected pages
    const currentPage = window.location.pathname;
    if (currentPage !== '/login.html' && currentPage !== '/') {
        checkAuth();
    }
    
    // Add logout functionality to all logout buttons
    const logoutBtns = document.querySelectorAll('.logout-btn, [data-action="logout"]');
    logoutBtns.forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            logout();
        });
    });
    
    // Update user info in navigation
    const user = getUser();
    if (user) {
        updateUserInfo(user);
    }
});

// Call Now Page Functions
async function initiateCall() {
    const phoneNumber = document.getElementById('phoneNumber').value;
    const prompt = document.getElementById('promptText').value;
    const statusDiv = document.getElementById('callStatus');
    const initiateBtn = document.getElementById('initiateBtn');
    
    if (!phoneNumber || !prompt) {
        showStatus('Please fill in all fields', 'error');
        return;
    }
    
    initiateBtn.disabled = true;
    initiateBtn.textContent = '📞 Initiating...';
    
    try {
        const response = await apiRequest('/api/calls/initiate', {
            method: 'POST',
            body: JSON.stringify({
                phone_number: phoneNumber,
                prompt: prompt
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            showStatus(`✅ ${data.message} Call ID: ${data.call_id}`, 'success');
            
            // Clear form
            document.getElementById('phoneNumber').value = '';
            document.getElementById('promptText').value = '';
            
            // Redirect to recordings after 2 seconds
            setTimeout(() => {
                window.location.href = '/recordings.html';
            }, 2000);
        } else {
            showStatus(`❌ Error: ${data.detail || 'Failed to initiate call'}`, 'error');
        }
    } catch (error) {
        if (error.message !== 'Unauthorized') {
            showStatus(`❌ Error: ${error.message}`, 'error');
        }
    } finally {
        initiateBtn.disabled = false;
        initiateBtn.textContent = '📞 Initiate Call';
    }
}

function showStatus(message, type) {
    const statusDiv = document.getElementById('callStatus');
    statusDiv.textContent = message;
    statusDiv.className = `status ${type}`;
    statusDiv.style.display = 'block';
}

// Recordings Page Functions
async function loadRecordings() {
    const recordingsList = document.getElementById('recordingsList');
    
    if (!recordingsList) return;
    
    recordingsList.innerHTML = '<p style="text-align: center; padding: 40px; color: #6b7280;">Loading calls...</p>';
    
    try {
        const response = await apiRequest('/api/calls');
        const data = await response.json();
        
        if (data.success && data.calls && data.calls.length > 0) {
            recordingsList.innerHTML = data.calls.map(call => `
                <div class="recording-card" data-call-id="${call.id}">
                    <div class="recording-header">
                        <div>
                            <h3>📞 ${call.phone_number}</h3>
                            <p class="recording-date">
                                ${new Date(call.created_at).toLocaleString()}
                                ${call.user ? `• User: ${call.user}` : ''}
                            </p>
                        </div>
                        <span class="status-badge status-${call.status}">${call.status}</span>
                    </div>
                    
                    <div class="recording-details">
                        <p><strong>Prompt:</strong> ${call.prompt || 'N/A'}</p>
                        ${call.duration ? `<p><strong>Duration:</strong> ${call.duration}s</p>` : ''}
                        ${call.ended_reason ? `<p><strong>End reason:</strong> ${call.ended_reason}</p>` : ''}
                        ${call.sync_error ? `<p><strong>Status refresh:</strong> ${call.sync_error}</p>` : ''}
                    </div>
                    
                    <div class="recording-actions">
                        <button onclick="viewDetails('${call.id}')" class="btn btn-primary">
                            📋 View Details
                        </button>
                        <button onclick="playRecording('${call.id}')" class="btn btn-secondary">
                            🎵 Play Recording
                        </button>
                        <button onclick="viewTranscript('${call.id}')" class="btn btn-secondary">
                            📝 Transcript
                        </button>
                        <button onclick="deleteCall('${call.id}')" class="btn btn-danger">
                            🗑️ Delete
                        </button>
                    </div>
                </div>
            `).join('');
        } else {
            recordingsList.innerHTML = '<p style="text-align: center; padding: 40px; color: #6b7280;">No calls found. Initiate your first call!</p>';
        }
    } catch (error) {
        if (error.message !== 'Unauthorized') {
            recordingsList.innerHTML = '<p style="text-align: center; padding: 40px; color: #ef4444;">Error loading calls. Please refresh the page.</p>';
        }
    }
}

async function viewDetails(callId) {
    try {
        const response = await apiRequest(`/api/calls/${callId}`);
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || `Request failed (${response.status})`);
        
        if (data.success) {
            const call = data.call;
            alert(`Call Details:\n\nID: ${call.id}\nPhone: ${call.customer?.number || 'N/A'}\nStatus: ${call.status}\n${call.endedReason ? `End reason: ${call.endedReason}\n` : ''}Created: ${new Date(call.createdAt || call.created_at).toLocaleString()}\n${call.endedAt ? `Ended: ${new Date(call.endedAt).toLocaleString()}` : ''}\n${call.cost ? `Cost: $${call.cost}` : ''}`);
        }
    } catch (error) {
        if (error.message !== 'Unauthorized') {
            alert(`Error fetching call details: ${error.message}`);
        }
    }
}

async function playRecording(callId) {
    const btn = event.target;
    btn.disabled = true;
    btn.textContent = '⏳ Loading...';
    
    try {
        const response = await apiRequest(`/api/calls/${callId}/recording`);
        const data = await response.json();
        
        if (data.success && data.recording_url) {
            window.open(data.recording_url, '_blank');
        } else {
            alert(data.message || 'Recording not available yet. Please try again in a few moments.');
        }
    } catch (error) {
        if (error.message !== 'Unauthorized') {
            alert('Error loading recording');
        }
    } finally {
        btn.disabled = false;
        btn.textContent = '🎵 Play Recording';
    }
}

async function viewTranscript(callId) {
    try {
        const response = await apiRequest(`/api/calls/${callId}/transcript`);
        const data = await response.json();
        
        if (data.success && data.transcript) {
            const transcriptText = Array.isArray(data.transcript) 
                ? data.transcript.map(msg => `${msg.role}: ${msg.message}`).join('\n\n')
                : JSON.stringify(data.transcript, null, 2);
            
            const modal = document.createElement('div');
            modal.style.cssText = 'position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; z-index: 1000;';
            modal.innerHTML = `
                <div style="background: white; padding: 30px; border-radius: 12px; max-width: 600px; max-height: 80vh; overflow-y: auto;">
                    <h3 style="margin-top: 0;">Call Transcript</h3>
                    <pre style="white-space: pre-wrap; background: #f3f4f6; padding: 15px; border-radius: 6px;">${transcriptText}</pre>
                    <button onclick="this.closest('div').parentElement.remove()" style="margin-top: 20px; padding: 10px 20px; background: #2563eb; color: white; border: none; border-radius: 6px; cursor: pointer;">Close</button>
                </div>
            `;
            document.body.appendChild(modal);
        } else {
            alert(data.message || 'Transcript not available yet.');
        }
    } catch (error) {
        if (error.message !== 'Unauthorized') {
            alert('Error loading transcript');
        }
    }
}

async function deleteCall(callId) {
    if (!confirm('Are you sure you want to delete this call?')) {
        return;
    }
    
    try {
        const response = await apiRequest(`/api/calls/${callId}`, {
            method: 'DELETE'
        });
        
        const data = await response.json();
        
        if (data.success) {
            loadRecordings();
        } else {
            alert('Error deleting call');
        }
    } catch (error) {
        if (error.message !== 'Unauthorized') {
            alert('Error deleting call');
        }
    }
}

// Auto-refresh recordings every 30 seconds
if (window.location.pathname === '/recordings.html') {
    loadRecordings();
    setInterval(loadRecordings, 30000);
}
