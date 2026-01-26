/**
 * DocAIAgent Test UI - JavaScript
 */

const API_BASE = '/api/v1';

// DOM Elements
const generateForm = document.getElementById('generateForm');
const generateBtn = document.getElementById('generateBtn');
const slidesContainer = document.getElementById('slidesContainer');
const progressContainer = document.getElementById('progressContainer');
const progressFill = document.getElementById('progressFill');
const progressText = document.getElementById('progressText');
const previewActions = document.getElementById('previewActions');
const statusText = document.getElementById('statusText');
const runInfo = document.getElementById('runInfo');

// State
let currentRunId = null;
let currentArtifactId = null;
let eventSource = null;

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    setupEventListeners();
});

function setupEventListeners() {
    // Form submit
    generateForm.addEventListener('submit', handleSubmit);

    // Download buttons
    document.getElementById('downloadPptx').addEventListener('click', () => downloadArtifact('pptx'));
    document.getElementById('downloadDocx').addEventListener('click', () => downloadArtifact('docx'));
    document.getElementById('downloadHtml').addEventListener('click', () => downloadArtifact('html'));
}

async function handleSubmit(e) {
    e.preventDefault();

    // Get form data
    const formData = new FormData(generateForm);
    const data = {
        prompt: formData.get('prompt'),
        language: formData.get('language'),
        slide_count: parseInt(formData.get('slide_count')) || 10,
        audience: formData.get('audience') || null,
        tone: formData.get('tone') || null,
        document_type: 'slides'
    };

    if (!data.prompt.trim()) {
        alert('Please enter a prompt.');
        return;
    }

    // Reset UI
    resetUI();
    setLoading(true);

    try {
        // Create run
        const runResponse = await fetch(`${API_BASE}/runs`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });

        if (!runResponse.ok) {
            throw new Error(`Failed to create run: ${runResponse.status}`);
        }

        const run = await runResponse.json();
        currentRunId = run.run_id;
        updateStatus(`Run created: ${currentRunId}`);
        runInfo.textContent = `Run ID: ${currentRunId.substring(0, 8)}...`;

        // Start SSE stream
        startEventStream(currentRunId);

    } catch (error) {
        console.error('Error:', error);
        updateStatus(`Error: ${error.message}`);
        setLoading(false);
    }
}

function startEventStream(runId) {
    // Close existing connection
    if (eventSource) {
        eventSource.close();
    }

    progressContainer.style.display = 'block';
    updateProgress(0, 'Connecting...');

    eventSource = new EventSource(`${API_BASE}/runs/${runId}/stream`);

    eventSource.onopen = () => {
        console.log('SSE connection opened');
        updateStatus('Connected, generating...');
    };

    eventSource.onerror = (error) => {
        console.error('SSE error:', error);
        updateStatus('Connection error');
        eventSource.close();
        setLoading(false);
    };

    // Event handlers for different event types
    eventSource.addEventListener('run_start', (e) => {
        const data = JSON.parse(e.data);
        console.log('Run started:', data);
        updateProgress(5, 'Starting generation...');
    });

    eventSource.addEventListener('run_progress', (e) => {
        const data = JSON.parse(e.data);
        console.log('Progress:', data);

        const progress = data.progress || 0;
        let message = data.message || `${data.status}...`;

        if (data.current_slide && data.total_slides) {
            message = `Generating slide ${data.current_slide} of ${data.total_slides}...`;
        }

        updateProgress(progress, message);
    });

    eventSource.addEventListener('slide_start', (e) => {
        const data = JSON.parse(e.data);
        console.log('Slide start:', data);
        updateStatus(`Generating slide ${data.slide_index + 1}...`);
    });

    eventSource.addEventListener('slide_chunk', (e) => {
        const data = JSON.parse(e.data);
        console.log('Slide chunk:', data);

        if (data.html && data.is_complete) {
            addSlide(data.slide_id, data.slide_index, data.html);
        }
    });

    eventSource.addEventListener('slide_complete', (e) => {
        const data = JSON.parse(e.data);
        console.log('Slide complete:', data);
    });

    eventSource.addEventListener('run_complete', (e) => {
        const data = JSON.parse(e.data);
        console.log('Run complete:', data);

        updateProgress(100, 'Complete!');
        updateStatus('Generation complete');
        setLoading(false);

        // Enable download buttons
        if (data.slidespec || currentRunId) {
            currentArtifactId = currentRunId;  // In MVP, artifact_id = run_id
            previewActions.style.display = 'flex';
        }

        eventSource.close();
    });

    eventSource.addEventListener('run_error', (e) => {
        const data = JSON.parse(e.data);
        console.error('Run error:', data);

        updateStatus(`Error: ${data.error}`);
        updateProgress(0, `Error: ${data.error}`);
        setLoading(false);
        eventSource.close();
    });
}

function addSlide(slideId, slideIndex, html) {
    // Remove empty state if present
    const emptyState = slidesContainer.querySelector('.empty-state');
    if (emptyState) {
        emptyState.remove();
    }

    // Create slide wrapper
    const wrapper = document.createElement('div');
    wrapper.className = 'slide-wrapper';
    wrapper.id = `slide-wrapper-${slideId}`;
    wrapper.dataset.index = slideIndex;

    wrapper.innerHTML = html;

    // Add slide number badge
    const badge = document.createElement('div');
    badge.className = 'slide-badge';
    badge.style.cssText = `
        position: absolute;
        top: 10px;
        right: 10px;
        background: var(--primary-color);
        color: white;
        padding: 4px 10px;
        border-radius: 4px;
        font-size: 12px;
        font-weight: 600;
    `;
    badge.textContent = `Slide ${slideIndex + 1}`;
    wrapper.style.position = 'relative';
    wrapper.appendChild(badge);

    // Add to container
    slidesContainer.appendChild(wrapper);

    // Scroll to new slide
    wrapper.scrollIntoView({ behavior: 'smooth', block: 'end' });
}

function updateProgress(percent, message) {
    progressFill.style.width = `${percent}%`;
    progressText.textContent = message;
}

function updateStatus(message) {
    statusText.textContent = message;
}

function setLoading(loading) {
    generateBtn.disabled = loading;
    generateBtn.querySelector('.btn-text').style.display = loading ? 'none' : 'inline';
    generateBtn.querySelector('.btn-loading').style.display = loading ? 'inline-flex' : 'none';
}

function resetUI() {
    slidesContainer.innerHTML = `
        <div class="empty-state">
            <p>Generating presentation...</p>
        </div>
    `;
    previewActions.style.display = 'none';
    progressContainer.style.display = 'none';
    updateProgress(0, '');
    currentArtifactId = null;
}

async function downloadArtifact(format) {
    if (!currentArtifactId) {
        alert('No artifact to download');
        return;
    }

    updateStatus(`Downloading ${format.toUpperCase()}...`);

    try {
        const response = await fetch(
            `${API_BASE}/artifacts/${currentArtifactId}/download?format=${format}`
        );

        if (!response.ok) {
            throw new Error(`Download failed: ${response.status}`);
        }

        // Get filename from header or use default
        const contentDisposition = response.headers.get('Content-Disposition');
        let filename = `presentation.${format}`;
        if (contentDisposition) {
            const match = contentDisposition.match(/filename="?(.+?)"?$/);
            if (match) {
                filename = match[1];
            }
        }

        // Download file
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);

        updateStatus(`Downloaded ${filename}`);

    } catch (error) {
        console.error('Download error:', error);
        updateStatus(`Download error: ${error.message}`);
        alert(`Failed to download: ${error.message}`);
    }
}
