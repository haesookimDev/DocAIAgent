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
let slideListVisible = false;
let slideListData = [];

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

    // Wrap slide content in scale container for proper scaling
    const scaleContainer = document.createElement('div');
    scaleContainer.className = 'slide-scale-container';
    scaleContainer.innerHTML = html;
    wrapper.appendChild(scaleContainer);

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

    // Update slide list if visible
    if (slideListVisible && slideData) {
        // Extract title from slide data
        let title = '';
        if (slideData.elements) {
            const titleElem = slideData.elements.find(e => e.role === 'title');
            if (titleElem && titleElem.content) {
                title = titleElem.content.text || '';
            }
        }

        slideListData[slideIndex] = {
            index: slideIndex,
            slide_id: slideId,
            type: slideData.type || 'content',
            layout: slideData.layout?.layout_id || 'one_column',
            title: title,
        };
        renderSlideList();
    }
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

    // Reset slide list
    slideListData = [];
    slideListVisible = false;
    const slideListPanel = document.getElementById('slideListPanel');
    if (slideListPanel) {
        slideListPanel.style.display = 'none';
    }
    const slideList = document.getElementById('slideList');
    if (slideList) {
        slideList.innerHTML = '';
    }
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

        // Update preview with proper container
        document.getElementById('editPreview').innerHTML = `<div class="edit-preview-container">${data.html}</div>`;

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

// Color presets for the editor
const COLOR_PRESETS = {
    backgrounds: [
        { name: 'White', value: '#ffffff', class: 'bg-white' },
        { name: 'Slate', value: '#0f172a', class: 'bg-slate-900' },
        { name: 'Blue', value: '#1e3a8a', class: 'bg-blue-900' },
        { name: 'Purple', value: '#7c3aed', class: 'bg-purple-600' },
        { name: 'Green', value: '#065f46', class: 'bg-emerald-800' },
        { name: 'Orange', value: '#9a3412', class: 'bg-orange-800' },
        { name: 'Rose', value: '#9f1239', class: 'bg-rose-800' },
        { name: 'Gray', value: '#f3f4f6', class: 'bg-gray-100' },
    ],
    text: [
        { name: 'Black', value: '#000000', class: 'text-black' },
        { name: 'White', value: '#ffffff', class: 'text-white' },
        { name: 'Gray', value: '#4b5563', class: 'text-gray-600' },
        { name: 'Blue', value: '#3b82f6', class: 'text-blue-500' },
        { name: 'Purple', value: '#8b5cf6', class: 'text-purple-500' },
    ]
};

// Theme presets
const THEME_PRESETS = [
    { id: 'white', name: 'Clean White', classes: 'bg-white' },
    { id: 'light', name: 'Light Gray', classes: 'bg-gradient-to-br from-slate-50 to-slate-200' },
    { id: 'dark', name: 'Dark', classes: 'bg-gradient-to-br from-slate-900 to-slate-800 text-white' },
    { id: 'primary', name: 'Blue', classes: 'bg-gradient-to-br from-blue-900 to-blue-600 text-white' },
    { id: 'accent', name: 'Purple', classes: 'bg-gradient-to-br from-purple-800 to-purple-500 text-white' },
    { id: 'emerald', name: 'Emerald', classes: 'bg-gradient-to-br from-emerald-900 to-emerald-600 text-white' },
    { id: 'orange', name: 'Orange', classes: 'bg-gradient-to-br from-orange-800 to-orange-500 text-white' },
    { id: 'rose', name: 'Rose', classes: 'bg-gradient-to-br from-rose-900 to-rose-600 text-white' },
];

// Font size options
const FONT_SIZES = [
    { label: 'Small', value: 'text-sm' },
    { label: 'Base', value: 'text-base' },
    { label: 'Large', value: 'text-lg' },
    { label: 'XL', value: 'text-xl' },
    { label: '2XL', value: 'text-2xl' },
    { label: '3XL', value: 'text-3xl' },
    { label: '4XL', value: 'text-4xl' },
    { label: '5XL', value: 'text-5xl' },
];

