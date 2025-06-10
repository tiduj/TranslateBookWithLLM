let filesToProcess = [];
let translationQueue = [];
let currentProcessingJob = null;
let isBatchActive = false;
let lastCompletedJobData = null;

const API_BASE_URL = `${window.location.protocol}//${window.location.hostname}:5000`;
const socket = io(API_BASE_URL);

socket.on('connect', () => {
    console.log('WebSocket connected to:', API_BASE_URL);
    addLog('✅ WebSocket connection to server established.');
});
socket.on('disconnect', () => {
    console.log('WebSocket disconnected.');
    addLog('❌ WebSocket connection lost.');
    if (isBatchActive && currentProcessingJob) {
        showMessage('Connection lost. Batch paused. Reconnect to resume or reset.', 'error');
    }
});

socket.on('translation_update', (data) => {
    if (currentProcessingJob && data.translation_id === currentProcessingJob.translationId) {
        handleTranslationUpdate(data);
    } else {
        console.log("Received update for a different/old job:", data.translation_id);
    }
});

function updateFileStatusInList(fileName, newStatus, translationId = null) {
    const fileListItem = document.querySelector(`#fileListContainer li[data-filename="${fileName}"] .file-status`);
    if (fileListItem) {
        fileListItem.textContent = `(${newStatus})`;
    }
    const fileObj = filesToProcess.find(f => f.name === fileName);
    if (fileObj) {
        fileObj.status = newStatus;
        if (translationId) fileObj.translationId = translationId;
    }
}

function finishCurrentFileTranslationUI(statusMessage, messageType, resultData) {
    if (!currentProcessingJob) return;

    const currentFile = currentProcessingJob.fileRef;
    currentFile.status = resultData.status || 'unknown_error';
    currentFile.result = resultData.result;

    if (resultData && resultData.result) {
        document.getElementById('outputSection').classList.remove('hidden');
        document.getElementById('outputTitle').textContent = `📄 Translation Result for ${currentFile.name}`;

        lastCompletedJobData = {
            translationId: currentProcessingJob.translationId,
            outputFilename: currentFile.outputFilename,
            status: resultData.status,
            fileType: resultData.file_type
        };
        document.getElementById('downloadBtn').disabled = !(lastCompletedJobData.outputFilename && (lastCompletedJobData.status === 'completed' || lastCompletedJobData.status === 'interrupted'));

    } else {
         document.getElementById('downloadBtn').disabled = true;
    }

    showMessage(statusMessage, messageType);
    updateFileStatusInList(currentFile.name, resultData.status === 'completed' ? 'Completed' : (resultData.status === 'interrupted' ? 'Interrupted' : 'Error'));

    currentProcessingJob = null;
    processNextFileInQueue();
}

function handleTranslationUpdate(data) {
    if (!currentProcessingJob || data.translation_id !== currentProcessingJob.translationId) return;

    const currentFile = currentProcessingJob.fileRef;

    if (data.log) addLog(`[${currentFile.name}] ${data.log}`);
    if (data.progress !== undefined) updateProgress(data.progress);

    if (data.stats) {
        if (currentFile.fileType === 'epub') {
            document.getElementById('statsGrid').style.display = 'none';
        } else if (currentFile.fileType === 'srt') {
            document.getElementById('statsGrid').style.display = '';
            document.getElementById('totalChunks').textContent = data.stats.total_subtitles || '0';
            document.getElementById('completedChunks').textContent = data.stats.completed_subtitles || '0';
            document.getElementById('failedChunks').textContent = data.stats.failed_subtitles || '0';
        } else {
            document.getElementById('statsGrid').style.display = '';
            document.getElementById('totalChunks').textContent = data.stats.total_chunks || '0';
            document.getElementById('completedChunks').textContent = data.stats.completed_chunks || '0';
            document.getElementById('failedChunks').textContent = data.stats.failed_chunks || '0';
        }
        
        if (data.stats.elapsed_time !== undefined) {
            document.getElementById('elapsedTime').textContent = data.stats.elapsed_time.toFixed(1) + 's';
        }
    }

    if (data.status === 'completed') {
        finishCurrentFileTranslationUI(`✅ ${currentFile.name}: Translation completed!`, 'success', data);
    } else if (data.status === 'interrupted') {
        finishCurrentFileTranslationUI(`ℹ️ ${currentFile.name}: Translation interrupted.`, 'info', data);
    } else if (data.status === 'error') {
        finishCurrentFileTranslationUI(`❌ ${currentFile.name}: Error - ${data.error || 'Unknown error.'}`, 'error', data);
    } else if (data.status === 'running') {
         document.getElementById('progressSection').classList.remove('hidden');
         document.getElementById('currentFileProgressTitle').textContent = `📊 Translating: ${currentFile.name}`;
         
         if (currentFile.fileType === 'epub') {
             showMessage(`Translating EPUB file: ${currentFile.name}... This may take some time.`, 'info');
             document.getElementById('statsGrid').style.display = 'none';
         } else if (currentFile.fileType === 'srt') {
             showMessage(`Translating SRT subtitle file: ${currentFile.name}...`, 'info');
             document.getElementById('statsGrid').style.display = '';
         } else {
             showMessage(`Translation in progress for ${currentFile.name}...`, 'info');
             document.getElementById('statsGrid').style.display = '';
         }
         
         updateFileStatusInList(currentFile.name, 'Processing');
    }
}

