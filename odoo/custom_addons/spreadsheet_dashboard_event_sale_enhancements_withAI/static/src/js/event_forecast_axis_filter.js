/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { rpc } from "@web/core/network/rpc";
import { OdooChartFeaturePlugin } from "@spreadsheet/chart/plugins/odoo_chart_feature_plugin";

const FORECAST_FILTER_ID = "c3a91e5b-7d24-4f68-9b0a-5e1d8c2f7a10";
const FORECAST_CHART_ID = "c3a91e5b-7d24-4f68-9b0a-5e1d8c2f7a11";
const ML_FORECAST_CHART_ID = "c3a91e5b-7d24-4f68-9b0a-5e1d8c2f7a12";
const VALIDATION_CHART_ID = "c3a91e5b-7d24-4f68-9b0a-5e1d8c2f7a13";
// Only these three charts follow the "Forecast Period" filter. No other chart
// (e.g. Monthly Sales) is touched by any logic in this file.
const FORECAST_CHART_IDS = [FORECAST_CHART_ID, ML_FORECAST_CHART_ID, VALIDATION_CHART_ID];

// ---------------------------------------------------------------------------
// Chart "group by" selector (the small <select> next to each chart title)
// ---------------------------------------------------------------------------
// Odoo 19 renders that selector from the `getAvailableChartGranularities`
// getter of OdooChartFeaturePlugin, so we filter the list there (a DOM-based
// approach cannot work: the control is a native <select>).
//
// Rules, driven by the "Forecast Period" global filter in the header:
//   * Days selected   (7 Days)               -> Days, Months
//   * Months selected (1 Month, 6 Months)    -> Months, Quarters
//   * Years selected  (1/2/5/10 Years)       -> Months, Quarters, Years
//   * Nothing selected                       -> every option (Odoo default)
//
console.info("[event_forecast_axis_filter] loaded: chart group-by options follow Forecast Period");

const VALID_FORECAST_PERIODS = [
    "7_days", "1_month", "6_months", "1_year", "2_years", "5_years", "10_years",
];

function matchForecastPeriod(raw) {
    if (typeof raw !== "string") {
        return null;
    }
    const normalized = raw.trim().toLowerCase().replace(/[ -]/g, "_");
    if (VALID_FORECAST_PERIODS.includes(normalized)) {
        return normalized;
    }
    // Accommodate display labels such as "6 Months".
    const compact = normalized.replace(/_/g, "");
    return VALID_FORECAST_PERIODS.find((key) => key.replace(/_/g, "") === compact) || null;
}

/**
 * Extract the selected forecast period from whatever shape the global filter
 * value has. Odoo 19 selection filters store
 * `{ operator: "in", selectionValues: ["6_months"] }`; other versions may
 * return a plain string or an array. Returns null when nothing is selected
 * (e.g. the facet was removed from the search bar).
 */
function normalizeForecastPeriod(value) {
    if (value === null || value === undefined || value === "") {
        return null;
    }
    if (typeof value === "string") {
        return matchForecastPeriod(value);
    }
    if (Array.isArray(value)) {
        for (const item of value) {
            const match = normalizeForecastPeriod(item);
            if (match) {
                return match;
            }
        }
        return null;
    }
    if (typeof value === "object") {
        const candidates = value.selectionValues ?? value.value ?? value.values ?? null;
        return candidates === null ? null : normalizeForecastPeriod(candidates);
    }
    return null;
}

/** Granularity values (as used by Odoo: day, month, ...) allowed per period. */
function allowedGranularitiesForPeriod(period) {
    switch (period) {
        case "7_days":
            return ["day", "month"];
        case "1_month":
        case "6_months":
            return ["month", "quarter"];
        case "1_year":
        case "2_years":
        case "5_years":
        case "10_years":
            return ["month", "quarter", "year"];
        default:
            return null; // nothing selected -> no restriction
    }
}

function findForecastFilterId(getters) {
    try {
        const filters = getters.getGlobalFilters?.() || [];
        const byId = filters.find((f) => f.id === FORECAST_FILTER_ID);
        if (byId) {
            return byId.id;
        }
        const other = filters.find(
            (f) => f.label === "Forecast Period" || f.selectionField === "forecast_period"
        );
        return other ? other.id : FORECAST_FILTER_ID;
    } catch (_error) {
        return FORECAST_FILTER_ID;
    }
}

