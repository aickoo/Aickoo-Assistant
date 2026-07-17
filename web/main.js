// Trae AI Assistant - Main JavaScript
// VSCode-like interface functionality

// Global state
let currentSessionId = null;
let isProcessing = false;
let activeTabs = new Map(); // sessionId -> tabElement
let sidebarCollapsed = false;

// Initialize when page loads
document.addEventListener('DOMContentLoaded', function() {
    console.log('Trae AI Assistant loaded');
    
    // Initialize UI components
    initializeActivityBar();
    initializeTabs();
    initializeKeyboardShortcuts();
    
    // Update status indicator
    updateStatusIndicator(true);
    
    // Load initial data
    loadInitialData();
    
    // Set up auto-resize for textarea
    const messageInput = document.getElementById('message-input');
    if (messageInput) {
        messageInput.addEventListener('input', function() {
            autoResize(this);
        });
    }
});

// Initialize activity bar
function initializeActivityBar() {
    const activityItems = document.querySelectorAll('.activity-item');
    activityItems.forEach(item => {
        item.addEventListener('click', function() {
            const view = this.dataset.view;
            
            // Update active state
            activityItems.forEach(i => i.classList.remove('active'));
            this.classList.add('active');
            
            // Switch view
            switchView(view);
        });
    });
}

// Switch between different views
function switchView(view) {
    console.log('Switching to view:', view);
    
    // Update UI based on view
    const userStatus = document.getElementById('user-status');
    if (userStatus) {
        userStatus.textContent = view.charAt(0).toUpperCase() + view.slice(1);
    }
    
    // Show/hide relevant components
    switch(view) {
        case 'chat':
            // Show chat interface
            document.getElementById('input-area').style.display = 'flex';
            break;
        case 'files':
            // Show file browser (placeholder)
            showNotification('Files', 'File browser coming soon', 'info');
            break;
        case 'search':
            // Show search (placeholder)
            showNotification('Search', 'Search functionality coming soon', 'info');
            break;
        case 'settings':
            // Show settings (placeholder)
            showNotification('Settings', 'Settings panel coming soon', 'info');
            break;
    }
}

// Initialize tab system
function initializeTabs() {
    // Close tab button handlers
    document.addEventListener('click', function(e) {
        if (e.target.closest('.tab-close')) {
            const tab = e.target.closest('.editor-tab');
            if (tab) {
                const sessionId = tab.dataset.session;
                closeTab(sessionId);
            }
        }
    });
    
    // Tab click handlers
    document.addEventListener('click', function(e) {
        const tab = e.target.closest('.editor-tab');
        if (tab && !e.target.closest('.tab-close')) {
            const sessionId = tab.dataset.session;
            switchToTab(sessionId);
        }
    });
}

// Create a new tab for a session
function createTab(sessionId, title) {
    const tabsContainer = document.getElementById('editor-tabs');
    
    // Check if tab already exists
    if (activeTabs.has(sessionId)) {
        switchToTab(sessionId);
        return;
    }
    
    // Create new tab
    const tab = document.createElement('div');
    tab.className = 'editor-tab';
    tab.dataset.session = sessionId;
    tab.innerHTML = `
        <i class="fas fa-comment tab-icon"></i>
        <span>${escapeHtml(title)}</span>
        <button class="tab-close">
            <i class="fas fa-times"></i>
        </button>
    `;
    
    tabsContainer.appendChild(tab);
    activeTabs.set(sessionId, tab);
    
    // Switch to new tab
    switchToTab(sessionId);
}

// Switch to a specific tab
function switchToTab(sessionId) {
    // Update tab states
    document.querySelectorAll('.editor-tab').forEach(tab => {
        tab.classList.remove('active');
    });
    
    const tab = activeTabs.get(sessionId);
    if (tab) {
        tab.classList.add('active');
    }
    
    // Update UI based on session
    if (sessionId === 'welcome') {
        showWelcomeScreen();
    } else {
        showChatSession(sessionId);
    }
}

// Close a tab
function closeTab(sessionId) {
    if (sessionId === 'welcome') {
        // Don't close welcome tab
        return;
    }
    
    const tab = activeTabs.get(sessionId);
    if (tab) {
        tab.remove();
        activeTabs.delete(sessionId);
        
        // Switch to another tab if available
        if (activeTabs.size > 0) {
            const firstTab = Array.from(activeTabs.keys())[0];
            switchToTab(firstTab);
        } else {
            switchToTab('welcome');
        }
        
        // If this was the current session, clear it
        if (currentSessionId === sessionId) {
            currentSessionId = null;
        }
    }
}

// Show welcome screen
function showWelcomeScreen() {
    document.getElementById('welcome-screen').style.display = 'flex';
    document.getElementById('chat-container').style.display = 'none';
    document.getElementById('input-area').style.display = 'none';
    
    // Update session title
    document.querySelectorAll('.editor-tab').forEach(tab => {
        if (tab.dataset.session === 'welcome') {
            tab.querySelector('span').textContent = 'Welcome';
        }
    });
}

// Show chat session
function showChatSession(sessionId) {
    document.getElementById('welcome-screen').style.display = 'none';
    document.getElementById('chat-container').style.display = 'block';
    document.getElementById('input-area').style.display = 'flex';
    
    // Load session messages
    switchToSession(sessionId);
}

// Toggle sidebar visibility
function toggleSidebar() {
    const sidebar = document.querySelector('.sidebar');
    const toggleButton = document.querySelector('.sidebar-action i');
    
    sidebarCollapsed = !sidebarCollapsed;
    
    if (sidebarCollapsed) {
        sidebar.classList.add('collapsed');
        toggleButton.className = 'fas fa-chevron-right';
    } else {
        sidebar.classList.remove('collapsed');
        toggleButton.className = 'fas fa-chevron-left';
    }
}