window.addEventListener('load', async () => {
    try {
        const response = await fetch(`${API_BASE_URL}/api/health`);
        if (!response.ok) throw new Error('Server health check failed');
        const healthData = await response.json();
        addLog('Server health check OK.');
        
        if (healthData.supported_formats) {
            addLog(`Supported file formats: ${healthData.supported_formats.join(', ')}`);
        }
        
        loadAvailableModels();
        const configResponse = await fetch(`${API_BASE_URL}/api/config`);
        if (configResponse.ok) {
            const defaultConfig = await configResponse.json();
            document.getElementById('apiEndpoint').value = defaultConfig.api_endpoint || 'http://localhost:11434/api/generate';
            document.getElementById('chunkSize').value = defaultConfig.chunk_size || 25;
            document.getElementById('timeout').value = defaultConfig.timeout || 180;
            document.getElementById('contextWindow').value = defaultConfig.context_window || 4096;
            document.getElementById('maxAttempts').value = defaultConfig.max_attempts || 2;
            document.getElementById('retryDelay').value = defaultConfig.retry_delay || 2;
            document.getElementById('outputFilenamePattern').value = "translated_{originalName}.{ext}";
        }
    } catch (error) {
        showMessage(`⚠️ Server unavailable at ${API_BASE_URL}. Ensure Python server is running. ${error.message}`, 'error');
        addLog(`❌ Failed to connect to server or load config: ${error.message}`);
    }
});

function toggleProviderSettings() {
    const provider = document.getElementById('llmProvider').value;
    const ollamaSettings = document.getElementById('ollamaSettings');
    const geminiSettings = document.getElementById('geminiSettings');
    const modelSelect = document.getElementById('model');
    
    if (provider === 'ollama') {
        ollamaSettings.style.display = 'block';
        geminiSettings.style.display = 'none';
        loadAvailableModels();
    } else if (provider === 'gemini') {
        ollamaSettings.style.display = 'none';
        geminiSettings.style.display = 'block';
        // Set Gemini models
        modelSelect.innerHTML = '';
        const geminiModels = ['gemini-2.0-flash', 'gemini-1.5-pro', 'gemini-1.5-flash'];
        geminiModels.forEach(modelName => {
            const option = document.createElement('option');
            option.value = modelName;
            option.textContent = modelName;
            if (modelName === 'gemini-2.0-flash') option.selected = true;
            modelSelect.appendChild(option);
        });
        addLog('✅ Gemini models loaded');
    }
}