patch(OdooChartFeaturePlugin.prototype, {
    getAvailableChartGranularities(chartId) {
        const options = super.getAvailableChartGranularities(chartId);
        if (!options?.length) {
            return options;
        }
        if (!FORECAST_CHART_IDS.includes(chartId)) {
            return options;
        }
        let period = null;
        try {
            period = normalizeForecastPeriod(
                this.getters.getGlobalFilterValue(findForecastFilterId(this.getters))
            );
        } catch (_error) {
            return options;
        }
        const allowed = allowedGranularitiesForPeriod(period);
        if (!allowed) {
            return options;
        }
        const filtered = options.filter((option) => allowed.includes(option.value));
        return filtered.length ? filtered : options;
    },
});

// This flag is deliberately kept outside the chart definition. Odoo
// Spreadsheet can recreate the Chart.js instance after a global-filter
// change, so the setting must survive chart recreation.
let forecastDailyAxisEnabled = false;

function getForecastGrain(value) {
    // 7 Days is displayed at daily resolution. All longer forecast
    // horizons keep the existing monthly resolution.
    return normalizeForecastPeriod(value) === "7_days" ? "date:day" : "date:month";
}

function isOverallForecastChart(chart) {
    if (!chart?.data || !Array.isArray(chart.data.datasets)) {
        return false;
    }

    const datasetLabels = chart.data.datasets.map((dataset) =>
        String(dataset.label || "")
    );
    const hasActual = datasetLabels.some((label) =>
        /actual\s*revenue/i.test(label)
    );
    const hasForecast = datasetLabels.some((label) =>
        /forecast/i.test(label)
    );
    const hasES = datasetLabels.some((label) =>
        /exponential\s*smoothing/i.test(label)
    );

    // The native forecast chart has Actual + Forecast series. The ML chart
    // contains the Exponential Smoothing and/or ARIMA time-series series.
    return (hasActual && hasForecast) || hasES;
}

/**
 * Chart.js normally auto-skips X-axis ticks when there are many daily points.
 * In Odoo Spreadsheet that can leave labels such as:
 *
 *   01 Mar, 06 Mar, 11 Mar, 16 Mar ...
 *
 * For the 7 Days forecast view we need the daily tick list itself to contain
 * every available day. Merely setting `autoSkip: false` after the chart has
 * already built its ticks is too late in some Odoo Spreadsheet render cycles.
 * This plugin changes the tick list during `afterBuildTicks`, before Chart.js
 * performs its final label conversion/drawing.
 */
const forecastDailyTicksPlugin = {
    id: "salesForecastDailyTicks",

    afterBuildTicks(chart, args) {
        if (!forecastDailyAxisEnabled || args?.scale?.id !== "x") {
            return;
        }

        const scale = args.scale;
        if (!isOverallForecastChart(chart)) {
            return;
        }

        // Category scale: every chart label corresponds to one daily point.
        if (scale.type === "category" && Array.isArray(chart.data?.labels)) {
            args.scale.ticks = chart.data.labels.map((_, index) => ({
                value: index,
            }));
            return;
        }

        // Time/linear scale: collect every distinct X value from the datasets.
        // Odoo Spreadsheet may store points as either `{x, y}` objects or use
        // a separate labels array, so support both forms.
        const values = new Set();
        for (const dataset of chart.data?.datasets || []) {
            for (const point of dataset.data || []) {
                if (point && typeof point === "object" && point.x !== undefined) {
                    values.add(point.x);
                }
            }
        }

        if (!values.size && Array.isArray(chart.data?.labels)) {
            for (const value of chart.data.labels) {
                values.add(value);
            }
        }

        if (values.size) {
            const sortedValues = [...values].sort((a, b) => {
                const na = typeof a === "number" ? a : Date.parse(a);
                const nb = typeof b === "number" ? b : Date.parse(b);
                if (Number.isFinite(na) && Number.isFinite(nb)) {
                    return na - nb;
                }
                return String(a).localeCompare(String(b));
            });
            args.scale.ticks = sortedValues.map((value) => ({ value }));
        }
    },
};