function buildVisualEditForm(slideSpec) {
    const form = document.getElementById('editForm');
    form.innerHTML = '';

    // === Slide Theme Section ===
    const themeSection = document.createElement('div');
    themeSection.className = 'style-section';
    themeSection.innerHTML = `
        <div class="style-section-title">🎨 Slide Theme</div>
        <div class="theme-presets" id="themePresets">
            ${THEME_PRESETS.map(theme => `
                <div class="theme-preset theme-${theme.id}" data-theme="${theme.id}" data-classes="${theme.classes}" onclick="selectTheme('${theme.id}')">
                    <span class="theme-preset-label">${theme.name}</span>
                </div>
            `).join('')}
        </div>
        <input type="hidden" id="editSlideTailwind" value="${slideSpec.tailwind_classes || ''}">
    `;
    form.appendChild(themeSection);

    // Highlight current theme if matches
    setTimeout(() => {
        const currentClasses = slideSpec.tailwind_classes || '';
        THEME_PRESETS.forEach(theme => {
            if (currentClasses.includes(theme.classes) || (theme.id === 'white' && !currentClasses)) {
                document.querySelector(`[data-theme="${theme.id}"]`)?.classList.add('selected');
            }
        });
    }, 0);

    // === Layout Section ===
    const layoutSection = document.createElement('div');
    layoutSection.className = 'style-section';
    layoutSection.innerHTML = `
        <div class="style-section-title">📐 Layout</div>
        <select id="editLayout" class="font-size-select" style="width: 100%;">
            <option value="title_center" ${slideSpec.layout?.layout_id === 'title_center' ? 'selected' : ''}>Title Center</option>
            <option value="section_header" ${slideSpec.layout?.layout_id === 'section_header' ? 'selected' : ''}>Section Header</option>
            <option value="one_column" ${slideSpec.layout?.layout_id === 'one_column' ? 'selected' : ''}>One Column</option>
            <option value="two_column" ${slideSpec.layout?.layout_id === 'two_column' ? 'selected' : ''}>Two Column</option>
            <option value="quote_center" ${slideSpec.layout?.layout_id === 'quote_center' ? 'selected' : ''}>Quote Center</option>
            <option value="closing" ${slideSpec.layout?.layout_id === 'closing' ? 'selected' : ''}>Closing</option>
        </select>
    `;
    form.appendChild(layoutSection);

    // === Elements Section ===
    const elementsSection = document.createElement('div');
    elementsSection.className = 'style-section';
    elementsSection.innerHTML = `<div class="style-section-title">✏️ Content Elements</div>`;

    slideSpec.elements?.forEach((elem, idx) => {
        const elemCard = document.createElement('div');
        elemCard.className = 'element-card';

        const label = elem.role || elem.kind;
        const content = elem.content?.text || '';

        if (elem.kind === 'text') {
            elemCard.innerHTML = `
                <div class="element-card-header">
                    <span class="element-card-title">${capitalizeFirst(label)}</span>
                    <span class="element-card-type">${elem.kind}</span>
                </div>
                <textarea id="editElem${idx}" data-element-id="${elem.element_id}" data-kind="text" style="width:100%; padding:8px; border:1px solid #d1d5db; border-radius:6px; font-size:14px; resize:vertical;">${content}</textarea>

                <div class="style-row" style="margin-top: 12px;">
                    <span class="style-label">Text Color</span>
                    <div class="style-control">
                        <input type="color" class="color-picker" id="elemColor${idx}" value="${getColorFromClasses(elem.tailwind_classes, 'text') || '#000000'}" onchange="updateElementStyle(${idx})">
                        <div class="color-presets">
                            ${COLOR_PRESETS.text.map(c => `
                                <div class="color-preset" style="background:${c.value}" data-idx="${idx}" data-color="${c.value}" data-class="${c.class}" onclick="setElementColor(${idx}, '${c.value}', '${c.class}')"></div>
                            `).join('')}
                        </div>
                    </div>
                </div>

                <div class="style-row">
                    <span class="style-label">Font Size</span>
                    <div class="style-control">
                        <select class="font-size-select" id="elemFontSize${idx}" onchange="updateElementStyle(${idx})">
                            ${FONT_SIZES.map(f => `<option value="${f.value}" ${hasClass(elem.tailwind_classes, f.value) ? 'selected' : ''}>${f.label}</option>`).join('')}
                        </select>
                    </div>
                </div>

                <div class="style-row">
                    <span class="style-label">Font Weight</span>
                    <div class="style-control">
                        <div class="font-weight-btns">
                            <button type="button" class="font-weight-btn ${hasClass(elem.tailwind_classes, 'font-normal') ? 'active' : ''}" data-weight="font-normal" onclick="setElementWeight(${idx}, 'font-normal')">Normal</button>
                            <button type="button" class="font-weight-btn ${hasClass(elem.tailwind_classes, 'font-semibold') ? 'active' : ''}" data-weight="font-semibold" onclick="setElementWeight(${idx}, 'font-semibold')">Semi</button>
                            <button type="button" class="font-weight-btn ${hasClass(elem.tailwind_classes, 'font-bold') ? 'active' : ''}" data-weight="font-bold" onclick="setElementWeight(${idx}, 'font-bold')">Bold</button>
                        </div>
                    </div>
                </div>

                <input type="hidden" id="editElemTailwind${idx}" value="${elem.tailwind_classes || ''}">
            `;
        } else if (elem.kind === 'bullets') {
            const items = elem.content?.items?.map(i => typeof i === 'string' ? i : i.text).join('\n') || '';
            elemCard.innerHTML = `
                <div class="element-card-header">
                    <span class="element-card-title">${capitalizeFirst(label)}</span>
                    <span class="element-card-type">${elem.kind}</span>
                </div>
                <textarea id="editElem${idx}" data-element-id="${elem.element_id}" data-kind="bullets" rows="5" style="width:100%; padding:8px; border:1px solid #d1d5db; border-radius:6px; font-size:14px; resize:vertical;" placeholder="One item per line">${items}</textarea>

                <div class="style-row" style="margin-top: 12px;">
                    <span class="style-label">Text Color</span>
                    <div class="style-control">
                        <input type="color" class="color-picker" id="elemColor${idx}" value="${getColorFromClasses(elem.tailwind_classes, 'text') || '#000000'}" onchange="updateElementStyle(${idx})">
                        <div class="color-presets">
                            ${COLOR_PRESETS.text.map(c => `
                                <div class="color-preset" style="background:${c.value}" data-idx="${idx}" data-color="${c.value}" data-class="${c.class}" onclick="setElementColor(${idx}, '${c.value}', '${c.class}')"></div>
                            `).join('')}
                        </div>
                    </div>
                </div>

                <input type="hidden" id="editElemTailwind${idx}" value="${elem.tailwind_classes || ''}">
            `;
        } else {
            elemCard.innerHTML = `
                <div class="element-card-header">
                    <span class="element-card-title">${capitalizeFirst(label)}</span>
                    <span class="element-card-type">${elem.kind}</span>
                </div>
                <p style="color: #6b7280; font-size: 12px; margin: 0;">Edit this element in JSON mode</p>
            `;
        }

        elementsSection.appendChild(elemCard);
    });

    form.appendChild(elementsSection);
}

