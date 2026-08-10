const projectInput = document.getElementById("projectFolder");
const folderText = document.getElementById("folderText");
const selectedFiles = document.getElementById("selectedFiles");
const analyzeButton = document.getElementById("analyzeButton");
const saveButton = document.getElementById("saveButton");
const loadingPanel = document.getElementById("loadingPanel");
const projectTypeBadge = document.getElementById("projectTypeBadge");
const downloadExcelButton = document.getElementById("downloadExcel");
const downloadJsonButton = document.getElementById("downloadJson");

const supportedExtensions = new Set([
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".java",
    ".cs",
    ".go",
    ".php",
    ".rb",
    ".cpp",
    ".c",
    ".h",
    ".hpp",
    ".html",
    ".css",
    ".sql",
    ".json",
    ".xml",
    ".yaml",
    ".yml",
]);

let selectedProjectFiles = [];
let selectedProjectName = "Selected Project";
let latestAnalysis = null;

function getSupportedProjectFiles(files) {
    return Array.from(files).filter((file) => {
        const name = (file.name || "").toLowerCase();
        const extension = name.includes(".") ? name.slice(name.lastIndexOf(".")) : "";
        return supportedExtensions.has(extension);
    });
}

function deriveProjectName(files) {
    const firstFile = files[0];
    if (!firstFile) {
        return "Selected Project";
    }

    const relativePath = firstFile.webkitRelativePath || firstFile.name || "";
    const pathParts = relativePath.split("/");
    return pathParts.length > 1 ? pathParts[0] : "Selected Project";
}

function getAuthHeaders() {
    const accessToken = sessionStorage.getItem("access_token");
    if (!accessToken) {
        return {};
    }
    return {
        Authorization: `Bearer ${accessToken}`,
    };
}

function updateSelectionUi() {
    if (selectedProjectFiles.length === 0) {
        folderText.textContent = "Browse project folder";
        selectedFiles.textContent = "";
        projectTypeBadge.textContent = "Awaiting selection";
        analyzeButton.disabled = true;
        if (saveButton) {
            saveButton.disabled = true;
        }
        return;
    }

    folderText.textContent = selectedProjectName;
    selectedFiles.textContent = `${selectedProjectFiles.length} supported source files selected`;
    projectTypeBadge.textContent = "Ready to process";
    analyzeButton.disabled = false;
    if (saveButton) {
        saveButton.disabled = selectedProjectFiles.length === 0;
    }
}

if (projectInput) {
    projectInput.addEventListener("change", function (event) {
        const files = event.target.files || [];
        selectedProjectFiles = getSupportedProjectFiles(files);
        selectedProjectName = deriveProjectName(files);
        updateSelectionUi();
    });
}

async function submitAnalysis(endpoint) {
    if (selectedProjectFiles.length === 0) {
        alert("Please select a folder that contains source files first.");
        return;
    }

    const formData = new FormData();
    formData.append("project_name", selectedProjectName);

    selectedProjectFiles.forEach((file) => {
        const relativePath = file.webkitRelativePath || file.name;
        formData.append("files", file, relativePath);
    });

    analyzeButton.disabled = true;
    if (saveButton) {
        saveButton.disabled = true;
    }
    loadingPanel.classList.remove("hidden");
    loadingPanel.innerHTML = `
            <div class="spinner"></div>
            <div>
                <strong>Processing ${selectedProjectFiles.length} source files...</strong>
                <p>Reading the project, detecting controllers, and generating test cases.</p>
            </div>`;

    try {
        const response = await fetch(endpoint, {
            method: "POST",
            headers: getAuthHeaders(),
            body: formData,
        });

        const text = await response.text();
        let data = null;
        try {
            data = text ? JSON.parse(text) : null;
        } catch (e) {
            data = null;
        }

        if (!response.ok) {
            const message = data?.detail || text || `Server responded with ${response.status}`;
            throw new Error(message);
        }

        if (!data || !data.analysis_id) {
            throw new Error("The server did not return analysis data.");
        }

        latestAnalysis = data;
        displayAnalysis(data);
        await loadHistory();
    } catch (error) {
        console.error("Project analysis failed:", error);
        const message = error.message || "Code analysis failed.";
        alert(message);
    } finally {
        analyzeButton.disabled = false;
        if (saveButton) {
            saveButton.disabled = selectedProjectFiles.length === 0;
        }
        updateSelectionUi();
        loadingPanel.classList.add("hidden");
        loadingPanel.innerHTML = `
                <div class="spinner"></div>
                <div>
                    <strong>Processing project...</strong>
                    <p>Scanning source files, identifying controllers, and generating test cases.</p>
                </div>`;
    }
}

if (analyzeButton) {
    analyzeButton.addEventListener("click", async function () {
        await submitAnalysis("/api/analysis/analyze");
    });
}

