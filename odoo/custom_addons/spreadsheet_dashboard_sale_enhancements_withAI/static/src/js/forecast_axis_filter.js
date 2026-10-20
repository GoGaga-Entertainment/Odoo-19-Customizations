/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { OdooChartFeaturePlugin } from "@spreadsheet/chart/plugins/odoo_chart_feature_plugin";

const FORECAST_FILTER_ID = "f7c6f2f1-7f8f-4e0f-a0fd-3a3a8a7e0f21";
const FORECAST_CHART_ID = "1a4b7f9c-2f8e-4c13-9a6e-2e8b7b1c4d55";
const ML_FORECAST_CHART_ID = "8e2f7c41-6a95-4d30-b18e-52c7f9a6d184";
const VALIDATION_CHART_ID = "6c4a1f82-9d7e-4b13-a5f0-2e8c6d7b1a90";

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
// Set to true to also restrict the non-forecast charts (e.g. Monthly Sales).
const APPLY_TO_ALL_CHARTS = true;

console.info("[forecast_axis_filter] loaded: chart group-by options follow Forecast Period");

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
        if (
            !APPLY_TO_ALL_CHARTS &&
            ![FORECAST_CHART_ID, ML_FORECAST_CHART_ID, VALIDATION_CHART_ID].includes(chartId)
        ) {
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

// Register once with the Chart.js instance used by the Odoo asset bundle.
// Chart.js is shipped by Odoo as a plain global script (window.Chart); it is
// NOT an importable ES module, so it must not be imported.
const Chart = typeof window !== "undefined" ? window.Chart : undefined;
if (Chart && typeof Chart.register === "function") {
    Chart.register(forecastDailyTicksPlugin);
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

            for (const chartId of [FORECAST_CHART_ID, ML_FORECAST_CHART_ID, VALIDATION_CHART_ID]) {
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
                // The trained/tested chart follows the selected forecast horizon too:
                // daily grouping for 7 Days, monthly grouping for longer horizons.
                const isValidationChart = chartId === VALIDATION_CHART_ID;
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


// Odoo may build the chart's initial view before the global-filter command
// handler runs. Override only the trained/tested chart definition on read so
// its initial grouping also follows the currently selected Forecast Period.
patch(OdooChartFeaturePlugin.prototype, {
    getChartDefinition(chartId) {
        const definition = super.getChartDefinition(chartId);
        if (!definition || chartId !== VALIDATION_CHART_ID) {
            return definition;
        }

        try {
            const filterId = findForecastFilterId(this.getters);
            const period = normalizeForecastPeriod(
                this.getters.getGlobalFilterValue(filterId)
            );
            if (!period) {
                return definition;
            }

            const grain = getForecastGrain(period);
            const { nested, meta, search } = readChartParams(definition);
            const metaGroupBy = meta.groupBy || [];
            const searchGroupBy = search.groupBy || [];
            if (metaGroupBy[0] === grain && searchGroupBy[0] === grain) {
                return definition;
            }

            const groupBy = [grain, "series"];
            return writeChartParams(
                definition,
                nested,
                { ...meta, groupBy },
                { ...search, groupBy }
            );
        } catch (_error) {
            return definition;
        }
    },
});