/**
 * Display clean-up for the Events dashboard line charts:
 *  - drop the stray "None" dataset (legend entry + flat line) that Odoo adds
 *    when a group has no series value;
 *  - show "Untaxed Total" instead of "Untaxed Revenues" on the Monthly Event
 *    Sales chart (fallback for versions that ignore dataSets[].label).
 * Only multi/single-series LINE charts are touched; pie/bar/geo are not.
 */
// Tooltip text such as "ARIMA Forecasted Revenue" is produced outside this
// module; on Events charts it must read "ARIMA Forecasted Event Revenue".
function renameForecastedRevenue(text) {
    if (typeof text === "string") {
        return text.replace(/\bForecasted\s+Revenue\b/g, "Forecasted Event Revenue");
    }
    if (Array.isArray(text)) {
        return text.map(renameForecastedRevenue);
    }
    return text;
}

function isEventsChart(chart) {
    const title = chart?.options?.plugins?.title?.text;
    const text = Array.isArray(title) ? title.join(" ") : String(title || "");
    return /event/i.test(text);
}

function wrapEventTooltipLabel(chart) {
    if (!isEventsChart(chart)) {
        return;
    }
    const callbacks = chart.options?.plugins?.tooltip?.callbacks;
    if (!callbacks || (callbacks.label && callbacks.label.__eventRenamed)) {
        return;
    }
    const original = callbacks.label;
    const wrapped = function (context) {
        const result = original
            ? original.call(this, context)
            : `${context?.dataset?.label ?? ""}`;
        return renameForecastedRevenue(result);
    };
    wrapped.__eventRenamed = true;
    callbacks.label = wrapped;
}

const eventChartCleanupPlugin = {
    id: "eventChartCleanup",

    beforeEvent(chart) {
        wrapEventTooltipLabel(chart);
    },

    afterUpdate(chart) {
        wrapEventTooltipLabel(chart);
    },

    beforeUpdate(chart) {
        wrapEventTooltipLabel(chart);
        const config = chart?.config;
        const type = config?._config?.type ?? config?.type;
        const data = chart?.data;
        if (type !== "line" || !data || !Array.isArray(data.datasets)) {
            return;
        }
        const isNone = (dataset) => String(dataset?.label ?? "").trim() === "None";
        if (data.datasets.some(isNone) && data.datasets.some((d) => !isNone(d))) {
            data.datasets = data.datasets.filter((d) => !isNone(d));
        }
        if (data.datasets.length === 1 && data.datasets[0].label === "Untaxed Revenues") {
            data.datasets[0].label = "Untaxed Total";
        }
    },
};

// Register once with the Chart.js instance used by the Odoo asset bundle.
// Chart.js is shipped by Odoo as a plain global script (window.Chart); it is
// NOT an importable ES module, so it must not be imported.
// ---------------------------------------------------------------------------
// DOM-level rename: "<Model> Forecasted Revenue" -> "<Model> Forecasted Event
// Revenue" in the hover tooltip of the Events forecast charts.
//
// The tooltip text is produced outside this module (it is not in any file of
// this addon and not in Odoo's spreadsheet/web code), so the text is corrected
// where it is finally displayed.  It only applies while the pointer is over
// one of the Events forecast charts, so other dashboards are never touched.
// ---------------------------------------------------------------------------
const EVENT_FIGURE_IDS = new Set(FORECAST_CHART_IDS);
const FORECASTED_REVENUE_RE = /\bForecasted\s+Revenue\b/g;
let pointerOverEventsChart = false;

function figureIsEventsChart(target) {
    if (!(target instanceof Element)) {
        return false;
    }
    // 1) The figure wrapper carries the figure id (== our chart id).
    const figure = target.closest("[data-id]");
    if (figure && EVENT_FIGURE_IDS.has(figure.getAttribute("data-id"))) {
        return true;
    }
    // 2) The canvas belongs to a Chart.js chart whose title mentions "Event".
    const canvas = target.closest("canvas") || target.querySelector?.("canvas");
    const chart = canvas && window.Chart?.getChart?.(canvas);
    if (chart && isEventsChart(chart)) {
        return true;
    }
    return false;
}