// Initialize keyboard shortcuts
function initializeKeyboardShortcuts() {
    document.addEventListener('keydown', function(e) {
        // Ctrl/Cmd + K for command palette
        if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
            e.preventDefault();
            showCommandPalette();
        }
        
        // Ctrl/Cmd + N for new session
        if ((e.ctrlKey || e.metaKey) && e.key === 'n') {
            e.preventDefault();
            createNewSession();
        }
        
        // Ctrl/Cmd + , for settings
        if ((e.ctrlKey || e.metaKey) && e.key === ',') {
            e.preventDefault();
            switchView('settings');
        }
        
        // Escape to close modals
        if (e.key === 'Escape') {
            const commandPalette = document.querySelector('.command-palette');
            if (commandPalette) {
                commandPalette.remove();
            }
        }
    });
}

// Show command palette
function showCommandPalette() {
    // Remove existing palette
    const existingPalette = document.querySelector('.command-palette');
    if (existingPalette) {
        existingPalette.remove();
    }
    
    // Create command palette
    const palette = document.createElement('div');
    palette.className = 'command-palette';
    palette.innerHTML = `
        <input type="text" class="command-input" placeholder="Type a command..." autofocus>
        <div class="command-list">
            <div class="command-item selected">
                <i class="fas fa-plus command-icon"></i>
                <div class="command-title">New Session</div>
                <div class="command-shortcut">Ctrl+N</div>
            </div>
            <div class="command-item">
                <i class="fas fa-folder command-icon"></i>
                <div class="command-title">Open File</div>
                <div class="command-shortcut">Ctrl+O</div>
            </div>
            <div class="command-item">
                <i class="fas fa-search command-icon"></i>
                <div class="command-title">Search Files</div>
                <div class="command-shortcut">Ctrl+Shift+F</div>
            </div>
            <div class="command-item">
                <i class="fas fa-cog command-icon"></i>
                <div class="command-title">Settings</div>
                <div class="command-shortcut">Ctrl+,</div>
            </div>
            <div class="command-item">
                <i class="fas fa-question command-icon"></i>
                <div class="command-title">Help</div>
                <div class="command-shortcut">F1</div>
            </div>
        </div>
    `;
    
    document.body.appendChild(palette);
    
    // Focus input
    const input = palette.querySelector('.command-input');
    input.focus();
    
    // Handle input
    input.addEventListener('input', function() {
        filterCommands(this.value);
    });
    
    // Handle keyboard navigation
    input.addEventListener('keydown', function(e) {
        const items = palette.querySelectorAll('.command-item');
        const selected = palette.querySelector('.command-item.selected');
        let index = Array.from(items).indexOf(selected);
        
        switch(e.key) {
            case 'ArrowDown':
                e.preventDefault();
                if (index < items.length - 1) {
                    items[index].classList.remove('selected');
                    items[index + 1].classList.add('selected');
                }
                break;
            case 'ArrowUp':
                e.preventDefault();
                if (index > 0) {
                    items[index].classList.remove('selected');
                    items[index - 1].classList.add('selected');
                }
                break;
            case 'Enter':
                e.preventDefault();
                if (selected) {
                    executeCommand(selected.querySelector('.command-title').textContent);
                    palette.remove();
                }
                break;
        }
    });
}

// Filter commands in palette
function filterCommands(query) {
    const items = document.querySelectorAll('.command-item');
    const lowerQuery = query.toLowerCase();
    
    items.forEach(item => {
        const title = item.querySelector('.command-title').textContent.toLowerCase();
        if (title.includes(lowerQuery)) {
            item.style.display = 'flex';
        } else {
            item.style.display = 'none';
        }
    });
    
    // Select first visible item
    const visibleItems = Array.from(items).filter(item => item.style.display !== 'none');
    if (visibleItems.length > 0) {
        items.forEach(item => item.classList.remove('selected'));
        visibleItems[0].classList.add('selected');
    }
}

// Execute command from palette
function executeCommand(command) {
    switch(command) {
        case 'New Session':
            createNewSession();
            break;
        case 'Open File':
            showNotification('Open File', 'File dialog would open here', 'info');
            break;
        case 'Search Files':
            switchView('search');
            break;
        case 'Settings':
            switchView('settings');
            break;
        case 'Help':
            showNotification('Help', 'Documentation would open here', 'info');
            break;
    }
}

// Update connection status indicator
function updateStatusIndicator(connected) {
    const statusDot = document.getElementById('status-dot');
    const statusText = document.getElementById('status-text');
    
    if (statusDot && statusText) {
        if (connected) {
            statusDot.className = 'status-dot connected';
            statusText.textContent = 'Connected';
        } else {
            statusDot.className = 'status-dot disconnected';
            statusText.textContent = 'Disconnected';
        }
    }
}

// Load initial data
function loadInitialData() {
    // Load sessions
    if (typeof eel !== 'undefined') {
        eel.get_sessions()(function(sessions) {
            console.log('Loaded sessions:', sessions);
            // Sessions will be loaded by the main script in index.html
        });
    }
}

// Handle window resize
window.addEventListener('resize', function() {
    // Auto-resize textarea
    const messageInput = document.getElementById('message-input');
    if (messageInput) {
        autoResize(messageInput);
    }
    
    // Ensure chat container scrolls to bottom
    const chatContainer = document.getElementById('chat-container');
    if (chatContainer) {
        chatContainer.scrollTop = chatContainer.scrollHeight;
    }
});

// Handle beforeunload event
window.addEventListener('beforeunload', function(e) {
    // Notify Python backend that we're closing
    if (typeof eel !== 'undefined') {
        try {
            eel.app_closing();
        } catch (error) {
            console.log('Error notifying app closing:', error);
        }
    }
});

// Auto-resize textarea
function autoResize(textarea) {
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 200) + 'px';
}

// Utility function to format code blocks with VSCode theme
function formatCodeBlocks(content) {
    // Enhanced code block formatting with language detection
    return content.replace(/```(\w+)?\n([\s\S]*?)```/g, function(match, lang, code) {
        const language = lang || 'text';
        const escapedCode = escapeHtml(code);
        return `<pre data-language="${language}"><code class="language-${language}">${escapedCode}</code></pre>`;
    });
}