async function loadAvailableModels() {
    const provider = document.getElementById('llmProvider').value;
    if (provider === 'gemini') {
        return; // Gemini models are hardcoded
    }
    
    const modelSelect = document.getElementById('model');
    modelSelect.innerHTML = '<option value="">Loading models...</option>';
    try {
        const currentApiEp = document.getElementById('apiEndpoint').value;
        const response = await fetch(`${API_BASE_URL}/api/models?api_endpoint=${encodeURIComponent(currentApiEp)}`);
        if (!response.ok) {
            const errData = await response.json();
            throw new Error(errData.error || `HTTP error ${response.status}`);
        }
        const data = await response.json();
        modelSelect.innerHTML = '';

        if (data.models && data.models.length > 0) {
            showMessage('', '');

            data.models.forEach(modelName => {
                const option = document.createElement('option');
                option.value = modelName; option.textContent = modelName;
                if (modelName === data.default) option.selected = true;
                modelSelect.appendChild(option);
            });
            addLog(`✅ ${data.count} LLM model(s) loaded. Default: ${data.default}`);
        } else {
            const errorMessage = data.error || 'No LLM models available. Ensure Ollama is running and accessible.';
            showMessage(`⚠️ ${errorMessage}`, 'error');

            modelSelect.innerHTML = '<option value="">Check connection !</option>';
            addLog(`⚠️ No models available from Ollama at ${currentApiEp}`);
        }
    } catch (error) {
        showMessage(`❌ Error fetching models: ${error.message}`, 'error');
        addLog(`❌ Failed to retrieve model list: ${error.message}`);
        modelSelect.innerHTML = '<option value="">Error loading models - Check Ollama</option>';
    }
}

const fileUploadArea = document.getElementById('fileUpload');
fileUploadArea.addEventListener('dragover', (e) => { e.preventDefault(); fileUploadArea.classList.add('dragging'); });
fileUploadArea.addEventListener('dragleave', () => fileUploadArea.classList.remove('dragging'));
fileUploadArea.addEventListener('drop', (e) => {
    e.preventDefault(); fileUploadArea.classList.remove('dragging');
    const files = e.dataTransfer.files;
    if (files.length > 0) {
        Array.from(files).forEach(file => {
            addFileToList(file); 
        });
        updateFileDisplay();
    }
});

function toggleAdvanced() {
    const settings = document.getElementById('advancedSettings');
    document.getElementById('advancedIcon').textContent = settings.classList.toggle('hidden') ? '▼' : '▲';
}
function checkCustomSourceLanguage(selectElement) {
    const customLangInput = document.getElementById('customSourceLang');
    customLangInput.style.display = (selectElement.value === 'Other') ? 'block' : 'none';
    if (selectElement.value === 'Other') customLangInput.focus();
}
function checkCustomTargetLanguage(selectElement) {
    const customLangInput = document.getElementById('customTargetLang');
    customLangInput.style.display = (selectElement.value === 'Other') ? 'block' : 'none';
    if (selectElement.value === 'Other') customLangInput.focus();
}

function handleFileSelect(e) {
    const files = e.target.files;
    if (files.length > 0) {
        Array.from(files).forEach(file => {
            addFileToList(file); 
        });
        updateFileDisplay();
    }
     document.getElementById('fileInput').value = '';
}

async function addFileToList(file) {
    if (filesToProcess.find(f => f.name === file.name)) {
        showMessage(`File '${file.name}' is already in the list.`, 'info');
        return;
    }
    
    const fileExtension = file.name.split('.').pop().toLowerCase();
    const originalNameWithoutExt = file.name.replace(/\.[^/.]+$/, "");
    const outputPattern = document.getElementById('outputFilenamePattern').value || "translated_{originalName}.{ext}";
    
    let processingFileType = 'txt'; 
    if (fileExtension === 'epub') {
        processingFileType = 'epub';
    } else if (fileExtension === 'srt') {
        processingFileType = 'srt';
    }
    
    const outputFilename = outputPattern
        .replace("{originalName}", originalNameWithoutExt)
        .replace("{ext}", fileExtension); 

    showMessage(`Uploading file: ${file.name}...`, 'info');
        
    const formData = new FormData();
    formData.append('file', file);
        
    try {
        const response = await fetch(`${API_BASE_URL}/api/upload`, {
            method: 'POST',
            body: formData
        });
            
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || `Upload failed: ${response.statusText}`);
        }
            
        const uploadResult = await response.json();
            
        filesToProcess.push({
            name: file.name,
            filePath: uploadResult.file_path,      
            fileType: uploadResult.file_type,      
            originalExtension: fileExtension,      
            status: 'Queued',
            outputFilename: outputFilename,
            size: file.size,
            translationId: null,
            result: null,
            content: null 
        });
            
        showMessage(`File '${file.name}' (${uploadResult.file_type}) uploaded. Path: ${uploadResult.file_path}`, 'success');
        updateFileDisplay();
            
    } catch (error) {
        showMessage(`Failed to upload file '${file.name}': ${error.message}`, 'error');
    }
}