function renameTextNodes(root) {
    if (!root) {
        return;
    }
    if (root.nodeType === Node.TEXT_NODE) {
        if (FORECASTED_REVENUE_RE.test(root.nodeValue)) {
            FORECASTED_REVENUE_RE.lastIndex = 0;
            root.nodeValue = root.nodeValue.replace(
                FORECASTED_REVENUE_RE, "Forecasted Event Revenue");
        }
        FORECASTED_REVENUE_RE.lastIndex = 0;
        return;
    }
    if (root.nodeType !== Node.ELEMENT_NODE) {
        return;
    }
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    let node = walker.nextNode();
    while (node) {
        renameTextNodes(node);
        node = walker.nextNode();
    }
}

// ---------------------------------------------------------------------------
// Events-only statistics in the hover tooltip of the AOV chart.
//
// Hovering "Actual Event Revenue" adds Average Order Value, Mode: Ticket Type,
// Frequency and Standard Deviation, computed from EVENT orders only by
// event.forecast.point.get_tooltip_stats (same data as the plotted revenue).
// ---------------------------------------------------------------------------
const STATS_TTL_MS = 60 * 1000;
const MONTH_INDEX = {
    jan: 0, feb: 1, mar: 2, apr: 3, may: 4, jun: 5,
    jul: 6, aug: 7, sep: 8, oct: 9, nov: 10, dec: 11,
};
const STAT_COLORS = ["#8E7CC3", "#2E8B57", "#2A9D8F", "#F28E2B"];
let tooltipStats = null;
let tooltipStatsLoadedAt = 0;
let tooltipStatsPromise = null;

function loadTooltipStats() {
    if (tooltipStats && Date.now() - tooltipStatsLoadedAt < STATS_TTL_MS) {
        return Promise.resolve(tooltipStats);
    }
    if (!tooltipStatsPromise) {
        tooltipStatsPromise = rpc("/web/dataset/call_kw/event.forecast.point/get_tooltip_stats", {
            model: "event.forecast.point",
            method: "get_tooltip_stats",
            args: [],
            kwargs: {},
        })
            .then((result) => {
                tooltipStats = result?.days || {};
                tooltipStatsLoadedAt = Date.now();
                return tooltipStats;
            })
            .catch(() => tooltipStats || {})
            .finally(() => {
                tooltipStatsPromise = null;
            });
    }
    return tooltipStatsPromise;
}

const pad2 = (n) => String(n).padStart(2, "0");
const dayKey = (y, m, d) => `${y}-${pad2(m + 1)}-${pad2(d)}`;

/** Turn a tooltip title ("August 2026", "21 Oct 2026", "Q4 2026", "2026")
 *  into a [startKey, endKey) range of "YYYY-MM-DD" day keys. */
function periodRangeFromTitle(title) {
    const text = String(title || "").trim();
    let match = text.match(/^Q([1-4])\s+(\d{4})$/i);
    if (match) {
        const year = Number(match[2]);
        const first = (Number(match[1]) - 1) * 3;
        return [dayKey(year, first, 1), first + 3 > 11
            ? dayKey(year + 1, 0, 1) : dayKey(year, first + 3, 1)];
    }
    match = text.match(/^(\d{4})$/);
    if (match) {
        return [dayKey(Number(match[1]), 0, 1), dayKey(Number(match[1]) + 1, 0, 1)];
    }
    match = text.match(/^([A-Za-z]+)\.?\s+(\d{4})$/);
    if (match && MONTH_INDEX[match[1].slice(0, 3).toLowerCase()] !== undefined) {
        const year = Number(match[2]);
        const month = MONTH_INDEX[match[1].slice(0, 3).toLowerCase()];
        return [dayKey(year, month, 1), month === 11
            ? dayKey(year + 1, 0, 1) : dayKey(year, month + 1, 1)];
    }
    const parsed = new Date(text);
    if (!Number.isNaN(parsed.getTime())) {
        const y = parsed.getFullYear();
        const m = parsed.getMonth();
        const d = parsed.getDate();
        const next = new Date(y, m, d + 1);
        return [dayKey(y, m, d), dayKey(next.getFullYear(), next.getMonth(), next.getDate())];
    }
    return null;
}