// Utility function to escape HTML
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Show notification (VSCode style)
function showNotification(title, message, type = 'info') {
    console.log(`Notification [${type}]: ${title} - ${message}`);
    
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `notification ${type}`;
    notification.innerHTML = `
        <div class="notification-header">
            <div class="notification-title">
                <i class="fas fa-${getNotificationIcon(type)}"></i>
                ${escapeHtml(title)}
            </div>
            <button class="notification-close">
                <i class="fas fa-times"></i>
            </button>
        </div>
        <div class="notification-body">
            ${escapeHtml(message)}
        </div>
    `;
    
    // Add to document
    document.body.appendChild(notification);
    
    // Add close handler
    const closeBtn = notification.querySelector('.notification-close');
    closeBtn.addEventListener('click', () => {
        notification.remove();
    });
    
    // Remove after 5 seconds
    setTimeout(() => {
        if (notification.parentNode) {
            notification.remove();
        }
    }, 5000);
}

// Get icon for notification type
function getNotificationIcon(type) {
    switch(type) {
        case 'info': return 'info-circle';
        case 'success': return 'check-circle';
        case 'warning': return 'exclamation-triangle';
        case 'error': return 'exclamation-circle';
        default: return 'info-circle';
    }
}

// Export functions for Python to call
if (typeof eel !== 'undefined') {
    // Expose functions to Python
    eel.expose(showNotification);
    eel.expose(updateUI);
    eel.expose(handleError);
}

// Update UI based on Python data
function updateUI(data) {
    if (data.type === 'sessions') {
        // Sessions were updated
        if (typeof loadSessions === 'function') {
            loadSessions();
        }
    } else if (data.type === 'message') {
        // New message received
        if (typeof addMessageToUI === 'function') {
            addMessageToUI(data.role, data.content, data.timestamp);
        }
    }
}

// Handle error from Python
function handleError(error) {
    console.error('Error from Python:', error);
    if (typeof showError === 'function') {
        showError(error);
    }
}

// Add missing functions that are referenced in index.html
function handleKeyPress(event) {
    if (event.ctrlKey && event.key === 'Enter') {
        event.preventDefault();
        sendMessage();
    }
}

// These functions will be defined in the main script in index.html
// They are referenced here for completeness
function sendMessage() {
    // Will be defined in index.html
    console.log('sendMessage called');
}

function createNewSession() {
    // Will be defined in index.html
    console.log('createNewSession called');
}

function loadSessions() {
    // Will be defined in index.html
    console.log('loadSessions called');
}

function switchToSession(sessionId) {
    // Will be defined in index.html
    console.log('switchToSession called:', sessionId);
}

function addMessageToUI(role, content, timestamp) {
    // Will be defined in index.html
    console.log('addMessageToUI called:', role, content.substring(0, 50));
}

function showError(message) {
    // Will be defined in index.html
    console.log('showError called:', message);
}

/* ============================================
   File Explorer Functions
   ============================================ */

// Open file explorer tab
function openFileExplorer() {
    const explorerTab = document.querySelector('.editor-tab[data-session="explorer"]');
    if (explorerTab) {
        explorerTab.style.display = 'flex';
        switchToTab('explorer');
    }
    refreshFileExplorer();
}

// Refresh file explorer
function refreshFileExplorer(path = ".") {
    const fileTree = document.getElementById('file-tree');
    if (!fileTree) return;
    
    fileTree.innerHTML = `
        <div class="loading-placeholder">
            <div class="loading-spinner"></div>
            <span>Loading file tree...</span>
        </div>
    `;
    
    // Load files from Python backend
    if (typeof eel !== 'undefined') {
        eel.list_files(path)(function(response) {
            if (response && !response.error) {
                renderRealFileTree(fileTree, response, path);
            } else {
                showNotification('File Error', response?.error || 'Failed to load files', 'error');
                loadSampleFileTree(); // Fallback to sample
            }
        });
    } else {
        // Fallback to sample if Eel not available
        setTimeout(() => {
            loadSampleFileTree();
        }, 500);
    }
}

// Load sample file tree (for demonstration)
function loadSampleFileTree() {
    const fileTree = document.getElementById('file-tree');
    if (!fileTree) return;
    
    const sampleFiles = [
        { name: 'src', type: 'folder', children: [
            { name: 'main.py', type: 'file', size: '2.1 KB' },
            { name: 'utils.py', type: 'file', size: '1.5 KB' },
            { name: 'config', type: 'folder', children: [
                { name: 'settings.json', type: 'file', size: '0.8 KB' }
            ]}
        ]},
        { name: 'tests', type: 'folder', children: [
            { name: 'test_main.py', type: 'file', size: '3.2 KB' }
        ]},
        { name: 'requirements.txt', type: 'file', size: '0.5 KB' },
        { name: 'README.md', type: 'file', size: '1.2 KB' },
        { name: '.gitignore', type: 'file', size: '0.3 KB' }
    ];
    
    fileTree.innerHTML = '';
    renderFileTree(fileTree, sampleFiles);
}

// Render file tree recursively
function renderFileTree(container, files, level = 0) {
    files.forEach(file => {
        const fileElement = document.createElement('div');
        fileElement.className = 'file-item';
        fileElement.dataset.path = file.name;
        fileElement.dataset.type = file.type;
        
        const icon = file.type === 'folder' ? 'fa-folder' : getFileIcon(file.name);
        const toggle = file.type === 'folder' ? 
            `<div class="folder-toggle" onclick="toggleFolder(this)"><i class="fas fa-chevron-right"></i></div>` : 
            '<div class="folder-toggle"></div>';
        
        fileElement.innerHTML = `
            ${toggle}
            <div class="file-icon">
                <i class="fas ${icon}"></i>
            </div>
            <div class="file-name">${escapeHtml(file.name)}</div>
            ${file.size ? `<div class="file-size">${file.size}</div>` : ''}
        `;
        
        container.appendChild(fileElement);
        
        // Add click handler
        fileElement.addEventListener('click', (e) => {
            if (!e.target.closest('.folder-toggle')) {
                handleFileClick(file);
            }
        });
        
        // Add context menu
        fileElement.addEventListener('contextmenu', (e) => {
            e.preventDefault();
            showFileContextMenu(e, file);
        });
        
        // Add children if folder
        if (file.type === 'folder' && file.children) {
            const childrenContainer = document.createElement('div');
            childrenContainer.className = 'folder-children';
            childrenContainer.style.display = 'none';
            container.appendChild(childrenContainer);
            renderFileTree(childrenContainer, file.children, level + 1);
        }
    });
}