function updateFileDisplay() {
    const fileListContainer = document.getElementById('fileListContainer');
    fileListContainer.innerHTML = '';

    if (filesToProcess.length > 0) {
        filesToProcess.forEach(file => {
            const li = document.createElement('li');
            li.setAttribute('data-filename', file.name);
            
            const fileIcon = file.fileType === 'epub' ? '📚' : (file.fileType === 'srt' ? '🎬' : '📄');
            li.textContent = `${fileIcon} ${file.name} (${(file.size / 1024).toFixed(2)} KB) `;
            
            const statusSpan = document.createElement('span');
            statusSpan.className = 'file-status';
            statusSpan.textContent = `(${file.status})`;
            li.appendChild(statusSpan);
            fileListContainer.appendChild(li);
        });
        document.getElementById('fileInfo').classList.remove('hidden');
        document.getElementById('translateBtn').disabled = isBatchActive;
    } else {
        document.getElementById('fileInfo').classList.add('hidden');
        document.getElementById('translateBtn').disabled = true;
    }
}

function resetFiles() {
    filesToProcess = [];
    translationQueue = [];
    currentProcessingJob = null;
    isBatchActive = false;
    lastCompletedJobData = null;

    document.getElementById('fileInput').value = '';
    updateFileDisplay();

    document.getElementById('progressSection').classList.add('hidden');
    document.getElementById('outputSection').classList.add('hidden');
    document.getElementById('logContainer').innerHTML = '';
    document.getElementById('translateBtn').innerHTML = '▶️ Start Translation Batch';
    document.getElementById('translateBtn').disabled = true;
    document.getElementById('interruptBtn').classList.add('hidden');
    document.getElementById('interruptBtn').disabled = false;

    document.getElementById('customSourceLang').style.display = 'none';
    document.getElementById('customTargetLang').style.display = 'none';
    document.getElementById('sourceLang').selectedIndex = 0;
    document.getElementById('targetLang').selectedIndex = 0;
    document.getElementById('statsGrid').style.display = '';
    updateProgress(0);
    showMessage('', '');
    addLog("Form and file list reset.");
}

function showMessage(text, type) {
    const messagesDiv = document.getElementById('messages');
    messagesDiv.innerHTML = text ? `<div class="message ${type}">${text}</div>` : '';
}
function addLog(message) {
    const logContainer = document.getElementById('logContainer');
    const timestamp = new Date().toLocaleTimeString();
    
    logContainer.innerHTML += `<div class="log-entry">
        <span class="log-timestamp">[${timestamp}]</span> ${message}
    </div>`;
    
    logContainer.scrollTop = logContainer.scrollHeight;
}