function aggregateStats(days, range) {
    const [start, end] = range;
    let revenue = 0;
    let orders = 0;
    let sumsq = 0;
    const tickets = {};
    for (const [key, day] of Object.entries(days || {})) {
        if (key >= start && key < end) {
            revenue += day.revenue || 0;
            orders += day.orders || 0;
            sumsq += day.sumsq || 0;
            for (const [name, qty] of Object.entries(day.tickets || {})) {
                tickets[name] = (tickets[name] || 0) + qty;
            }
        }
    }
    if (!orders) {
        return null;
    }
    const mean = revenue / orders;
    const variance = Math.max(0, sumsq / orders - mean * mean);
    const top = Object.entries(tickets).sort((a, b) => b[1] - a[1])[0];
    return { mean, orders, deviation: Math.sqrt(variance), top };
}

function formatAmount(value) {
    const abs = Math.abs(value);
    if (abs >= 1000) {
        return `${Math.round(value / 1000).toLocaleString("en-US")}k`;
    }
    return value.toFixed(2).replace(/\.00$/, "");
}

function tooltipChartIsAov(tooltipEl) {
    const figure = tooltipEl.closest("[data-id]");
    if (figure && figure.getAttribute("data-id") === FORECAST_CHART_ID) {
        return true;
    }
    const canvas = tooltipEl.parentNode?.querySelector?.("canvas");
    const chart = canvas && window.Chart?.getChart?.(canvas);
    const title = chart?.options?.plugins?.title?.text;
    const text = Array.isArray(title) ? title.join(" ") : String(title || "");
    return /event sales forecast\s*\(AOV\)/i.test(text);
}

function appendStatRows(tooltipEl, stats) {
    const tbody = tooltipEl.querySelector("tbody");
    if (!tbody || tooltipEl.dataset.eventStats === "1") {
        return;
    }
    tooltipEl.dataset.eventStats = "1";
    const rows = [
        ["Average Order Value", formatAmount(stats.mean)],
        ["Mode : Ticket Type", stats.top
            ? `${Math.round(stats.top[1]).toLocaleString("en-US")} : ${stats.top[0]}` : "-"],
        ["Frequency", String(stats.orders)],
        ["Standard Deviation", formatAmount(stats.deviation)],
    ];
    const heightBefore = tooltipEl.clientHeight;
    rows.forEach(([label, value], index) => {
        const tr = document.createElement("tr");
        const left = document.createElement("td");
        const swatch = document.createElement("span");
        swatch.className = "badge ps-2 py-2 rounded-0 align-middle";
        swatch.style.backgroundColor = STAT_COLORS[index];
        swatch.textContent = " ";
        const name = document.createElement("small");
        name.className = "o-tooltip-label d-inline-block text-truncate align-middle smaller ms-2";
        name.textContent = label;
        left.append(swatch, name);
        const right = document.createElement("td");
        right.className = "o-tooltip-value ps-2 fw-bolder text-end";
        const small = document.createElement("small");
        small.className = "smaller d-inline-block text-truncate align-middle";
        small.textContent = value;
        right.append(small);
        tr.append(left, right);
        tbody.append(tr);
    });
    // Keep the tooltip vertically centred on the hovered point.
    const grown = tooltipEl.clientHeight - heightBefore;
    const top = parseFloat(tooltipEl.style.top);
    if (grown > 0 && Number.isFinite(top)) {
        tooltipEl.style.top = `${top - grown / 2}px`;
    }
}

function decorateAovTooltip(node) {
    if (!(node instanceof Element)) {
        return;
    }
    const tooltipEl = node.matches?.("div.o-chart-custom-tooltip")
        ? node
        : node.querySelector?.("div.o-chart-custom-tooltip");
    if (!tooltipEl || !tooltipChartIsAov(tooltipEl)) {
        return;
    }
    // Only the "Actual Event Revenue" hover gets the extra statistics.
    if (!/Actual Event Revenue/.test(tooltipEl.textContent || "")) {
        return;
    }
    const range = periodRangeFromTitle(
        tooltipEl.querySelector(".o-tooltip-title")?.textContent
    );
    if (!range) {
        return;
    }
    loadTooltipStats().then((days) => {
        if (!tooltipEl.isConnected) {
            return;
        }
        const stats = aggregateStats(days, range);
        if (stats) {
            appendStatRows(tooltipEl, stats);
        }
    });
}