// Render real file tree from Python backend data
function renderRealFileTree(container, files, currentPath = ".") {
    container.innerHTML = '';
    
    // Add ".." for parent directory if not at root
    if (currentPath !== "." && currentPath !== "/") {
        const parentElement = document.createElement('div');
        parentElement.className = 'file-item';
        parentElement.dataset.path = '..';
        parentElement.dataset.type = 'folder';
        
        parentElement.innerHTML = `
            <div class="folder-toggle"></div>
            <div class="file-icon">
                <i class="fas fa-level-up-alt"></i>
            </div>
            <div class="file-name">..</div>
        `;
        
        parentElement.addEventListener('click', () => {
            const parentPath = currentPath.split('/').slice(0, -1).join('/') || '.';
            refreshFileExplorer(parentPath);
        });
        
        container.appendChild(parentElement);
    }
    
    files.forEach(file => {
        const fileElement = document.createElement('div');
        fileElement.className = 'file-item';
        fileElement.dataset.path = file.path;
        fileElement.dataset.type = file.is_dir ? 'folder' : 'file';
        fileElement.dataset.name = file.name;
        
        const icon = file.is_dir ? 'fa-folder' : getFileIcon(file.name);
        const toggle = file.is_dir ? 
            `<div class="folder-toggle" onclick="toggleFolder(this)"><i class="fas fa-chevron-right"></i></div>` : 
            '<div class="folder-toggle"></div>';
        
        // Format file size
        let sizeText = '';
        if (!file.is_dir && file.size) {
            if (file.size < 1024) {
                sizeText = `${file.size} B`;
            } else if (file.size < 1024 * 1024) {
                sizeText = `${(file.size / 1024).toFixed(1)} KB`;
            } else {
                sizeText = `${(file.size / (1024 * 1024)).toFixed(1)} MB`;
            }
        }
        
        fileElement.innerHTML = `
            ${toggle}
            <div class="file-icon">
                <i class="fas ${icon}"></i>
            </div>
            <div class="file-name">${escapeHtml(file.name)}</div>
            ${sizeText ? `<div class="file-size">${sizeText}</div>` : ''}
        `;
        
        container.appendChild(fileElement);
        
        // Add click handler
        fileElement.addEventListener('click', (e) => {
            if (!e.target.closest('.folder-toggle')) {
                handleRealFileClick(file, currentPath);
            }
        });
        
        // Add context menu
        fileElement.addEventListener('contextmenu', (e) => {
            e.preventDefault();
            showRealFileContextMenu(e, file, currentPath);
        });
        
        // Note: For real implementation, we would lazy load folder contents
        // when the folder is expanded, not pre-load all children
    });
}

// Get file icon based on extension
function getFileIcon(filename) {
    const ext = filename.split('.').pop().toLowerCase();
    const iconMap = {
        'py': 'fa-file-code',
        'js': 'fa-file-code',
        'ts': 'fa-file-code',
        'html': 'fa-file-code',
        'css': 'fa-file-code',
        'json': 'fa-file-code',
        'md': 'fa-file-alt',
        'txt': 'fa-file-alt',
        'pdf': 'fa-file-pdf',
        'jpg': 'fa-file-image',
        'png': 'fa-file-image',
        'gitignore': 'fa-file-code'
    };
    return iconMap[ext] || 'fa-file';
}

// Toggle folder expansion
function toggleFolder(toggleElement) {
    const folderItem = toggleElement.closest('.file-item');
    const childrenContainer = folderItem.nextElementSibling;
    
    if (childrenContainer && childrenContainer.classList.contains('folder-children')) {
        const isCollapsed = childrenContainer.style.display === 'none';
        childrenContainer.style.display = isCollapsed ? 'block' : 'none';
        toggleElement.classList.toggle('collapsed', !isCollapsed);
        toggleElement.querySelector('i').className = isCollapsed ? 
            'fas fa-chevron-down' : 'fas fa-chevron-right';
    }
}

// Handle file click (for sample files)
function handleFileClick(file) {
    if (file.type === 'file') {
        openFileInEditor(file.name, file.content || '');
        updateFilePreview(file.name, file.content || '');
    }
}

// Handle real file click (for files from Python backend)
function handleRealFileClick(file, currentPath) {
    if (file.is_dir) {
        // Navigate into directory
        refreshFileExplorer(file.path);
    } else {
        // Read and open file
        if (typeof eel !== 'undefined') {
            eel.read_file(file.path)(function(response) {
                if (response && !response.error) {
                    openFileInEditor(file.name, response.content);
                    updateFilePreview(file.name, response.content);
                } else {
                    showNotification('File Error', response?.error || 'Failed to read file', 'error');
                }
            });
        } else {
            showNotification('File Error', 'Eel not available', 'error');
        }
    }
}