if (saveButton) {
    saveButton.addEventListener("click", async function () {
        await submitAnalysis("/api/analysis/save");
    });
}

function displayAnalysis(analysis) {
    document.getElementById("totalFiles").textContent = formatNumber(analysis.total_files || 0);
    document.getElementById("totalLines").textContent = formatNumber(analysis.total_lines || 0);
    document.getElementById("functionCount").textContent = formatNumber(analysis.function_count || 0);
    document.getElementById("classCount").textContent = formatNumber(analysis.class_count || 0);

    displaySummary(analysis);
    displayLanguages(analysis.languages || {});
    displayFiles(analysis.files || []);
    displayGeneratedTests(analysis);
    displayStatistics(analysis);
    updateReportActions(analysis);
}

function displaySummary(analysis) {
    const element = document.getElementById("summaryMessage");
    const projectType = analysis.project_type || "generic";
    const generatedCount = Array.isArray(analysis.generated_test_cases) ? analysis.generated_test_cases.length : 0;
    const generatedByRole = analysis.summary?.generated_by_role || analysis.generated_by_role;
    const generatedByUsername = analysis.summary?.generated_by_username || analysis.generated_by_username;

    element.innerHTML = `
        <p><strong>${escapeHtml(analysis.project_name || "Imported Project")}</strong> was processed as a <strong>${escapeHtml(projectType)}</strong> project.</p>
        <p>The project contains <strong>${formatNumber(analysis.total_files || 0)}</strong> supported source files.</p>
        <p>The analyzer identified <strong>${formatNumber(analysis.function_count || 0)}</strong> functions/methods and <strong>${formatNumber(analysis.class_count || 0)}</strong> classes.</p>
        <p>Total source size: <strong>${formatNumber(analysis.total_lines || 0)}</strong> lines. Generated <strong>${formatNumber(generatedCount)}</strong> test cases.</p>
        ${generatedByRole ? `<p>Saved with user level: <strong>${escapeHtml(generatedByRole)}</strong>${generatedByUsername ? ` by <strong>${escapeHtml(generatedByUsername)}</strong>` : ""}.</p>` : ""}
    `;
}

function displayLanguages(languages) {
    const chart = document.getElementById("languageChart");
    chart.innerHTML = "";

    const entries = Object.entries(languages || {});
    if (entries.length === 0) {
        chart.innerHTML = '<div class="empty-state">No supported languages found.</div>';
        return;
    }

    const maximum = Math.max(...entries.map(([, count]) => count));
    entries.sort((a, b) => b[1] - a[1]).forEach(([language, count]) => {
        const percentage = maximum > 0 ? (count / maximum) * 100 : 0;
        const row = document.createElement("div");
        row.className = "language-row";
        row.innerHTML = `
            <div class="language-header">
                <span>${escapeHtml(language)}</span>
                <strong>${count}</strong>
            </div>
            <div class="language-track">
                <div class="language-bar" style="width: ${percentage}%"></div>
            </div>`;
        chart.appendChild(row);
    });
}

function displayFiles(files) {
    const body = document.getElementById("fileTableBody");
    body.innerHTML = "";

    if (!Array.isArray(files) || files.length === 0) {
        body.innerHTML = '<tr><td colspan="5" class="empty-state">No supported source files found.</td></tr>';
        return;
    }

    files.forEach((file) => {
        const row = document.createElement("tr");
        row.innerHTML = `
            <td>${escapeHtml(file.path || file.name || "")}</td>
            <td>${escapeHtml(file.language || "Unknown")}</td>
            <td>${formatNumber(file.lines || 0)}</td>
            <td>${formatNumber(file.functions || 0)}</td>
            <td>${formatNumber(file.classes || 0)}</td>`;
        body.appendChild(row);
    });
}

function displayGeneratedTests(analysis) {
    const container = document.getElementById("generatedTests");
    const files = Array.isArray(analysis.files) ? analysis.files : [];

    if (files.length === 0) {
        container.innerHTML = '<div class="empty-state">No generated tests yet.</div>';
        return;
    }

    container.innerHTML = "";
    files.forEach((file) => {
        const card = document.createElement("div");
        card.className = "generated-card";
        const testCases = Array.isArray(file.test_cases) ? file.test_cases : [];
        card.innerHTML = `
            <div class="history-meta">
                <strong>${escapeHtml(file.path || file.name || "Unknown file")}</strong>
                <span>${escapeHtml(file.language || "Unknown")}</span>
            </div>
            <div>
                ${testCases.length ? testCases.map((testCase) => `<span class="file-pill">${escapeHtml(testCase)}</span>`).join("") : '<span class="file-pill">No test cases generated</span>'}
            </div>`;
        container.appendChild(card);
    });
}