if (typeof document !== "undefined" && typeof MutationObserver !== "undefined") {
    document.addEventListener("mouseover", (ev) => {
        pointerOverEventsChart = figureIsEventsChart(ev.target);
    }, true);

    const tooltipObserver = new MutationObserver((mutations) => {
        if (!pointerOverEventsChart) {
            return;
        }
        for (const mutation of mutations) {
            if (mutation.type === "characterData") {
                renameTextNodes(mutation.target);
            } else {
                for (const node of mutation.addedNodes) {
                    renameTextNodes(node);
                    decorateAovTooltip(node);
                }
            }
        }
    });
    const startObserver = () => tooltipObserver.observe(document.body, {
        childList: true, subtree: true, characterData: true,
    });
    if (document.body) {
        startObserver();
    } else {
        document.addEventListener("DOMContentLoaded", startObserver, { once: true });
    }
}

const Chart = typeof window !== "undefined" ? window.Chart : undefined;
if (Chart && typeof Chart.register === "function") {
    Chart.register(forecastDailyTicksPlugin);
    Chart.register(eventChartCleanupPlugin);
}

function updateDailyAxisLabels(showEveryDay) {
    if (!Chart || typeof Chart.getChart !== "function") {
        return;
    }

    document.querySelectorAll("canvas").forEach((canvas) => {
        const chart = Chart.getChart(canvas);
        if (!chart || !isOverallForecastChart(chart) || !chart.options?.scales?.x) {
            return;
        }

        const xScale = chart.options.scales.x;
        xScale.ticks = {
            ...(xScale.ticks || {}),
            autoSkip: !showEveryDay,
            // Remove the practical tick-count ceiling in the daily view.
            // The plugin above supplies the complete daily tick list.
            maxTicksLimit: showEveryDay ? undefined : (xScale.ticks?.maxTicksLimit || 11),
            source: showEveryDay ? "data" : (xScale.ticks?.source || "auto"),
            minRotation: showEveryDay ? 45 : (xScale.ticks?.minRotation ?? 0),
            maxRotation: showEveryDay ? 45 : (xScale.ticks?.maxRotation ?? 50),
        };

        chart.update("none");
    });
}

function refreshForecastAxisLabels(showEveryDay) {
    forecastDailyAxisEnabled = showEveryDay;

    // Odoo can destroy/recreate the canvas while applying the filter. Keep a
    // short refresh window so the setting is applied to the newly-created
    // Chart.js instance as well.
    const delays = [0, 50, 150, 300, 600, 1000];
    for (const delay of delays) {
        window.setTimeout(() => updateDailyAxisLabels(showEveryDay), delay);
    }
}

/**
 * Chart definitions differ between Odoo versions:
 *  - older:  definition.metaData / definition.searchParams
 *  - newer:  definition.dataSource.metaData / definition.dataSource.searchParams
 * These helpers read and rewrite whichever shape is present.
 */
function readChartParams(definition) {
    if (definition?.dataSource?.metaData) {
        return {
            nested: true,
            meta: definition.dataSource.metaData,
            search: definition.dataSource.searchParams || {},
        };
    }
    return {
        nested: false,
        meta: definition?.metaData || {},
        search: definition?.searchParams || {},
    };
}

function writeChartParams(definition, nested, meta, search) {
    if (nested) {
        return {
            ...definition,
            dataSource: { ...definition.dataSource, metaData: meta, searchParams: search },
        };
    }
    return { ...definition, metaData: meta, searchParams: search };
}

/**
 * Called after any global filter command. When the Forecast Period filter was
 * set or cleared, re-group the forecast charts (days for 7 Days, months
 * otherwise) and keep the validation chart's domain in sync.
 */