// Show file context menu (for sample files)
function showFileContextMenu(event, file) {
    // Remove existing context menu
    const existingMenu = document.querySelector('.file-context-menu');
    if (existingMenu) {
        existingMenu.remove();
    }
    
    // Create context menu
    const contextMenu = document.createElement('div');
    contextMenu.className = 'file-context-menu';
    contextMenu.style.left = `${event.pageX}px`;
    contextMenu.style.top = `${event.pageY}px`;
    
    const items = file.type === 'folder' ? [
        { icon: 'fa-folder-open', label: 'Open', action: () => handleFileClick(file) },
        { icon: 'fa-edit', label: 'Rename', action: () => renameFile(file.name, file.name) },
        { icon: 'fa-trash', label: 'Delete', action: () => deleteFile(file.name) },
        { type: 'divider' },
        { icon: 'fa-file', label: 'New File', action: () => createNewFileInFolder(file.name) },
        { icon: 'fa-folder-plus', label: 'New Folder', action: () => createNewFolderInFolder(file.name) }
    ] : [
        { icon: 'fa-edit', label: 'Edit', action: () => handleFileClick(file) },
        { icon: 'fa-copy', label: 'Copy', action: () => copyFile(file.name) },
        { icon: 'fa-trash', label: 'Delete', action: () => deleteFile(file.name) },
        { type: 'divider' },
        { icon: 'fa-download', label: 'Download', action: () => downloadFile(file.name) }
    ];
    
    items.forEach(item => {
        if (item.type === 'divider') {
            const divider = document.createElement('div');
            divider.className = 'context-menu-divider';
            contextMenu.appendChild(divider);
        } else {
            const menuItem = document.createElement('div');
            menuItem.className = 'context-menu-item';
            menuItem.innerHTML = `
                <i class="fas ${item.icon}"></i>
                <span>${item.label}</span>
            `;
            menuItem.onclick = () => {
                item.action();
                contextMenu.remove();
            };
            contextMenu.appendChild(menuItem);
        }
    });
    
    document.body.appendChild(contextMenu);
    
    // Remove menu when clicking elsewhere
    setTimeout(() => {
        document.addEventListener('click', function removeMenu() {
            if (contextMenu && contextMenu.parentNode) {
                contextMenu.remove();
            }
            document.removeEventListener('click', removeMenu);
        });
    }, 10);
}

// Show real file context menu (for files from Python backend)
function showRealFileContextMenu(event, file, currentPath) {
    // Remove existing context menu
    const existingMenu = document.querySelector('.file-context-menu');
    if (existingMenu) {
        existingMenu.remove();
    }
    
    // Create context menu
    const contextMenu = document.createElement('div');
    contextMenu.className = 'file-context-menu';
    contextMenu.style.left = `${event.pageX}px`;
    contextMenu.style.top = `${event.pageY}px`;
    
    const items = file.is_dir ? [
        { icon: 'fa-folder-open', label: 'Open', action: () => handleRealFileClick(file, currentPath) },
        { icon: 'fa-edit', label: 'Rename', action: () => {
            const newName = prompt(`Rename "${file.name}" to:`, file.name);
            if (newName) renameFile(file.path, newName);
        }},
        { icon: 'fa-trash', label: 'Delete', action: () => deleteFile(file.path) },
        { type: 'divider' },
        { icon: 'fa-file', label: 'New File', action: () => {
            const filename = prompt(`Create new file in "${file.name}":`, 'newfile.py');
            if (filename) {
                const filePath = file.path + '/' + filename;
                eel.write_file(filePath, '')(function(response) {
                    if (response && response.success) {
                        showNotification('File Created', `Created: ${filename}`, 'success');
                        refreshFileExplorer(file.path);
                    } else {
                        showNotification('File Error', response?.error || 'Failed to create file', 'error');
                    }
                });
            }
        }},
        { icon: 'fa-folder-plus', label: 'New Folder', action: () => {
            const foldername = prompt(`Create new folder in "${file.name}":`, 'newfolder');
            if (foldername) {
                const folderPath = file.path + '/' + foldername;
                eel.create_directory(folderPath)(function(response) {
                    if (response && response.success) {
                        showNotification('Folder Created', `Created: ${foldername}`, 'success');
                        refreshFileExplorer(file.path);
                    } else {
                        showNotification('Folder Error', response?.error || 'Failed to create folder', 'error');
                    }
                });
            }
        }}
    ] : [
        { icon: 'fa-edit', label: 'Edit', action: () => handleRealFileClick(file, currentPath) },
        { icon: 'fa-copy', label: 'Copy', action: () => copyFile(file.name) },
        { icon: 'fa-trash', label: 'Delete', action: () => deleteFile(file.path) },
        { type: 'divider' },
        { icon: 'fa-download', label: 'Download', action: () => downloadFile(file.name) }
    ];
    
    items.forEach(item => {
        if (item.type === 'divider') {
            const divider = document.createElement('div');
            divider.className = 'context-menu-divider';
            contextMenu.appendChild(divider);
        } else {
            const menuItem = document.createElement('div');
            menuItem.className = 'context-menu-item';
            menuItem.innerHTML = `
                <i class="fas ${item.icon}"></i>
                <span>${item.label}</span>
            `;
            menuItem.onclick = () => {
                item.action();
                contextMenu.remove();
            };
            contextMenu.appendChild(menuItem);
        }
    });
    
    document.body.appendChild(contextMenu);
    
    // Remove menu when clicking elsewhere
    setTimeout(() => {
        document.addEventListener('click', function removeMenu() {
            if (contextMenu && contextMenu.parentNode) {
                contextMenu.remove();
            }
            document.removeEventListener('click', removeMenu);
        });
    }, 10);
}

// Open file in editor
function openFileInEditor(filename, content) {
    // Show code editor, hide chat
    document.getElementById('chat-container').style.display = 'none';
    document.getElementById('code-editor-container').style.display = 'flex';
    
    // Update editor tab
    const editorTab = document.querySelector('.editor-file-tab');
    editorTab.querySelector('.file-name').textContent = filename;
    editorTab.dataset.file = filename;
    
    // Update code editor
    const codeInput = document.getElementById('code-input');
    codeInput.value = content || `# ${filename}\n# File opened in Trae Editor\n\nprint("Hello from ${filename}")`;
    
    // Update line numbers
    updateLineNumbers();
    
    // Focus editor
    codeInput.focus();
}

// Update file preview
function updateFilePreview(filename, content) {
    const preview = document.getElementById('file-preview');
    if (!preview) return;
    
    preview.innerHTML = `
        <div class="preview-content">
            <div style="margin-bottom: 12px; color: var(--vscode-text-secondary); font-size: 11px;">
                <i class="fas ${getFileIcon(filename)}"></i>
                ${escapeHtml(filename)}
            </div>
            <pre style="margin: 0; background: transparent; border: none; padding: 0;">${escapeHtml(content || 'No content available')}</pre>
        </div>
    `;
}

