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
let currentSlideData = {};  // Store slide data for editing
let editingSlideIndex = null;

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

function addSlide(slideId, slideIndex, html, slideData = null) {
    // Remove empty state if present
    const emptyState = slidesContainer.querySelector('.empty-state');
    if (emptyState) {
        emptyState.remove();
    }

    // Store slide data for editing
    if (slideData) {
        currentSlideData[slideIndex] = slideData;
    }

    // Create slide wrapper
    const wrapper = document.createElement('div');
    wrapper.className = 'slide-wrapper';
    wrapper.id = `slide-wrapper-${slideId}`;
    wrapper.dataset.index = slideIndex;
    wrapper.dataset.slideId = slideId;

    wrapper.innerHTML = html;

    // Add edit button
    const editBtn = document.createElement('button');
    editBtn.className = 'slide-edit-btn';
    editBtn.innerHTML = '✏️ Edit';
    editBtn.onclick = () => openEditModal(slideIndex);
    wrapper.appendChild(editBtn);

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

// ==================== SLIDE EDITING ====================

async function openEditModal(slideIndex) {
    editingSlideIndex = slideIndex;

    // Show modal
    const modal = document.getElementById('editModal');
    modal.style.display = 'flex';

    document.getElementById('editSlideNumber').textContent = slideIndex + 1;

    // Fetch slide data
    try {
        const response = await fetch(`${API_BASE}/artifacts/${currentArtifactId}/slides/${slideIndex}`);
        if (!response.ok) throw new Error('Failed to fetch slide');

        const data = await response.json();
        currentSlideData[slideIndex] = data;

        // Update preview
        document.getElementById('editPreview').innerHTML = data.html;

        // Fetch full slide spec for JSON editor
        const specResponse = await fetch(`${API_BASE}/artifacts/${currentArtifactId}/slidespec`);
        const spec = await specResponse.json();
        const slideSpec = spec.slides[slideIndex];

        // Populate JSON editor
        document.getElementById('jsonEditArea').value = JSON.stringify(slideSpec, null, 2);

        // Build visual edit form
        buildVisualEditForm(slideSpec);

    } catch (error) {
        console.error('Error loading slide:', error);
        alert('Failed to load slide for editing');
    }
}

function closeEditModal() {
    document.getElementById('editModal').style.display = 'none';
    editingSlideIndex = null;
}

function switchEditTab(tab) {
    // Update tab buttons
    document.querySelectorAll('.edit-tab').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.tab === tab);
    });

    // Show/hide panels
    document.getElementById('visualEditor').style.display = tab === 'visual' ? 'grid' : 'none';
    document.getElementById('jsonEditor').style.display = tab === 'json' ? 'block' : 'none';
}

function buildVisualEditForm(slideSpec) {
    const form = document.getElementById('editForm');
    form.innerHTML = '';

    // Layout selector
    const layoutField = document.createElement('div');
    layoutField.className = 'edit-field';
    layoutField.innerHTML = `
        <label>Layout</label>
        <select id="editLayout">
            <option value="title_center" ${slideSpec.layout?.layout_id === 'title_center' ? 'selected' : ''}>Title Center</option>
            <option value="section_header" ${slideSpec.layout?.layout_id === 'section_header' ? 'selected' : ''}>Section Header</option>
            <option value="one_column" ${slideSpec.layout?.layout_id === 'one_column' ? 'selected' : ''}>One Column</option>
            <option value="two_column" ${slideSpec.layout?.layout_id === 'two_column' ? 'selected' : ''}>Two Column</option>
            <option value="quote_center" ${slideSpec.layout?.layout_id === 'quote_center' ? 'selected' : ''}>Quote Center</option>
            <option value="closing" ${slideSpec.layout?.layout_id === 'closing' ? 'selected' : ''}>Closing</option>
        </select>
    `;
    form.appendChild(layoutField);

    // Tailwind classes for slide
    const tailwindField = document.createElement('div');
    tailwindField.className = 'edit-field';
    tailwindField.innerHTML = `
        <label>Slide Tailwind Classes</label>
        <input type="text" id="editSlideTailwind" value="${slideSpec.tailwind_classes || ''}" placeholder="e.g., bg-gradient-to-br from-purple-900 to-indigo-900">
    `;
    form.appendChild(tailwindField);

    // Elements
    slideSpec.elements?.forEach((elem, idx) => {
        const elemDiv = document.createElement('div');
        elemDiv.className = 'edit-field';
        elemDiv.style.borderTop = '1px solid #e5e7eb';
        elemDiv.style.paddingTop = '16px';

        const label = elem.role || elem.kind;
        const content = elem.content?.text || elem.content?.items?.join('\n') || '';

        if (elem.kind === 'text') {
            elemDiv.innerHTML = `
                <label>Element ${idx + 1}: ${label}</label>
                <textarea id="editElem${idx}" data-element-id="${elem.element_id}" data-kind="text">${content}</textarea>
                <input type="text" id="editElemTailwind${idx}" placeholder="Tailwind classes" value="${elem.tailwind_classes || ''}" style="margin-top: 8px;">
            `;
        } else if (elem.kind === 'bullets') {
            const items = elem.content?.items?.map(i => typeof i === 'string' ? i : i.text).join('\n') || '';
            elemDiv.innerHTML = `
                <label>Element ${idx + 1}: ${label} (one item per line)</label>
                <textarea id="editElem${idx}" data-element-id="${elem.element_id}" data-kind="bullets" rows="6">${items}</textarea>
                <input type="text" id="editElemTailwind${idx}" placeholder="Tailwind classes" value="${elem.tailwind_classes || ''}" style="margin-top: 8px;">
            `;
        } else {
            elemDiv.innerHTML = `
                <label>Element ${idx + 1}: ${label} (${elem.kind})</label>
                <p style="color: #6b7280; font-size: 12px;">Edit this element in JSON mode</p>
            `;
        }

        form.appendChild(elemDiv);
    });
}