function syncForecastCharts(plugin, cmd) {
    const isFilterCmd =
        (cmd.type === "SET_GLOBAL_FILTER_VALUE" || cmd.type === "CLEAR_GLOBAL_FILTER_VALUE") &&
        cmd.id === FORECAST_FILTER_ID;
    if (!isFilterCmd) {
        return;
    }
    queueMicrotask(() => {
        try {
            const rawValue = plugin.getters.getGlobalFilterValue(FORECAST_FILTER_ID);
            // Plain period key ("6_months") or null when nothing selected.
            const value = normalizeForecastPeriod(rawValue);
            const grain = getForecastGrain(value);
            const sheetId = plugin.getters.getActiveSheetId?.();

            for (const chartId of FORECAST_CHART_IDS) {
                let definition;
                try {
                    definition = plugin.getters.getChartDefinition(chartId);
                } catch (_error) {
                    definition = null;
                }
                if (!definition) {
                    continue;
                }

                const { nested, meta: currentMeta, search: currentSearch } =
                    readChartParams(definition);
                const currentMetaGroupBy = currentMeta.groupBy || [];
                const currentSearchGroupBy = currentSearch.groupBy || [];
                const isValidationChart = chartId === VALIDATION_CHART_ID;
                // All three forecast charts (including Trained & Tested) use
                // days for 7 Days and months for every other period.
                const desiredGroupBy = [grain, "series"];
                // Keep a granularity the user picked from the side menu
                // (e.g. Quarters) as long as it is still allowed.
                const allowedNow = allowedGranularitiesForPeriod(value);
                const currentGrain = (currentMetaGroupBy[0] || "").split(":")[1];
                const keepUserGrain =
                    !isValidationChart &&
                    value !== "7_days" &&
                    allowedNow &&
                    allowedNow.includes(currentGrain) &&
                    currentSearchGroupBy[0] === currentMetaGroupBy[0];
                const finalGroupBy = keepUserGrain ? [...currentMetaGroupBy] : desiredGroupBy;
                const sameGroupBy =
                    currentMetaGroupBy.length === finalGroupBy.length &&
                    currentSearchGroupBy.length === finalGroupBy.length &&
                    finalGroupBy.every((item, index) =>
                        currentMetaGroupBy[index] === item &&
                        currentSearchGroupBy[index] === item
                    );

                const currentDomain = Array.isArray(currentSearch.domain) ? currentSearch.domain : [];
                const withoutPeriod = currentDomain.filter((item) => !(Array.isArray(item) && item[0] === "forecast_period"));
                const desiredDomain = isValidationChart
                    ? (value ? [...withoutPeriod, ["forecast_period", "=", value]] : withoutPeriod)
                    : currentDomain;
                const domainChanged = isValidationChart && JSON.stringify(currentDomain) !== JSON.stringify(desiredDomain);

                if (!sameGroupBy || domainChanged) {
                    let figureId;
                    try {
                        figureId = plugin.getters.getFigureIdFromChartId?.(chartId);
                    } catch (_error) {
                        figureId = undefined;
                    }
                    plugin.dispatch("UPDATE_CHART", {
                        // chartId/figureId: current Odoo; id/sheetId: older.
                        chartId,
                        figureId,
                        id: chartId,
                        sheetId,
                        definition: writeChartParams(
                            definition,
                            nested,
                            { ...currentMeta, groupBy: finalGroupBy },
                            { ...currentSearch, groupBy: finalGroupBy, domain: desiredDomain }
                        ),
                    });
                }
            }

            refreshForecastAxisLabels(value === "7_days");
        } catch (error) {
            console.warn("Forecast axis update skipped:", error);
        }
    });
}

// Hook into whichever command mechanism this Odoo version's plugin uses:
//  - newer Odoo: declarative `handlers` map -> onSetGlobalFilterValue()
//  - older Odoo: a generic handle(cmd) method
const featureProto = OdooChartFeaturePlugin.prototype;
if (typeof featureProto.onSetGlobalFilterValue === "function") {
    patch(featureProto, {
        onSetGlobalFilterValue(cmd) {
            const result = super.onSetGlobalFilterValue(cmd);
            syncForecastCharts(this, cmd);
            return result;
        },
    });
} else if (typeof featureProto.handle === "function") {
    patch(featureProto, {
        handle(cmd) {
            super.handle(cmd);
            syncForecastCharts(this, cmd);
        },
    });
}