// Update line numbers in editor
function updateLineNumbers() {
    const codeInput = document.getElementById('code-input');
    const lineNumbers = document.getElementById('line-numbers');
    
    if (!codeInput || !lineNumbers) return;
    
    const lines = codeInput.value.split('\n').length;
    let numbers = '';
    for (let i = 1; i <= lines; i++) {
        numbers += i + '\n';
    }
    lineNumbers.textContent = numbers;
    
    // Sync scrolling
    codeInput.addEventListener('scroll', () => {
        lineNumbers.scrollTop = codeInput.scrollTop;
    });
}

// Create new file
function createNewFile() {
    const filename = prompt('Enter filename:', 'newfile.py');
    if (filename) {
        // Get current directory
        if (typeof eel !== 'undefined') {
            eel.get_current_directory()(function(currentDir) {
                const filePath = currentDir + '/' + filename;
                eel.write_file(filePath, '')(function(response) {
                    if (response && response.success) {
                        openFileInEditor(filename, '');
                        showNotification('File Created', `Created new file: ${filename}`, 'success');
                        refreshFileExplorer();
                    } else {
                        showNotification('File Error', response?.error || 'Failed to create file', 'error');
                    }
                });
            });
        } else {
            openFileInEditor(filename, '');
            showNotification('File Created', `Created new file: ${filename}`, 'success');
        }
    }
}

// Create new folder
function createNewFolder() {
    const foldername = prompt('Enter folder name:', 'newfolder');
    if (foldername) {
        if (typeof eel !== 'undefined') {
            eel.get_current_directory()(function(currentDir) {
                const folderPath = currentDir + '/' + foldername;
                eel.create_directory(folderPath)(function(response) {
                    if (response && response.success) {
                        showNotification('Folder Created', `Created new folder: ${foldername}`, 'success');
                        refreshFileExplorer();
                    } else {
                        showNotification('Folder Error', response?.error || 'Failed to create folder', 'error');
                    }
                });
            });
        } else {
            showNotification('Folder Created', `Created new folder: ${foldername}`, 'success');
            refreshFileExplorer();
        }
    }
}

// Save current file
function saveCurrentFile() {
    const editorTab = document.querySelector('.editor-file-tab.active');
    const filename = editorTab.dataset.file;
    const codeInput = document.getElementById('code-input');
    
    if (filename && codeInput) {
        if (typeof eel !== 'undefined') {
            eel.get_current_directory()(function(currentDir) {
                const filePath = currentDir + '/' + filename;
                eel.write_file(filePath, codeInput.value)(function(response) {
                    if (response && response.success) {
                        showNotification('File Saved', `Saved: ${filename}`, 'success');
                    } else {
                        showNotification('Save Error', response?.error || 'Failed to save file', 'error');
                    }
                });
            });
        } else {
            showNotification('File Saved', `Saved: ${filename}`, 'success');
            console.log('Saving file:', filename, codeInput.value);
        }
    }
}

// Run current file
function runCurrentFile() {
    const editorTab = document.querySelector('.editor-file-tab.active');
    const filename = editorTab.dataset.file;
    const codeInput = document.getElementById('code-input');
    
    if (filename && codeInput) {
        showNotification('Running', `Executing: ${filename}`, 'info');
        
        // Simulate execution output
        const output = `Running ${filename}...\n>>> ${codeInput.value.substring(0, 100)}${codeInput.value.length > 100 ? '...' : ''}\nExecution completed.`;
        appendToConsole(output, 'info');
        
        // Switch to output panel
        switchBottomPanel('output');
    }
}

// Format current file
function formatCurrentFile() {
    const codeInput = document.getElementById('code-input');
    if (codeInput) {
        // Simple formatting example
        const formatted = codeInput.value
            .replace(/\n{3,}/g, '\n\n')  // Remove multiple empty lines
            .replace(/^\s+$/gm, '');     // Remove whitespace-only lines
        
        codeInput.value = formatted;
        updateLineNumbers();
        showNotification('Formatted', 'File formatted successfully', 'success');
    }
}

// Close editor tab
function closeEditorTab() {
    document.getElementById('chat-container').style.display = 'block';
    document.getElementById('code-editor-container').style.display = 'none';
    showNotification('Editor Closed', 'Returned to chat view', 'info');
}

// Attach file to chat
function attachFile() {
    showNotification('Attach File', 'File attachment dialog would open here', 'info');
}

// Insert code block
function insertCodeBlock() {
    const messageInput = document.getElementById('message-input');
    if (messageInput) {
        messageInput.value += '\n```python\n# Your code here\n```\n';
        autoResize(messageInput);
        messageInput.focus();
    }
}

// Clear input
function clearInput() {
    const messageInput = document.getElementById('message-input');
    if (messageInput) {
        messageInput.value = '';
        autoResize(messageInput);
        messageInput.focus();
    }
}

/* ============================================
   Console Functions (Legacy - moved to index.html)
   ============================================ */

// Note: Console functions have been moved to index.html
// to support editor-integrated console panel

// Process console command (Legacy - moved to index.html)
function processConsoleCommand(command) {
    console.log('Legacy console command:', command);
    // This function is now handled in index.html
}

// Append text to console (Legacy - moved to index.html)
function appendToConsole(text, type = 'info') {
    console.log('Legacy console output:', text);
    // This function is now handled in index.html
}

// Clear console (Legacy - moved to index.html)
function clearConsole() {
    console.log('Legacy console clear');
    // This function is now handled in index.html
}

// Switch bottom panel (Legacy - panel moved to editor)
function switchBottomPanel(panelName) {
    console.log('Legacy panel switch:', panelName);
    // This function is now handled in index.html
}

// Toggle bottom panel (Legacy - panel moved to editor)
function toggleBottomPanel() {
    console.log('Legacy panel toggle');
    // This function is now handled in index.html
}

// Toggle right panel (Legacy - right panel removed)
function toggleRightPanel() {
    console.log('Legacy right panel toggle');
    // Right panel has been removed
}

/* ============================================
   Splitter/Drag Functions
   ============================================ */