function displayStatistics(analysis) {
    const element = document.getElementById("statisticsContent");
    element.innerHTML = `
        <div class="cards">
            <div class="metric-card">
                <span class="metric-label">Languages</span>
                <strong class="metric-value">${analysis.language_count || 0}</strong>
            </div>
            <div class="metric-card">
                <span class="metric-label">Functions</span>
                <strong class="metric-value">${analysis.function_count || 0}</strong>
            </div>
            <div class="metric-card">
                <span class="metric-label">Classes</span>
                <strong class="metric-value">${analysis.class_count || 0}</strong>
            </div>
            <div class="metric-card">
                <span class="metric-label">Lines / File</span>
                <strong class="metric-value">${analysis.total_files ? Math.round((analysis.total_lines || 0) / analysis.total_files) : 0}</strong>
            </div>
        </div>`;
}

function updateReportActions(analysis) {
    const reportSummary = document.getElementById("reportSummary");
    if (!analysis || !analysis.analysis_id) {
        reportSummary.innerHTML = '<div class="empty-state">Run a new analysis to enable report downloads.</div>';
        return;
    }

    reportSummary.innerHTML = `
        <p><strong>${escapeHtml(analysis.project_name || "Imported Project")}</strong> is ready for download.</p>
        <p>${formatNumber(analysis.total_files || 0)} files processed and ${formatNumber((analysis.generated_test_cases || []).length)} test cases generated.</p>`;
    latestAnalysis = analysis;
}

async function loadHistory() {
    try {
        const response = await fetch("/api/analysis/history");
        const data = await response.json();
        displayHistory(data.history || []);
    } catch (error) {
        console.error("Unable to load history:", error);
    }
}

function displayHistory(historyItems) {
    const container = document.getElementById("historyContent");
    if (!historyItems.length) {
        container.innerHTML = '<div class="empty-state">No history yet. Process a folder to start building your audit trail.</div>';
        return;
    }

    container.innerHTML = "";
    historyItems.forEach((item) => {
        const card = document.createElement("div");
        card.className = "history-card";
        const processedFiles = Array.isArray(item.processed_files) ? item.processed_files : [];
        const testCases = Array.isArray(item.generated_test_cases) ? item.generated_test_cases : [];
        card.innerHTML = `
            <div class="history-meta">
                <strong>${escapeHtml(item.project_name || "Imported Project")}</strong>
                <span>${escapeHtml(item.project_type || "generic")}</span>
                <span>${escapeHtml(new Date(item.created_at).toLocaleString())}</span>
            </div>
            <div class="history-meta">
                <span>${formatNumber(item.total_files || 0)} files</span>
                <span>${formatNumber(testCases.length)} tests</span>
            </div>
            <div>${processedFiles.slice(0, 4).map((file) => `<span class="file-pill">${escapeHtml(file.path || file.name || "")}</span>`).join("")}</div>
            <div class="download-row">
                <button class="secondary-button" data-analysis-id="${item.analysis_id}" data-format="excel">Excel</button>
                <button class="secondary-button" data-analysis-id="${item.analysis_id}" data-format="json">JSON</button>
            </div>`;
        container.appendChild(card);
    });

    container.querySelectorAll("button[data-analysis-id]").forEach((button) => {
        button.addEventListener("click", function () {
            const analysisId = this.getAttribute("data-analysis-id");
            const format = this.getAttribute("data-format") || "json";
            window.open(`/api/analysis/download/${analysisId}?format=${format}`);
        });
    });
}

function formatNumber(value) {
    return Number(value || 0).toLocaleString();
}

function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

document.querySelectorAll(".nav-item").forEach((button) => {
    button.addEventListener("click", () => {
        document.querySelectorAll(".nav-item").forEach((item) => item.classList.remove("active"));
        document.querySelectorAll(".tab-content").forEach((tab) => tab.classList.remove("active"));
        button.classList.add("active");
        const tab = document.getElementById(button.dataset.tab);
        if (tab) {
            tab.classList.add("active");
        }
    });
});

const logoutButton = document.getElementById("logoutButton");
if (logoutButton) {
    logoutButton.addEventListener("click", () => {
        sessionStorage.removeItem("access_token");
        sessionStorage.removeItem("token_type");
        window.location.href = "/";
    });
}

if (downloadExcelButton) {
    downloadExcelButton.addEventListener("click", () => {
        if (!latestAnalysis || !latestAnalysis.analysis_id) {
            alert("Run an analysis before downloading reports.");
            return;
        }
        window.open(`/api/analysis/download/${latestAnalysis.analysis_id}?format=excel`);
    });
}

if (downloadJsonButton) {
    downloadJsonButton.addEventListener("click", () => {
        if (!latestAnalysis || !latestAnalysis.analysis_id) {
            alert("Run an analysis before downloading reports.");
            return;
        }
        window.open(`/api/analysis/download/${latestAnalysis.analysis_id}?format=json`);
    });
}

loadHistory();