// Helper functions for the visual editor
function capitalizeFirst(str) {
    return str.charAt(0).toUpperCase() + str.slice(1);
}

function hasClass(classes, className) {
    if (!classes) return false;
    return classes.split(' ').includes(className);
}

function getColorFromClasses(classes, type) {
    if (!classes) return null;
    // Simple color extraction - in real implementation, map Tailwind classes to hex
    const colorMap = {
        'text-white': '#ffffff',
        'text-black': '#000000',
        'text-gray-600': '#4b5563',
        'text-blue-500': '#3b82f6',
        'text-purple-500': '#8b5cf6',
    };
    for (const [cls, hex] of Object.entries(colorMap)) {
        if (classes.includes(cls)) return hex;
    }
    return null;
}

function selectTheme(themeId) {
    // Remove selected from all
    document.querySelectorAll('.theme-preset').forEach(el => el.classList.remove('selected'));
    // Add selected to clicked
    document.querySelector(`[data-theme="${themeId}"]`)?.classList.add('selected');

    // Update hidden input with theme classes
    const theme = THEME_PRESETS.find(t => t.id === themeId);
    if (theme) {
        document.getElementById('editSlideTailwind').value = theme.classes;
    }
}

function setElementColor(idx, colorValue, colorClass) {
    document.getElementById(`elemColor${idx}`).value = colorValue;
    updateElementTailwindClass(idx, 'text-', colorClass);

    // Highlight selected preset
    document.querySelectorAll(`[data-idx="${idx}"]`).forEach(el => el.classList.remove('selected'));
    event.target.classList.add('selected');
}

function setElementWeight(idx, weight) {
    const btns = event.target.parentElement.querySelectorAll('.font-weight-btn');
    btns.forEach(btn => btn.classList.remove('active'));
    event.target.classList.add('active');

    updateElementTailwindClass(idx, 'font-', weight);
}

function updateElementStyle(idx) {
    const fontSize = document.getElementById(`elemFontSize${idx}`)?.value;
    if (fontSize) {
        updateElementTailwindClass(idx, 'text-', fontSize);
    }
}

