/**
 * panel.js – webview-side script for the jsonantt preview panel.
 *
 * This runs inside the VS Code WebviewPanel (sandboxed browser context).
 * It communicates with the extension host via acquireVsCodeApi().postMessage().
 */
(function () {
  "use strict";

  // VS Code API (available in WebviewPanel context).
  const vscode = acquireVsCodeApi();

  // ── Element references ──────────────────────────────────────────────────
  const chartTypeEl       = /** @type {HTMLSelectElement} */ (document.getElementById("chartType"));
  const renderDepthEl     = /** @type {HTMLInputElement}  */ (document.getElementById("renderDepth"));
  const refreshBtn        = /** @type {HTMLButtonElement} */ (document.getElementById("refreshBtn"));
  const exportBtn         = /** @type {HTMLButtonElement} */ (document.getElementById("exportBtn"));

  const burnRow           = document.getElementById("burnRow");
  const burnFieldEl       = /** @type {HTMLInputElement}  */ (document.getElementById("burnField"));
  const burnPeriodEl      = /** @type {HTMLSelectElement} */ (document.getElementById("burnPeriod"));
  const burnGroupEl       = /** @type {HTMLInputElement}  */ (document.getElementById("burnGroup"));
  const burnDisplayFactorEl = /** @type {HTMLInputElement} */ (document.getElementById("burnDisplayFactor"));

  const ganttRow          = document.getElementById("ganttRow");
  const dateLineEl        = /** @type {HTMLInputElement}  */ (document.getElementById("dateLine"));
  const dateLineColorEl   = /** @type {HTMLInputElement}  */ (document.getElementById("dateLineColor"));
  const pickCompareBtn    = /** @type {HTMLButtonElement} */ (document.getElementById("pickCompareBtn"));
  const compareLabel      = document.getElementById("compareLabel");

  const milestoneRow      = document.getElementById("milestoneRow");
  const msAll             = /** @type {HTMLInputElement}  */ (document.getElementById("msAll"));
  const msOnly            = /** @type {HTMLInputElement}  */ (document.getElementById("msOnly"));
  const msNone            = /** @type {HTMLInputElement}  */ (document.getElementById("msNone"));

  const statusBar         = document.getElementById("statusBar");
  const statusText        = document.getElementById("statusText");
  const svgContainer      = document.getElementById("svgContainer");
  const errorBox          = document.getElementById("errorBox");
  const errorText         = document.getElementById("errorText");
  const installBtn        = /** @type {HTMLButtonElement} */ (document.getElementById("installBtn"));

  // ── State ───────────────────────────────────────────────────────────────
  let currentChartType = "chart";

  // ── Toolbar visibility ──────────────────────────────────────────────────
  function updateRowVisibility() {
    const type = chartTypeEl.value;
    currentChartType = type;
    const isBurn  = type === "burn" || type === "burn-table";
    const isGantt = type === "chart";
    const isTable = type === "table";

    burnRow.hidden      = !isBurn;
    ganttRow.hidden     = !isGantt;
    milestoneRow.hidden = !isTable;
  }

  // ── Collect current options and post to extension host ─────────────────
  function sendOptions() {
    const type  = /** @type {"chart"|"table"|"burn"|"burn-table"} */ (chartTypeEl.value);
    const depth = parseInt(renderDepthEl.value, 10) || 0;

    const msValue = msAll.checked ? "all" : msOnly.checked ? "only" : "none";

    vscode.postMessage({
      type: "updateOptions",
      options: {
        chartType:         type,
        renderDepth:       depth,
        burnField:         burnFieldEl.value.trim()         || "cost",
        burnPeriod:        burnPeriodEl.value               || "month",
        burnGroup:         burnGroupEl.value.trim()         || "0",
        burnDisplayFactor: burnDisplayFactorEl.value.trim() || "1",
        dateLine:          dateLineEl.value.trim(),
        dateLineColor:     dateLineColorEl.value,
        milestonesOnly:    msValue === "only",
        noMilestones:      msValue === "none",
        // comparePath is managed by the extension host (file picker).
      },
    });
  }

  // ── Event listeners ─────────────────────────────────────────────────────
  chartTypeEl.addEventListener("change", () => {
    updateRowVisibility();
    sendOptions();
  });

  // Debounced re-render for text inputs.
  let debounceTimer = null;
  function debouncedSend() {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(sendOptions, 400);
  }

  renderDepthEl.addEventListener("input", debouncedSend);
  burnFieldEl.addEventListener("input", debouncedSend);
  burnPeriodEl.addEventListener("change", sendOptions);
  burnGroupEl.addEventListener("input", debouncedSend);
  burnDisplayFactorEl.addEventListener("input", debouncedSend);
  dateLineEl.addEventListener("input", debouncedSend);
  dateLineColorEl.addEventListener("input", debouncedSend);
  msAll.addEventListener("change",  sendOptions);
  msOnly.addEventListener("change", sendOptions);
  msNone.addEventListener("change", sendOptions);

  refreshBtn.addEventListener("click", () => {
    vscode.postMessage({ type: "refresh" });
  });

  exportBtn.addEventListener("click", () => {
    vscode.postMessage({ type: "export" });
  });

  pickCompareBtn.addEventListener("click", () => {
    vscode.postMessage({ type: "pickCompare" });
  });

  installBtn.addEventListener("click", () => {
    vscode.postMessage({ type: "installJsonantt" });
  });

  // ── Messages from the extension host ────────────────────────────────────
  window.addEventListener("message", (event) => {
    const message = event.data;
    switch (message.type) {
      case "rendering":
        showRendering();
        break;
      case "rendered":
        showSvg(message.svgData);
        break;
      case "error":
        showError(message.error);
        break;
      case "comparePathSet":
        compareLabel.textContent = message.filePath
          ? "📎 " + message.filePath.split(/[\\/]/).pop()
          : "";
        break;
    }
  });

  // ── UI state helpers ─────────────────────────────────────────────────────
  function showRendering() {
    statusBar.className = "rendering";
    statusText.textContent = "Rendering…";
    svgContainer.innerHTML = "";
    errorBox.hidden = true;
  }

  function showSvg(svgData) {
    errorBox.hidden = true;
    svgContainer.innerHTML = svgData;
    statusBar.className = "";
    statusText.textContent = "Rendered at " + new Date().toLocaleTimeString();
  }

  function showError(error) {
    svgContainer.innerHTML = "";
    errorText.textContent = error;
    errorBox.hidden = false;

    // Show the "Install jsonantt" button when the error looks like a missing command.
    const lc = error.toLowerCase();
    installBtn.hidden = !(
      lc.includes("not found") ||
      lc.includes("enoent") ||
      lc.includes("no module named") ||
      lc.includes("install jsonantt")
    );

    statusBar.className = "error";
    statusText.textContent = "Error";
  }

  // ── Initialise toolbar ──────────────────────────────────────────────────
  updateRowVisibility();
})();