async function saveSlideChanges() {
    if (editingSlideIndex === null) return;

    try {
        // Check which tab is active
        const isJsonMode = document.querySelector('.edit-tab[data-tab="json"]').classList.contains('active');

        let slideData;

        if (isJsonMode) {
            // Get JSON from editor
            const jsonText = document.getElementById('jsonEditArea').value;
            slideData = JSON.parse(jsonText);
        } else {
            // Build slide data from visual form
            const specResponse = await fetch(`${API_BASE}/artifacts/${currentArtifactId}/slidespec`);
            const spec = await specResponse.json();
            slideData = { ...spec.slides[editingSlideIndex] };

            // Update layout
            slideData.layout = { layout_id: document.getElementById('editLayout').value };

            // Update slide tailwind classes
            slideData.tailwind_classes = document.getElementById('editSlideTailwind').value || null;

            // Update elements
            slideData.elements.forEach((elem, idx) => {
                const textInput = document.getElementById(`editElem${idx}`);
                const tailwindInput = document.getElementById(`editElemTailwind${idx}`);

                if (textInput) {
                    const kind = textInput.dataset.kind;
                    if (kind === 'text') {
                        elem.content = { text: textInput.value };
                    } else if (kind === 'bullets') {
                        const items = textInput.value.split('\n').filter(item => item.trim());
                        elem.content = { items: items };
                    }
                }

                if (tailwindInput) {
                    elem.tailwind_classes = tailwindInput.value || null;
                }
            });
        }

        updateStatus('Saving changes...');

        // Send update to server
        const response = await fetch(
            `${API_BASE}/artifacts/${currentArtifactId}/slides/${editingSlideIndex}`,
            {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(slideData),
            }
        );

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to save');
        }

        const result = await response.json();

        // Update the slide in the preview
        const wrapper = document.getElementById(`slide-wrapper-${result.slide_id}`);
        if (wrapper) {
            const slideElement = wrapper.querySelector('.slide');
            if (slideElement) {
                slideElement.outerHTML = result.html;
            }
        }

        updateStatus('Changes saved!');
        closeEditModal();

    } catch (error) {
        console.error('Save error:', error);
        alert(`Failed to save: ${error.message}`);
        updateStatus('Save failed');
    }
}

async function regenerateSlide() {
    if (editingSlideIndex === null) return;

    const prompt = window.prompt('Enter any specific instructions for regeneration (optional):');

    try {
        updateStatus('Regenerating slide...');

        const response = await fetch(
            `${API_BASE}/artifacts/${currentArtifactId}/slides/${editingSlideIndex}/regenerate`,
            {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ prompt: prompt || '' }),
            }
        );

        if (!response.ok) {
            throw new Error('Failed to regenerate');
        }

        const result = await response.json();

        // Update the slide in preview
        const slideId = result.slide_id;
        const wrapper = document.getElementById(`slide-wrapper-${slideId}`) ||
                        document.querySelector(`[data-index="${editingSlideIndex}"]`);
        if (wrapper) {
            const slideHtml = result.html;
            // Keep only the slide content
            const existingBtns = wrapper.querySelectorAll('.slide-edit-btn, .slide-badge');
            wrapper.innerHTML = slideHtml;
            existingBtns.forEach(btn => wrapper.appendChild(btn.cloneNode(true)));
        }

        // Update modal preview
        document.getElementById('editPreview').innerHTML = result.html;
        document.getElementById('jsonEditArea').value = JSON.stringify(result.slide_data, null, 2);
        buildVisualEditForm(result.slide_data);

        updateStatus('Slide regenerated!');

    } catch (error) {
        console.error('Regenerate error:', error);
        alert(`Failed to regenerate: ${error.message}`);
        updateStatus('Regeneration failed');
    }
}

// Make functions globally available
window.openEditModal = openEditModal;
window.closeEditModal = closeEditModal;
window.switchEditTab = switchEditTab;
window.saveSlideChanges = saveSlideChanges;
window.regenerateSlide = regenerateSlide;