function escapeHtml(unsafe) {
    return unsafe
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function earlyValidationFail(message) {
    showMessage(message, 'error');
    isBatchActive = false;
    document.getElementById('translateBtn').disabled = filesToProcess.length === 0;
    document.getElementById('translateBtn').innerHTML = '▶️ Start Translation Batch';
    document.getElementById('interruptBtn').classList.add('hidden');
    return false;
}

async function startBatchTranslation() {
    if (isBatchActive || filesToProcess.length === 0) return;

    let sourceLanguageVal = document.getElementById('sourceLang').value;
    if (sourceLanguageVal === 'Other') {
        sourceLanguageVal = document.getElementById('customSourceLang').value.trim();
        if (!sourceLanguageVal) return earlyValidationFail('Please specify the custom source language for the batch.');
    }
    let targetLanguageVal = document.getElementById('targetLang').value;
    if (targetLanguageVal === 'Other') {
        targetLanguageVal = document.getElementById('customTargetLang').value.trim();
        if (!targetLanguageVal) return earlyValidationFail('Please specify the custom target language for the batch.');
    }
    const selectedModel = document.getElementById('model').value;
    if (!selectedModel) return earlyValidationFail('Please select an LLM model for the batch.');
    const ollamaApiEndpoint = document.getElementById('apiEndpoint').value.trim();
    if (!ollamaApiEndpoint) return earlyValidationFail('Ollama API Endpoint cannot be empty for the batch.');

    isBatchActive = true;
    translationQueue = [...filesToProcess];

    document.getElementById('translateBtn').disabled = true;
    document.getElementById('translateBtn').innerHTML = '⏳ Batch in Progress...';
    document.getElementById('interruptBtn').classList.remove('hidden');
    document.getElementById('interruptBtn').disabled = false;

    document.getElementById('outputSection').classList.add('hidden');
    document.getElementById('logContainer').innerHTML = '';

    addLog(`🚀 Batch translation started for ${translationQueue.length} file(s).`);
    showMessage(`Batch of ${translationQueue.length} file(s) initiated.`, 'info');

    processNextFileInQueue();
}

async function processNextFileInQueue() {
    if (currentProcessingJob) return;

    if (translationQueue.length === 0) {
        isBatchActive = false;
        document.getElementById('translateBtn').disabled = filesToProcess.length === 0;
        document.getElementById('translateBtn').innerHTML = '▶️ Start Translation Batch';
        document.getElementById('interruptBtn').classList.add('hidden');
        showMessage('✅ Batch translation completed for all files!', 'success');
        addLog('🏁 All files in the batch have been processed.');
        document.getElementById('currentFileProgressTitle').textContent = `📊 Batch Completed`;
        return;
    }

    const fileToTranslate = translationQueue.shift();

    updateProgress(0);
    ['totalChunks', 'completedChunks', 'failedChunks'].forEach(id => document.getElementById(id).textContent = '0');
    document.getElementById('elapsedTime').textContent = '0s';
    document.getElementById('logContainer').innerHTML = '';
    document.getElementById('outputSection').classList.add('hidden');
    document.getElementById('downloadBtn').disabled = true;

    if (fileToTranslate.fileType === 'epub') {
        document.getElementById('statsGrid').style.display = 'none';
    } else if (fileToTranslate.fileType === 'srt') {
        document.getElementById('statsGrid').style.display = '';
    } else {
        document.getElementById('statsGrid').style.display = '';
    }

    document.getElementById('currentFileProgressTitle').textContent = `📊 Translating: ${fileToTranslate.name}`;
    document.getElementById('progressSection').classList.remove('hidden');
    addLog(`▶️ Starting translation for: ${fileToTranslate.name} (${fileToTranslate.fileType.toUpperCase()})`);
    updateFileStatusInList(fileToTranslate.name, 'Preparing...');

    let sourceLanguageVal = document.getElementById('sourceLang').value;
    if (sourceLanguageVal === 'Other') sourceLanguageVal = document.getElementById('customSourceLang').value.trim();
    let targetLanguageVal = document.getElementById('targetLang').value;
    if (targetLanguageVal === 'Other') targetLanguageVal = document.getElementById('customTargetLang').value.trim();

    const provider = document.getElementById('llmProvider').value;
    
    // Validate Gemini API key if using Gemini
    if (provider === 'gemini') {
        const geminiApiKey = document.getElementById('geminiApiKey').value.trim();
        if (!geminiApiKey) {
            addLog('❌ Error: Gemini API key is required when using Gemini provider');
            showMessage('Please enter your Gemini API key', 'error');
            updateFileStatusInList(fileToTranslate.name, 'Error: Missing API key');
            currentProcessingJob = null;
            processNextFileInQueue();
            return;
        }
    }
    
    const config = {
        source_language: sourceLanguageVal,
        target_language: targetLanguageVal,
        model: document.getElementById('model').value,
        llm_api_endpoint: document.getElementById('apiEndpoint').value,
        llm_provider: provider,
        gemini_api_key: provider === 'gemini' ? document.getElementById('geminiApiKey').value : '',
        chunk_size: parseInt(document.getElementById('chunkSize').value),
        timeout: parseInt(document.getElementById('timeout').value),
        context_window: parseInt(document.getElementById('contextWindow').value),
        max_attempts: parseInt(document.getElementById('maxAttempts').value),
        retry_delay: parseInt(document.getElementById('retryDelay').value),
        output_filename: fileToTranslate.outputFilename,
        file_type: fileToTranslate.fileType,
        custom_instructions: document.getElementById('customInstructions').value.trim()
    };

    if (fileToTranslate.fileType === 'epub' || fileToTranslate.fileType === 'srt') {
        if (!fileToTranslate.filePath) {
             addLog(`❌ Critical Error: ${fileToTranslate.fileType.toUpperCase()} file ${fileToTranslate.name} has no server path. Upload might have failed silently or logic error.`);
             showMessage(`Cannot process ${fileToTranslate.fileType.toUpperCase()} ${fileToTranslate.name}: server path missing.`, 'error');
             updateFileStatusInList(fileToTranslate.name, 'Path Error');
             currentProcessingJob = null; 
             processNextFileInQueue(); 
             return;
        }
        config.file_path = fileToTranslate.filePath;
    } else { 
        if (fileToTranslate.content) {
            config.text = fileToTranslate.content; 
        } else {
            if (!fileToTranslate.filePath) {
                 addLog(`❌ Critical Error: TXT file ${fileToTranslate.name} has no server path and no direct content. Upload might have failed or logic error.`);
                 showMessage(`Cannot process TXT file ${fileToTranslate.name}: server path or content missing.`, 'error');
                 updateFileStatusInList(fileToTranslate.name, 'Input Error');
                 currentProcessingJob = null;
                 processNextFileInQueue();
                 return;
            }
            config.file_path = fileToTranslate.filePath;
        }
    }

    try {
        const response = await fetch(`${API_BASE_URL}/api/translate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        });
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || `Server error ${response.status} for ${fileToTranslate.name}.`);
        }
        const data = await response.json();
        currentProcessingJob = { fileRef: fileToTranslate, translationId: data.translation_id };
        fileToTranslate.translationId = data.translation_id;
        updateFileStatusInList(fileToTranslate.name, 'Submitted', data.translation_id);

    } catch (error) {
        addLog(`❌ Error initiating translation for ${fileToTranslate.name}: ${error.message}`);
        showMessage(`Error starting ${fileToTranslate.name}: ${error.message}`, 'error');
        updateFileStatusInList(fileToTranslate.name, 'Initiation Error');
        currentProcessingJob = null;
        processNextFileInQueue();
    }
}

async function interruptCurrentTranslation() {
    if (!isBatchActive || !currentProcessingJob) {
        showMessage('No active translation to interrupt.', 'info');
        return;
    }

    const fileToInterrupt = currentProcessingJob.fileRef;
    const tidToInterrupt = currentProcessingJob.translationId;

    document.getElementById('interruptBtn').disabled = true;
    document.getElementById('interruptBtn').innerHTML = '⏳ Interrupting...';
    addLog(`🛑 User requested interruption for ${fileToInterrupt.name} (ID: ${tidToInterrupt}). This will stop the batch.`);
    translationQueue = [];

    try {
        const response = await fetch(`${API_BASE_URL}/api/translation/${tidToInterrupt}/interrupt`, { method: 'POST' });
        if (!response.ok) {
            const errData = await response.json();
            throw new Error(errData.message || `Failed to send interrupt signal for ${fileToInterrupt.name}.`);
        }
        showMessage(`ℹ️ Interruption for ${fileToInterrupt.name} requested. Batch will stop after this file.`, 'info');
    } catch (error) {
        showMessage(`❌ Error sending interruption for ${fileToInterrupt.name}: ${error.message}`, 'error');
         document.getElementById('interruptBtn').disabled = false;
         document.getElementById('interruptBtn').innerHTML = '⏹️ Interrupt Current & Stop Batch';
    }
}

function updateProgress(percent) {
    const progressBar = document.getElementById('progressBar');
    progressBar.style.width = percent + '%';
    progressBar.textContent = Math.round(percent) + '%';
}

function downloadLastTranslation() {
    if (!lastCompletedJobData || !lastCompletedJobData.translationId) {
        showMessage('No completed translation available for download, or ID missing.', 'error'); return;
    }
    if (lastCompletedJobData.status !== 'completed' && lastCompletedJobData.status !== 'interrupted') {
         showMessage(`Cannot download file as its status is '${lastCompletedJobData.status}'.`, 'error'); return;
    }
    
    const fileTypeIcon = lastCompletedJobData.fileType === 'epub' ? '📚' : (lastCompletedJobData.fileType === 'srt' ? '🎬' : '📄');
    const downloadUrl = `${API_BASE_URL}/api/download/${lastCompletedJobData.translationId}`;
    addLog(`${fileTypeIcon} Initiating download for ${lastCompletedJobData.outputFilename} from: ${downloadUrl}`);
    window.location.href = downloadUrl;
}