// Initialize splitter handles for the new layout
function initializeSplitters() {
    // Main layout splitters
    const sessionsSplitter = document.getElementById('sessions-splitter');
    const mainSplitter = document.getElementById('main-splitter');
    const horizontalSplitter = document.getElementById('horizontal-splitter');
    
    if (sessionsSplitter) {
        makeResizable(sessionsSplitter, 'horizontal', 
            document.getElementById('sessions-sidebar'), 
            document.getElementById('editor-main-area'));
    }
    
    if (mainSplitter) {
        makeResizable(mainSplitter, 'horizontal', 
            document.getElementById('center-area'), 
            document.getElementById('chat-sidebar'));
    }
    
    if (horizontalSplitter) {
        makeResizable(horizontalSplitter, 'vertical', 
            document.getElementById('main-content'), 
            document.getElementById('bottom-panel'));
    }
}

// Make element resizable
function makeResizable(splitter, direction, panel1, panel2) {
    let isResizing = false;
    
    splitter.addEventListener('mousedown', (e) => {
        isResizing = true;
        document.body.classList.add('resizing');
        splitter.classList.add('dragging');
        
        const startX = e.clientX;
        const startY = e.clientY;
        const startWidth1 = panel1.offsetWidth;
        const startHeight1 = panel1.offsetHeight;
        const startWidth2 = panel2.offsetWidth;
        const startHeight2 = panel2.offsetHeight;
        
        function onMouseMove(e) {
            if (!isResizing) return;
            
            if (direction === 'horizontal') {
                const dx = e.clientX - startX;
                const newWidth1 = startWidth1 + dx;
                const newWidth2 = startWidth2 - dx;
                
                if (newWidth1 > 100 && newWidth2 > 100) {
                    panel1.style.width = `${newWidth1}px`;
                    panel2.style.width = `${newWidth2}px`;
                }
            } else {
                const dy = e.clientY - startY;
                const newHeight1 = startHeight1 + dy;
                const newHeight2 = startHeight2 - dy;
                
                if (newHeight1 > 50 && newHeight2 > 50) {
                    panel1.style.height = `${newHeight1}px`;
                    panel2.style.height = `${newHeight2}px`;
                }
            }
        }
        
        function onMouseUp() {
            isResizing = false;
            document.body.classList.remove('resizing');
            splitter.classList.remove('dragging');
            document.removeEventListener('mousemove', onMouseMove);
            document.removeEventListener('mouseup', onMouseUp);
        }
        
        document.addEventListener('mousemove', onMouseMove);
        document.addEventListener('mouseup', onMouseUp);
    });
}

/* ============================================
   Window Switching Functions
   ============================================ */

// Global state for window switching
let currentLeftView = 'traeai';

// Initialize window switching
function initializeWindowSwitching() {
    // Set up activity bar click handlers
    const activityItems = document.querySelectorAll('.activity-item[data-view]');
    activityItems.forEach(item => {
        item.addEventListener('click', function() {
            const view = this.dataset.view;
            switchLeftView(view);
        });
    });
    
    // Initialize with traeai view (first position)
    switchLeftView('traeai');
}

// Switch between traeai, explorer, and sessions views (traeai is first)
function switchLeftView(view) {
    if (view !== 'traeai' && view !== 'explorer' && view !== 'sessions') {
        return; // Only handle left panel views
    }
    
    currentLeftView = view;
    
    // Update activity bar active state
    document.querySelectorAll('.activity-item[data-view]').forEach(item => {
        item.classList.toggle('active', item.dataset.view === view);
    });
    
    // Get all view elements
    const traeaiView = document.getElementById('traeai-view');
    const explorerView = document.getElementById('explorer-view');
    const sessionsView = document.getElementById('sessions-view');
    
    // Hide all views first
    if (traeaiView) traeaiView.classList.add('hidden');
    if (explorerView) explorerView.classList.add('hidden');
    if (sessionsView) sessionsView.classList.add('hidden');
    
    // Show the selected view
    if (view === 'traeai' && traeaiView) {
        traeaiView.classList.remove('hidden');
        console.log('Switched to Trae AI view (default)');
    } else if (view === 'explorer' && explorerView) {
        explorerView.classList.remove('hidden');
        console.log('Switched to Explorer view');
    } else if (view === 'sessions' && sessionsView) {
        sessionsView.classList.remove('hidden');
        console.log('Switched to Sessions view');
    }
}

// Refresh file explorer
function refreshFileExplorer() {
    console.log('Refreshing file explorer...');
    // Call the existing file explorer refresh function
    if (typeof loadSampleFileTree === 'function') {
        loadSampleFileTree();
    }
}

// Create new file
function createNewFile() {
    console.log('Creating new file...');
    // Implementation would go here
    showNotification('New File', 'File creation dialog would open here', 'info');
}

// Create new folder
function createNewFolder() {
    console.log('Creating new folder...');
    // Implementation would go here
    showNotification('New Folder', 'Folder creation dialog would open here', 'info');
}

// Refresh sessions
function refreshSessions() {
    console.log('Refreshing sessions...');
    // Implementation would go here
    showNotification('Sessions', 'Refreshing session list...', 'info');
}

// Create new session
function createNewSession() {
    console.log('Creating new session...');
    // Implementation would go here
    showNotification('New Session', 'Creating new AI session...', 'info');
}

// Open file explorer
function openFileExplorer() {
    console.log('Opening file explorer...');
    // Switch to explorer view if not already
    if (currentLeftView !== 'explorer') {
        switchLeftView('explorer');
    }
    showNotification('File Explorer', 'File explorer opened', 'info');
}

// Trae AI functions
function newChat() {
    console.log('Starting new chat...');
    showNotification('New Chat', 'Starting new conversation...', 'info');
}

function clearChat() {
    console.log('Clearing chat...');
    const chatMessages = document.querySelector('.traeai-view .chat-messages');
    if (chatMessages) {
        chatMessages.innerHTML = `
            <div class="message assistant-message">
                <div class="message-header">
                    <div class="message-avatar assistant-avatar">
                        <i class="fas fa-robot"></i>
                    </div>
                    <div class="message-info">
                        <div class="message-role">Trae Assistant</div>
                        <div class="message-time">Now</div>
                    </div>
                </div>
                <div class="message-content">
                    Hello! I'm Trae, your AI coding assistant.
                </div>
            </div>
        `;
        showNotification('Chat Cleared', 'Conversation history cleared', 'success');
    }
}

