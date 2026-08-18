// Unified Telecom Analyzer — Vue 3 App Logic
import { createApp, ref, computed, watch, nextTick, onMounted } from 'https://unpkg.com/vue@3/dist/vue.esm-browser.js';

const app = createApp({
  setup() {
    // ── Reactive State ───────────────────────────────────────────────
    const activeTab = ref('dashboard');
    const health = ref({ status: 'checking', llm: { running: false, model: 'phi3:mini' } });
    const isDragging = ref(false);
    const theme = ref('light');

    // Session Multi-Job Store
    const sessionJobs = ref([]);
    const correlationData = ref(null);
    const isCorrelating = ref(false);

    // Multi-step Progress & File Size Tracking
    const progressState = ref({
      active: false,
      step: 1, // 1: Uploading, 2: Processing, 3: Complete
      fileName: '',
      percent: 0,
      loadedMB: '0.0',
      totalMB: '0.0',
      statusText: 'Preparing upload...'
    });
    
    const analysisResult = ref(null);
    const searchQuery = ref('');
    const protocolFilter = ref('ALL');
    const selectedAnomaly = ref(null);
    const feedbackStatus = ref('');

    // KPI Explorer — filter by gNB / cell (PCI) and chart any number of
    // metrics at once (each metric gets its own small chart, since metrics
    // rarely share a comparable scale/unit).
    const kpiFilterOptions = ref({ gnbs: [], cells: [], metrics: [] });
    const selectedGnbs = ref([]);
    const selectedCells = ref([]);
    const selectedMetrics = ref([]);
    const kpiSeriesData = ref({});
    const kpiSeriesLoading = ref(false);

    // Chart.js instances storage
    let chartInstances = {};

    // ── Theme Toggle ────────────────────────────────────────────────
    const toggleTheme = () => {
      theme.value = theme.value === 'light' ? 'dark' : 'light';
      if (theme.value === 'dark') {
        document.body.classList.add('dark-theme');
      } else {
        document.body.classList.remove('dark-theme');
      }
      nextTick(renderCharts);
    };

    // ── Chart Renderer ──────────────────────────────────────────────
    const renderCharts = () => {
      if (!analysisResult.value || activeTab.value !== 'dashboard') return;

      const isDark = theme.value === 'dark';
      const textColor = isDark ? '#f1f5f9' : '#0f172a';
      const gridColor = isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.06)';

      // 1. Severity Doughnut Chart
      const ctxSev = document.getElementById('severityChart');
      if (ctxSev) {
        if (chartInstances.severityChart) chartInstances.severityChart.destroy();

        const anomalies = analysisResult.value.anomalies || [];
        const crit = anomalies.filter(a => a.severity === 'Critical').length;
        const high = anomalies.filter(a => a.severity === 'High').length;
        const med  = anomalies.filter(a => a.severity === 'Medium').length;
        const low  = anomalies.filter(a => a.severity === 'Low').length;

        chartInstances.severityChart = new Chart(ctxSev, {
          type: 'doughnut',
          data: {
            labels: ['Critical', 'High', 'Medium', 'Low / Clean'],
            datasets: [{
              data: [crit, high, med, low],
              backgroundColor: ['#dc2626', '#d97706', '#eab308', '#059669'],
              borderWidth: 2,
              borderColor: isDark ? '#0e131f' : '#ffffff',
            }]
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              legend: { position: 'right', labels: { color: textColor, font: { family: 'Inter', size: 12 } } }
            }
          }
        });
      }

      // 2. Protocol Signaling Distribution Bar Chart
      const ctxProt = document.getElementById('protocolChart');
      if (ctxProt) {
        if (chartInstances.protocolChart) chartInstances.protocolChart.destroy();

        const events = analysisResult.value.parsed?.message_log || [];
        const layers = ['NAS', 'NGAP', 'RRC', 'F1AP', 'E1AP', 'XnAP'];
        const counts = layers.map(l => events.filter(e => e.layer === l).length);

        chartInstances.protocolChart = new Chart(ctxProt, {
          type: 'bar',
          data: {
            labels: layers,
            datasets: [{
              label: 'Procedure Messages',
              data: counts,
              backgroundColor: '#0284c7',
              borderRadius: 6,
            }]
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              legend: { display: false }
            },
            scales: {
              x: { ticks: { color: textColor }, grid: { display: false } },
              y: { ticks: { color: textColor }, grid: { color: gridColor }, beginAtZero: true }
            }
          }
        });
      }

      // 3. Anomaly Type Breakdown (top 10, grouped by category/label/layer/type)
      const ctxAnomType = document.getElementById('anomalyTypeChart');
      if (ctxAnomType) {
        if (chartInstances.anomalyTypeChart) chartInstances.anomalyTypeChart.destroy();

        const anomalies = analysisResult.value.anomalies || [];
        const counts = {};
        anomalies.forEach(a => {
          const key = a.category || a.label || a.layer || a.type || 'Other';
          counts[key] = (counts[key] || 0) + 1;
        });
        const sorted = Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 10);

        chartInstances.anomalyTypeChart = new Chart(ctxAnomType, {
          type: 'bar',
          data: {
            labels: sorted.map(([k]) => k),
            datasets: [{
              label: 'Anomaly Count',
              data: sorted.map(([, v]) => v),
              backgroundColor: '#7c3aed',
              borderRadius: 6,
            }]
          },
          options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              legend: { display: false }
            },
            scales: {
              x: { ticks: { color: textColor }, grid: { color: gridColor }, beginAtZero: true },
              y: { ticks: { color: textColor }, grid: { display: false } }
            }
          }
        });
      }

      // 4. KPI Performance Trend Line Chart
      const ctxKpi = document.getElementById('kpiTrendChart');
      if (ctxKpi) {
        if (chartInstances.kpiTrendChart) chartInstances.kpiTrendChart.destroy();

        const trend = analysisResult.value.parsed?.kpi_trend || [];
        const timestamps = trend.map(p => {
          const t = p.timestamp || '';
          const spaceIdx = t.indexOf(' ');
          return spaceIdx > -1 ? t.slice(spaceIdx + 1, spaceIdx + 6) : t;
        });
        const throughput = trend.map(p => p.dl_throughput_mbps);
        const prbUtil    = trend.map(p => p.prb_utilization_pct);

        chartInstances.kpiTrendChart = new Chart(ctxKpi, {
          type: 'line',
          data: {
            labels: timestamps,
            datasets: [
              {
                label: 'DL Throughput (Mbps)',
                data: throughput,
                borderColor: '#0284c7',
                backgroundColor: 'rgba(2, 132, 199, 0.1)',
                tension: 0.3,
                fill: true
              },
              {
                label: 'PRB Utilization (%)',
                data: prbUtil,
                borderColor: '#dc2626',
                borderDash: [5, 5],
                tension: 0.3,
                fill: false
              }
            ]
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              legend: { position: 'top', labels: { color: textColor, font: { family: 'Inter', size: 12 } } }
            },
            scales: {
              x: { ticks: { color: textColor }, grid: { color: gridColor } },
              y: { ticks: { color: textColor }, grid: { color: gridColor }, beginAtZero: true }
            }
          }
        });
      }
    };

    watch([analysisResult, activeTab], () => {
      nextTick(renderCharts);
    });

    // ── KPI Explorer — gNB/cell filters + one small chart per selected metric ──
    const renderKpiExplorerCharts = () => {
      const isDark = theme.value === 'dark';
      const textColor = isDark ? '#f1f5f9' : '#0f172a';
      const gridColor = isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.06)';
      const palette = ['#0284c7', '#dc2626', '#059669', '#7c3aed', '#d97706', '#db2777'];

      selectedMetrics.value.forEach((metric, idx) => {
        const ctx = document.getElementById('kpiChart_' + idx);
        const series = kpiSeriesData.value[metric];
        if (!ctx || !series) return;
        const key = 'kpiExplorer_' + idx;
        if (chartInstances[key]) chartInstances[key].destroy();

        const cells = Object.keys(series);
        const allTimestamps = [...new Set(cells.flatMap(c => series[c].map(p => p.timestamp)))].sort();
        const labels = allTimestamps.map(t => {
          const spaceIdx = t.indexOf(' ');
          return spaceIdx > -1 ? t.slice(spaceIdx + 1, spaceIdx + 6) : t;
        });
        const datasets = cells.map((cell, i) => {
          const byTs = Object.fromEntries(series[cell].map(p => [p.timestamp, p.value]));
          return {
            label: cell,
            data: allTimestamps.map(t => byTs[t] ?? null),
            borderColor: palette[i % palette.length],
            tension: 0.3,
            fill: false,
            spanGaps: true,
          };
        });

        chartInstances[key] = new Chart(ctx, {
          type: 'line',
          data: { labels, datasets },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              legend: { position: 'top', labels: { color: textColor, font: { size: 11 } } }
            },
            scales: {
              x: { ticks: { color: textColor, maxRotation: 0, autoSkip: true, maxTicksLimit: 8 }, grid: { color: gridColor } },
              y: { ticks: { color: textColor }, grid: { color: gridColor } }
            }
          }
        });
      });
    };

    const loadKpiSeries = async () => {
      const jobId = analysisResult.value?.job_id;
      if (!jobId || selectedMetrics.value.length === 0) return;
      kpiSeriesLoading.value = true;
      try {
        const params = new URLSearchParams({ metrics: selectedMetrics.value.join(',') });
        if (selectedGnbs.value.length > 0 && selectedGnbs.value.length < kpiFilterOptions.value.gnbs.length) {
          params.set('gnbs', selectedGnbs.value.join(','));
        }
        if (selectedCells.value.length > 0 && selectedCells.value.length < kpiFilterOptions.value.cells.length) {
          params.set('cells', selectedCells.value.join(','));
        }
        const res = await fetch(`/analyze/${jobId}/kpi-series?${params.toString()}`);
        if (res.ok) {
          const data = await res.json();
          kpiSeriesData.value = data.series || {};
          nextTick(renderKpiExplorerCharts);
        }
      } catch (err) {
        console.error('Failed to load KPI series:', err);
      } finally {
        kpiSeriesLoading.value = false;
      }
    };

    const loadKpiFilters = async () => {
      const jobId = analysisResult.value?.job_id;
      kpiFilterOptions.value = { gnbs: [], cells: [], metrics: [] };
      selectedGnbs.value = [];
      selectedCells.value = [];
      selectedMetrics.value = [];
      if (!jobId) return;
      try {
        const res = await fetch(`/analyze/${jobId}/kpi-filters`);
        if (res.ok) {
          const data = await res.json();
          kpiFilterOptions.value = data;
          selectedGnbs.value = [...(data.gnbs || [])];
          selectedCells.value = [...(data.cells || [])];
          if (data.metrics?.length > 0) {
            selectedMetrics.value = [data.metrics[0]];
            await loadKpiSeries();
          }
        }
      } catch (err) {
        console.error('Failed to load KPI filters:', err);
      }
    };

    const selectAllGnbs    = () => { selectedGnbs.value = [...kpiFilterOptions.value.gnbs]; loadKpiSeries(); };
    const selectAllCells   = () => { selectedCells.value = [...kpiFilterOptions.value.cells]; loadKpiSeries(); };
    const selectAllMetrics = () => { selectedMetrics.value = [...kpiFilterOptions.value.metrics]; loadKpiSeries(); };

    watch(() => analysisResult.value?.job_id, (jobId) => {
      if (jobId) loadKpiFilters();
    });

    // ── Health Polling ──────────────────────────────────────────────
    const checkHealth = async () => {
      try {
        const res = await fetch('/health');
        if (res.ok) {
          health.value = await res.json();
        } else {
          health.value.status = 'error';
        }
      } catch (err) {
        health.value.status = 'error';
      }
    };

    onMounted(() => {
      checkHealth();
      setInterval(checkHealth, 10000);
    });

    // ── Single File Upload Function (Promise Wrapped) ───────────────
    const uploadSingleFile = (file, fileIdx = 1, totalFiles = 1) => {
      return new Promise((resolve, reject) => {
        const totalSizeMB = (file.size / (1024 * 1024)).toFixed(1);
        
        progressState.value = {
          active: true,
          step: 1,
          fileName: file.name,
          percent: 0,
          loadedMB: '0.0',
          totalMB: totalSizeMB,
          statusText: `[File ${fileIdx}/${totalFiles}] Step 1: Uploading ${file.name} (0.0 MB / ${totalSizeMB} MB)`
        };

        const formData = new FormData();
        formData.append('file', file);

        const ext = file.name.split('.').pop().toLowerCase();
        let endpoint = '/analyze/pcap';
        
        if (['xlsx', 'xls', 'csv'].includes(ext)) {
          if (file.name.toLowerCase().includes('stats')) {
            endpoint = '/analyze/stats?run_prediction=true';
          } else {
            endpoint = '/analyze/kpi?run_prediction=true';
          }
        }

        const xhr = new XMLHttpRequest();
        xhr.open('POST', endpoint, true);

        // Track Upload Progress (Step 1)
        xhr.upload.onprogress = (event) => {
          if (event.lengthComputable) {
            const percentComplete = Math.round((event.loaded / event.total) * 100);
            const loadedMB = (event.loaded / (1024 * 1024)).toFixed(1);
            progressState.value.percent = percentComplete;
            progressState.value.loadedMB = loadedMB;
            progressState.value.statusText = `[File ${fileIdx}/${totalFiles}] Uploading ${file.name}: ${loadedMB} MB / ${totalSizeMB} MB (${percentComplete}%)`;
          }
        };

        // Upload Completed -> Step 2
        xhr.upload.onload = () => {
          progressState.value.step = 2;
          progressState.value.percent = 100;
          progressState.value.statusText = `[File ${fileIdx}/${totalFiles}] Step 2: Processing 5G Telemetry & 18-Detector Ensemble for ${file.name}...`;
        };

        xhr.onload = () => {
          if (xhr.status === 200) {
            try {
              const data = JSON.parse(xhr.responseText);
              analysisResult.value = data;
              
              if (data.job_id) {
                const existingIdx = sessionJobs.value.findIndex(j => j.id === data.job_id);
                if (existingIdx === -1) {
                  sessionJobs.value.push({
                    id: data.job_id,
                    fileName: file.name,
                    pipeline: data.pipeline || 'telemetry',
                    anomalyCount: (data.anomalies || []).length
                  });
                }
              }

              if (data.anomalies && data.anomalies.length > 0) {
                selectedAnomaly.value = data.anomalies[0];
              }
              resolve(data);
            } catch (e) {
              reject(e);
            }
          } else {
            reject(new Error(`Server status ${xhr.status}`));
          }
        };

        xhr.onerror = (err) => reject(err);
        xhr.send(formData);
      });
    };

    // ── Batch Multi-File Upload Controller ──────────────────────────
    const processBatchUpload = async (files) => {
      if (!files || files.length === 0) return;

      const totalFiles = files.length;
      for (let i = 0; i < totalFiles; i++) {
        try {
          await uploadSingleFile(files[i], i + 1, totalFiles);
        } catch (err) {
          console.error(`Error uploading ${files[i].name}:`, err);
        }
      }

      progressState.value.active = false;
      nextTick(renderCharts);

      // Auto-trigger cross-source correlation if multiple files uploaded
      if (sessionJobs.value.length >= 2) {
        await runCorrelation();
      }
    };

    // ── Run Cross-Source Correlation Agent ─────────────────────────
    const runCorrelation = async () => {
      if (sessionJobs.value.length === 0) return;
      isCorrelating.value = true;
      try {
        const jobIds = sessionJobs.value.map(j => j.id);
        const res = await fetch('/agent/root-cause', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ job_ids: jobIds, min_sources: 1 })
        });
        if (res.ok) {
          correlationData.value = await res.json();
          activeTab.value = 'correlation';
        } else {
          alert('Correlation engine failed to process jobs.');
        }
      } catch (err) {
        console.error(err);
        alert('Failed to connect to root cause correlation agent.');
      } finally {
        isCorrelating.value = false;
      }
    };

    // ── Remove an uploaded job from the session ────────────────────
    const removeJob = (jobId) => {
      sessionJobs.value = sessionJobs.value.filter(j => j.id !== jobId);
      if (analysisResult.value?.job_id === jobId) {
        analysisResult.value = null;
        selectedAnomaly.value = null;
      }
      if (sessionJobs.value.length < 2) {
        correlationData.value = null;
      }
    };

    // ── Export current job's report (opens the browser's native download) ──
    const exportReport = (format) => {
      const jobId = analysisResult.value?.job_id;
      if (!jobId) return;
      window.open(`/analyze/${jobId}/export?format=${format}`, '_blank');
    };

    const handleFileSelect = (event) => {
      const files = Array.from(event.target.files);
      processBatchUpload(files);
    };

    const handleDrop = (event) => {
      isDragging.value = false;
      const files = Array.from(event.dataTransfer.files);
      processBatchUpload(files);
    };

    // ── Engineer Feedback ────────────────────────────────────────────
    const sendFeedback = async (verdict) => {
      if (!selectedAnomaly.value) return;
      try {
        const payload = {
          event_id: selectedAnomaly.value.id || 'anom-0',
          source: analysisResult.value?.pipeline || 'pcap',
          anomaly_type: selectedAnomaly.value.type,
          severity: selectedAnomaly.value.severity,
          detector: selectedAnomaly.value.detector || 'Ensemble',
          cell_id: selectedAnomaly.value.cell_id || 'gNB-1',
          evidence: selectedAnomaly.value.evidence || '',
          verdict: verdict,
        };
        
        feedbackStatus.value = `Saved feedback: ${verdict.toUpperCase()}`;
        setTimeout(() => { feedbackStatus.value = ''; }, 3000);
      } catch (e) {
        console.error(e);
      }
    };

    // ── Computed Properties ──────────────────────────────────────────
    // parsed.procedures is an aggregate dict (per-procedure attempt/success
    // counts), not per-event rows — the actual timestamped event stream for
    // this table lives in parsed.message_log (one row per request/response/
    // failure/timeout, each with its own real capture timestamp).
    const ROLE_STATUS = { response: 'Success', failure: 'Failed', timeout: 'Timeout', request: 'Requested' };

    const filteredProcedures = computed(() => {
      const log = analysisResult.value?.parsed?.message_log;
      if (!log) return [];
      let list = log.map(evt => ({
        timestamp: evt.timestamp,
        layer: evt.layer,
        ue_id: evt.ue_id,
        name: evt.procedure,
        status: ROLE_STATUS[evt.role] || evt.role,
        cause: evt.ies && evt.ies.Cause,
      }));
      if (protocolFilter.value !== 'ALL') {
        list = list.filter(p => p.layer === protocolFilter.value);
      }
      if (searchQuery.value) {
        const q = searchQuery.value.toLowerCase();
        list = list.filter(p =>
          (p.name && p.name.toLowerCase().includes(q)) ||
          (p.ue_id && p.ue_id.toLowerCase().includes(q)) ||
          (p.cause && p.cause.toLowerCase().includes(q))
        );
      }
      return list;
    });

    // Raw timestamps are epoch seconds with microsecond (or finer) precision
    // from the packet capture — JS Date only resolves to milliseconds, so the
    // sub-millisecond digits are pulled from the raw float string directly.
    const formatFullTimestamp = (epochSeconds) => {
      if (epochSeconds === undefined || epochSeconds === null) return '—';
      const date = new Date(epochSeconds * 1000);
      const pad = (n) => String(n).padStart(2, '0');
      const datePart = `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
      const timePart = `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
      const fracStr = (epochSeconds.toString().split('.')[1] || '0').padEnd(6, '0');
      return `${datePart} ${timePart}.${fracStr}`;
    };

    const filteredAnomalies = computed(() => {
      if (!analysisResult.value?.anomalies) return [];
      let list = analysisResult.value.anomalies;
      if (searchQuery.value) {
        const q = searchQuery.value.toLowerCase();
        list = list.filter(a => 
          (a.type && a.type.toLowerCase().includes(q)) ||
          (a.evidence && a.evidence.toLowerCase().includes(q))
        );
      }
      return list;
    });

    const criticalCount = computed(() => {
      return (analysisResult.value?.anomalies || []).filter(a => a.severity === 'Critical').length;
    });

    const highCount = computed(() => {
      return (analysisResult.value?.anomalies || []).filter(a => a.severity === 'High').length;
    });

    const predictedList = computed(() => {
      if (!analysisResult.value?.predictions) return [];
      const preds = analysisResult.value.predictions;
      return Object.values(preds).flat();
    });

    // Backend only sends a relative lead_time_h (e.g. "4 hours from now"),
    // not an absolute timestamp — derive a wall-clock estimate for display.
    const predictedClockTime = (leadTimeH) => {
      const d = new Date(Date.now() + (leadTimeH || 4) * 3600 * 1000);
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    };

    return {
      activeTab,
      health,
      theme,
      toggleTheme,
      sessionJobs,
      correlationData,
      isCorrelating,
      runCorrelation,
      progressState,
      isDragging,
      analysisResult,
      searchQuery,
      protocolFilter,
      selectedAnomaly,
      feedbackStatus,
      handleFileSelect,
      handleDrop,
      sendFeedback,
      filteredProcedures,
      filteredAnomalies,
      criticalCount,
      highCount,
      predictedList,
      predictedClockTime,
      formatFullTimestamp,
      removeJob,
      exportReport,
      kpiFilterOptions,
      selectedGnbs,
      selectedCells,
      selectedMetrics,
      kpiSeriesLoading,
      loadKpiSeries,
      selectAllGnbs,
      selectAllCells,
      selectAllMetrics,
    };
  }
});

app.mount('#app');