function updateElementTailwindClass(idx, prefix, newClass) {
    const input = document.getElementById(`editElemTailwind${idx}`);
    if (!input) return;

    let classes = input.value.split(' ').filter(c => c.trim());

    // Remove existing classes with same prefix
    classes = classes.filter(c => !c.startsWith(prefix));

    // Add new class
    if (newClass) {
        classes.push(newClass);
    }

    input.value = classes.join(' ');
}

// Make editor functions globally available
window.selectTheme = selectTheme;
window.setElementColor = setElementColor;
window.setElementWeight = setElementWeight;
window.updateElementStyle = updateElementStyle;

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
            const scaleContainer = wrapper.querySelector('.slide-scale-container');
            if (scaleContainer) {
                scaleContainer.innerHTML = result.html;
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
            const scaleContainer = wrapper.querySelector('.slide-scale-container');
            if (scaleContainer) {
                scaleContainer.innerHTML = result.html;
            }
        }

        // Update modal preview
        document.getElementById('editPreview').innerHTML = `<div class="edit-preview-container">${result.html}</div>`;
        document.getElementById('jsonEditArea').value = JSON.stringify(result.slide_data, null, 2);
        buildVisualEditForm(result.slide_data);

        updateStatus('Slide regenerated!');

    } catch (error) {
        console.error('Regenerate error:', error);
        alert(`Failed to regenerate: ${error.message}`);
        updateStatus('Regeneration failed');
    }
}

// ==================== SLIDE LIST ====================

function toggleSlideList() {
    slideListVisible = !slideListVisible;
    const panel = document.getElementById('slideListPanel');

    if (slideListVisible) {
        panel.style.display = 'flex';
        loadSlideList();
    } else {
        panel.style.display = 'none';
    }
}

async function loadSlideList() {
    if (!currentArtifactId) {
        document.getElementById('slideList').innerHTML = '<p style="padding:16px;color:#6b7280;text-align:center;">No presentation loaded</p>';
        return;
    }

    try {
        const response = await fetch(`${API_BASE}/artifacts/${currentArtifactId}/slides`);
        if (!response.ok) throw new Error('Failed to load slides');

        const data = await response.json();
        slideListData = data.slides;

        renderSlideList();

    } catch (error) {
        console.error('Error loading slide list:', error);
        document.getElementById('slideList').innerHTML = '<p style="padding:16px;color:#dc3545;">Failed to load slides</p>';
    }
}

function renderSlideList() {
    const container = document.getElementById('slideList');

    if (slideListData.length === 0) {
        container.innerHTML = '<p style="padding:16px;color:#6b7280;text-align:center;">No slides yet</p>';
        return;
    }

    container.innerHTML = slideListData.map((slide, idx) => `
        <div class="slide-list-item" data-index="${idx}" onclick="scrollToSlide(${idx})">
            <div class="slide-list-item-number">${idx + 1}</div>
            <div class="slide-list-item-info">
                <div class="slide-list-item-title">${slide.title || 'Untitled'}</div>
                <div class="slide-list-item-type">${slide.layout || 'content'}</div>
            </div>
            <div class="slide-list-item-actions">
                <button class="slide-list-action-btn" onclick="event.stopPropagation(); openEditModal(${idx})" title="Edit">✏️</button>
            </div>
        </div>
    `).join('');
}

function scrollToSlide(index) {
    const wrapper = document.querySelector(`[data-index="${index}"]`);
    if (wrapper) {
        wrapper.scrollIntoView({ behavior: 'smooth', block: 'center' });
        // Highlight briefly
        wrapper.style.boxShadow = '0 0 0 4px #3b82f6';
        setTimeout(() => {
            wrapper.style.boxShadow = '';
        }, 1500);
    }

    // Update active state in list
    document.querySelectorAll('.slide-list-item').forEach(item => {
        item.classList.toggle('active', parseInt(item.dataset.index) === index);
    });
}

function updateSlideList(slideIndex, title) {
    // Update local data
    if (slideListData[slideIndex]) {
        slideListData[slideIndex].title = title;
        renderSlideList();
    }
}

// Make functions globally available
window.openEditModal = openEditModal;
window.closeEditModal = closeEditModal;
window.switchEditTab = switchEditTab;
window.saveSlideChanges = saveSlideChanges;
window.regenerateSlide = regenerateSlide;
window.toggleSlideList = toggleSlideList;
window.scrollToSlide = scrollToSlide;