// Send message in Trae AI
function sendTraeAIMessage() {
    const messageInput = document.querySelector('.traeai-view .message-input');
    if (!messageInput) return;
    
    const text = messageInput.value.trim();
    if (!text) return;
    
    // Add user message
    const chatMessages = document.querySelector('.traeai-view .chat-messages');
    if (!chatMessages) return;
    
    // Create user message
    const userMsg = document.createElement('div');
    userMsg.className = 'message user-message';
    userMsg.innerHTML = `
        <div class="message-header">
            <div class="message-avatar user-avatar">
                <i class="fas fa-user"></i>
            </div>
            <div class="message-info">
                <div class="message-role">You</div>
                <div class="message-time">Now</div>
            </div>
        </div>
        <div class="message-content">${escapeHtml(text)}</div>
    `;
    chatMessages.appendChild(userMsg);
    
    // Clear input
    messageInput.value = '';
    messageInput.style.height = 'auto';
    
    // Scroll to bottom
    chatMessages.scrollTop = chatMessages.scrollHeight;
    
    // Simulate AI response (in real implementation, this would call the backend)
    setTimeout(() => {
        const aiMsg = document.createElement('div');
        aiMsg.className = 'message assistant-message';
        aiMsg.innerHTML = `
            <div class="message-header">
                <div class="message-avatar assistant-avatar">
                    <i class="fas fa-robot"></i>
                </div>
                <div class="message-info">
                    <div class="message-role">Trae Assistant</div>
                    <div class="message-time">Now</div>
                </div>
            </div>
            <div class="message-content">
                I received your message: "${escapeHtml(text.substring(0, 50))}${text.length > 50 ? '...' : ''}"<br><br>
                In a real implementation, I would process your query and provide a helpful response.
            </div>
        `;
        chatMessages.appendChild(aiMsg);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }, 1000);
    
    console.log('Trae AI message sent:', text);
}

// Handle keyboard in Trae AI input
function handleTraeAIKeyPress(event) {
    if (event.ctrlKey && event.key === 'Enter') {
        event.preventDefault();
        sendTraeAIMessage();
    }
    
    // Auto-resize textarea
    if (event.target.classList.contains('message-input')) {
        setTimeout(() => {
            event.target.style.height = 'auto';
            event.target.style.height = Math.min(event.target.scrollHeight, 120) + 'px';
        }, 0);
    }
}

// Utility function to escape HTML
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Initialize when page loads
document.addEventListener('DOMContentLoaded', function() {
    // Initialize window switching
    initializeWindowSwitching();
    
    // Initialize other components
    if (typeof initializeActivityBar === 'function') {
        initializeActivityBar();
    }
    if (typeof initializeTabs === 'function') {
        initializeTabs();
    }
    if (typeof initializeKeyboardShortcuts === 'function') {
        initializeKeyboardShortcuts();
    }
    
    console.log('Window switching initialized');
});

/* ============================================
   Initialize Enhanced Features
   ============================================ */

// Initialize enhanced features when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    // Note: Splitters are now initialized in index.html
    // initializeSplitters(); // Disabled - splitters handled in index.html
    
    // Initialize console input (legacy - now handled in index.html)
    const consoleCommand = document.getElementById('console-command');
    if (consoleCommand) {
        consoleCommand.addEventListener('keydown', handleConsoleKeyPress);
    }
    
    // Initialize code editor
    const codeInput = document.getElementById('code-input');
    if (codeInput) {
        codeInput.addEventListener('input', updateLineNumbers);
        codeInput.addEventListener('scroll', () => {
            const lineNumbers = document.getElementById('line-numbers');
            if (lineNumbers) {
                lineNumbers.scrollTop = codeInput.scrollTop;
            }
        });
    }
    
    // Initialize window switching
    initializeWindowSwitching();
    
    console.log('Enhanced features initialized');
});
    
    // Initialize panel tabs
    document.querySelectorAll('.panel-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            const panelName = tab.dataset.panel;
            switchBottomPanel(panelName);
        });
    });
    
    // Add welcome message to console
    setTimeout(() => {
        appendToConsole('Trae AI Assistant Console initialized', 'success');
        appendToConsole('Type "help" for available commands', 'info');
    }, 1000);
});

// Real file operations using Python backend
function renameFile(oldPath, newName) {
    const newPath = oldPath.split('/').slice(0, -1).join('/') + '/' + newName;
    if (typeof eel !== 'undefined') {
        // For now, we'll just show a notification since rename requires more complex logic
        showNotification('Rename', `Would rename ${oldPath} to ${newPath}`, 'info');
        // In real implementation: copy file to new name, delete old file
    } else {
        showNotification('File Renamed', `Renamed ${oldPath} to ${newName}`, 'success');
        refreshFileExplorer();
    }
}

function deleteFile(filePath) {
    if (confirm(`Are you sure you want to delete "${filePath}"?`)) {
        if (typeof eel !== 'undefined') {
            eel.delete_path(filePath)(function(response) {
                if (response && response.success) {
                    showNotification('File Deleted', `Deleted: ${filePath}`, 'success');
                    refreshFileExplorer();
                } else {
                    showNotification('Delete Error', response?.error || 'Failed to delete file', 'error');
                }
            });
        } else {
            showNotification('File Deleted', `Deleted: ${filePath}`, 'success');
            refreshFileExplorer();
        }
    }
}

function copyFile(filename) {
    showNotification('File Copied', `Copied: ${filename}`, 'success');
}

function downloadFile(filename) {
    showNotification('Download', `Downloading: ${filename}`, 'info');
}

function createNewFileInFolder(folder) {
    const filename = prompt(`Create new file in "${folder}":`, 'newfile.py');
    if (filename) {
        showNotification('File Created', `Created: ${folder}/${filename}`, 'success');
        refreshFileExplorer();
    }
}

function createNewFolderInFolder(folder) {
    const foldername = prompt(`Create new folder in "${folder}":`, 'newfolder');
    if (foldername) {
        showNotification('Folder Created', `Created: ${folder}/${foldername}`, 'success');
        refreshFileExplorer();
    }
}