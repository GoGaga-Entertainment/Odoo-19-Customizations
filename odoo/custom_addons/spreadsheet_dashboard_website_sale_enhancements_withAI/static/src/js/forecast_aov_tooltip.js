/** @odoo-module **/

import { rpc } from "@web/core/network/rpc";

const MONTHS = {
    January: "01", February: "02", March: "03", April: "04",
    May: "05", June: "06", July: "07", August: "08",
    September: "09", October: "10", November: "11", December: "12",
};

const AOV_COLOR = "#7b61a8";
const STANDARD_DEVIATION_COLOR = "#d97706";
const MODE_PRODUCT_COLOR = "#2e8b57";
const MODE_FREQUENCY_COLOR = "#2f7f9f";

let aovByMonth = {};
let currencySymbol = "";
let modeProductByMonth = {};
let modeFrequencyByMonth = {};
let modeProductPriceByMonth = {};
let standardDeviationByMonth = {};
let ecommerceDashboardId = null;
let aovPromise = null;

function loadAovData() {
    if (!aovPromise) {
        aovPromise = rpc("/web/dataset/call_kw", {
            model: "website.sale.forecast.point",
            method: "get_monthly_aov_tooltip_data",
            args: [],
            kwargs: {},
        }).then((result) => {
            aovByMonth = (result && result.values) || {};
            currencySymbol = (result && result.currency_symbol) || "";
            modeProductByMonth = (result && result.mode_product) || {};
            modeFrequencyByMonth = (result && result.mode_frequency) || {};
            modeProductPriceByMonth = (result && result.mode_product_price) || {};
            standardDeviationByMonth = (result && result.standard_deviation) || {};
            ecommerceDashboardId = (result && result.dashboard_id) || null;
            return aovByMonth;
        }).catch(() => {
            aovByMonth = {};
            modeProductByMonth = {};
            modeFrequencyByMonth = {};
            modeProductPriceByMonth = {};
            standardDeviationByMonth = {};
            return aovByMonth;
        });
    }
    return aovPromise;
}


const ML_TOOLTIP_LABELS = {
    "ARIMA": "ARIMA Forecasted e-Commerce Revenue",
    "Exponential Smoothing": "Exponential Forecasted e-Commerce Revenue",
    "Linear Regression": "Linear Forecasted e-Commerce Revenue",
    "Polynomial Regression": "Polynomial Forecasted e-Commerce Revenue",
    // AOV chart: plain "Forecasted Revenue" series.
    "Forecasted Revenue": "Forecasted e-Commerce Revenue",
    // The Sales dashboard module's tooltip script (same page, same observer
    // approach) may already have expanded the short names to these longer
    // labels before this script runs. Map those too so the eCommerce names
    // are applied either way.
    "ARIMA Forecasted Revenue": "ARIMA Forecasted e-Commerce Revenue",
    "Exponential Smoothing Forecasted Revenue": "Exponential Forecasted e-Commerce Revenue",
    "Linear Forecasted Revenue": "Linear Forecasted e-Commerce Revenue",
    "Polynomial Forecasted Revenue": "Polynomial Forecasted e-Commerce Revenue",
};

/**
 * The chart series labels are intentionally short so the graph legend fits.
 * In the native hover tooltip, expand only those exact short labels to their
 * full descriptive names. The tooltip is date-scoped, so this does not alter
 * legend labels or other dashboard text.
 */
function expandMlTooltipLabels() {
    const candidates = document.querySelectorAll("body *");
    for (const element of candidates) {
        if (!(element instanceof HTMLElement) || !isVisible(element)) {
            continue;
        }
        const label = (element.textContent || "").trim();
        const fullLabel = ML_TOOLTIP_LABELS[label];
        if (!fullLabel || element.children.length > 0) {
            continue;
        }

        let ancestor = element.parentElement;
        while (ancestor && ancestor !== document.body) {
            const rect = ancestor.getBoundingClientRect();
            const text = ancestor.textContent || "";
            if (rect.width > 0 && rect.width <= 500 && rect.height > 0 && rect.height <= 250 && /\b20\d{2}\b/.test(text)) {
                element.textContent = fullLabel;
                break;
            }
            // Stop before climbing into a large chart or dashboard container.
            if (rect.width > 500 || rect.height > 250) {
                break;
            }
            ancestor = ancestor.parentElement;
        }
    }
}

/**
 * The Sales dashboard module (spreadsheet_dashboard_sale_enhancements_withAI)
 * ships a tooltip script with the same row classes, and both scripts watch
 * the same document. To keep this module's eCommerce-only numbers on the
 * eCommerce dashboard (and off the Sales dashboard), only act when the
 * eCommerce dashboard is the one currently open.
 */
function isEcommerceDashboardActive() {
    const urlId = new URLSearchParams(window.location.search).get("dashboard_id");
    if (urlId && ecommerceDashboardId) {
        return Number(urlId) === Number(ecommerceDashboardId);
    }
    const active = document.querySelector(
        ".o_spreadsheet_dashboard_search_panel .o_search_panel_category_value.active"
    );
    if (active) {
        return /commerce/i.test(active.getAttribute("data-name") || "");
    }
    // Cannot tell (e.g. collapsed sidebar and no dashboard_id in the URL).
    return true;
}

function monthKeyFromText(text) {
    const match = String(text || "").match(
        /\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(20\d{2})\b/
    );
    if (!match) {
        return null;
    }
    return `${match[2]}-${MONTHS[match[1]]}`;
}

function isVisible(element) {
    if (!(element instanceof HTMLElement)) {
        return false;
    }
    const style = window.getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return style.display !== "none" && style.visibility !== "hidden" &&
        rect.width > 0 && rect.height > 0;
}

function findForecastTooltip() {
    const candidates = document.querySelectorAll("body *");
    for (const element of candidates) {
        if (!isVisible(element)) {
            continue;
        }
        const text = element.textContent || "";
        if (!text.includes("Actual Revenue") || !/\b20\d{2}\b/.test(text)) {
            continue;
        }
        const key = monthKeyFromText(text);
        if (!key) {
            continue;
        }
        // The native spreadsheet tooltip is a compact floating element. Avoid
        // selecting the large dashboard/chart containers themselves.
        const rect = element.getBoundingClientRect();
        if (rect.width > 500 || rect.height > 250) {
            continue;
        }
        return { element, key };
    }
    return null;
}

function formatAov(value) {
    // Keep AOV in the same compact style as the revenue tooltip: 123k.
    // Truncation avoids changing 123,762 into 124k.
    const amount = Number(value) || 0;
    if (Math.abs(amount) >= 1000) {
        const compact = Math.floor(Math.abs(amount) / 1000);
        return `${amount < 0 ? "-" : ""}${compact}k`;
    }
    return new Intl.NumberFormat(undefined, {
        maximumFractionDigits: 0,
    }).format(amount);
}

function formatProductPrice(value) {
    // Plain number with thousands separators (e.g. 15,000), no currency
    // symbol, to match the tooltip layout "15,000 : HP Monitor".
    const amount = Number(value);
    if (!Number.isFinite(amount)) {
        return "";
    }
    return new Intl.NumberFormat(undefined, {
        maximumFractionDigits: 2,
        minimumFractionDigits: 0,
    }).format(amount);
}

/**
 * Given the "Actual Revenue" label element, find the marker CONTAINER
 * sitting next to it in the same tooltip row (the element that carries no
 * text of its own). This container may or may not be the visible swatch
 * itself -- see findColoredLeaf below, which drills into it.
 */
function findNativeMarker(labelEl) {
    if (!labelEl || !labelEl.parentElement) {
        return null;
    }
    const isMarkerCandidate = (el) =>
        el.nodeType === 1 && el !== labelEl && (el.textContent || "").trim() === "";

    const row = labelEl.parentElement;
    let marker = Array.from(row.children).find(isMarkerCandidate);
    if (marker) {
        return marker;
    }

    // Some tooltip layouts nest the label one level deeper than the marker.
    const outerRow = row.parentElement;
    if (outerRow && outerRow !== row) {
        marker = Array.from(outerRow.children).find(
            (el) => el !== row && isMarkerCandidate(el)
        );
        if (marker) {
            return marker;
        }
    }

    return null;
}

/** True if `el` itself actually paints a solid color (background or SVG fill). */
function isPaintedElement(el) {
    if (!(el instanceof Element)) {
        return false;
    }
    const style = window.getComputedStyle(el);
    const bg = style.backgroundColor;
    const bgImg = style.backgroundImage;
    const hasBackground =
        (bg && bg !== "transparent" && bg !== "rgba(0, 0, 0, 0)") ||
        (bgImg && bgImg !== "none");
    if (hasBackground) {
        return true;
    }
    const fillAttr = el.getAttribute && el.getAttribute("fill");
    if (fillAttr && fillAttr !== "none") {
        return true;
    }
    if (typeof SVGElement !== "undefined" && el instanceof SVGElement) {
        const fill = style.fill;
        if (fill && fill !== "none" && fill !== "transparent") {
            return true;
        }
    }
    return false;
}

/**
 * Within `container` (itself included), find the SMALLEST element that
 * actually has a real color applied to it. Charting-library swatches are
 * often a colored leaf nested inside a slightly larger, transparent
 * wrapper (for spacing/alignment). Cloning the wrapper and recoloring it
 * paints that wrapper's own padding too -- which the native version never
 * does -- so the clone ends up visibly bigger than the true swatch. The
 * smallest painted element is, by construction, the actual visible square.
 */
function findColoredLeaf(container) {
    if (!container) {
        return null;
    }
    const candidates = [container, ...container.querySelectorAll("*")];
    let best = null;
    let bestArea = Infinity;
    for (const el of candidates) {
        if (!isPaintedElement(el)) {
            continue;
        }
        const rect = el.getBoundingClientRect();
        if (rect.width <= 0 || rect.height <= 0) {
            continue;
        }
        const area = rect.width * rect.height;
        if (area < bestArea) {
            bestArea = area;
            best = el;
        }
    }
    return best;
}

/** Recolor a cloned marker without touching its size/shape at all. */
function recolorMarkerClone(clone, color) {
    // Shorthand `background` resets background-image/position too, so any
    // native gradient/pattern is replaced with a flat color, not layered on.
    clone.style.setProperty("background", color, "important");
    clone.style.setProperty("border-color", color, "important");
    clone.style.setProperty("color", color, "important"); // icon-font fills using currentColor
    if (clone.hasAttribute("fill")) {
        clone.setAttribute("fill", color);
    }
    clone.querySelectorAll("[fill]").forEach((node) => node.setAttribute("fill", color));
    return clone;
}

/**
 * Build the AOV marker. Preferred path: find the real "Actual Revenue"
 * swatch (the smallest actually-painted element near the label, drilling
 * past any transparent spacing wrapper) and clone JUST that leaf, then
 * recolor it -- so size/shape match by construction and no wrapper padding
 * gets colored in. Falls back to the marker's outer container, then to a
 * CSS-sized plain span, if no painted leaf can be located.
 */
function buildAovMarker(actualLabelEl, color = AOV_COLOR) {
    const container = findNativeMarker(actualLabelEl);
    const target = container ? (findColoredLeaf(container) || container) : null;
    if (target) {
        const clone = target.cloneNode(true);
        clone.removeAttribute("id");
        clone.classList.add("o_forecast_aov_marker_clone");
        return recolorMarkerClone(clone, color);
    }
    const span = document.createElement("span");
    span.className = "o_forecast_aov_marker";
    span.style.setProperty("background", color, "important");
    return span;
}

/**
 * Build one injected tooltip row (marker + label + value), using the same
 * clone-and-recolor marker as the native "Actual Revenue" row so every
 * injected row visually matches the native tooltip.
 *
 * `anchorLabelEl` is the reference element the marker is cloned from (the
 * "Actual Revenue" label). `insertAfterEl` is the element this new row is
 * inserted immediately after; passing the previously-inserted row lets rows
 * stack in a fixed order (AOV, then Mode Product, then Mode Frequency).
 */
function buildInjectedRow(
    rowClass,
    labelText,
    valueText,
    anchorLabelEl,
    markerColor = AOV_COLOR
) {
    const row = document.createElement("div");
    row.className = `o_forecast_aov_row o_forecast_web_row ${rowClass}`;

    const marker = buildAovMarker(anchorLabelEl, markerColor);
    const label = document.createElement("span");
    label.className = "o_forecast_aov_label";
    label.textContent = labelText;
    const strong = document.createElement("strong");
    strong.className = "o_forecast_aov_value";
    strong.textContent = valueText;

    row.appendChild(marker);
    row.appendChild(label);
    row.appendChild(strong);
    return row;
}

function injectAov(tooltip, key) {
    if (!tooltip || !key) {
        return;
    }
    // Rows injected by the Sales module's script (all sales orders) carry
    // the same base class but not our marker: replace them with eCommerce rows.
    tooltip.element
        .querySelectorAll(".o_forecast_aov_row:not(.o_forecast_web_row)")
        .forEach((row) => row.remove());
    if (tooltip.element.querySelector(".o_forecast_web_row")) {
        return;
    }

    const actualText = Array.from(tooltip.element.querySelectorAll("div, span"))
        .find((node) => (node.textContent || "").trim() === "Actual Revenue");

    // Each row is only added when its own value is actually available for
    // this month, so a month missing e.g. mode product data still gets the
    // AOV row (and vice versa) instead of all rows disappearing together.
    let lastInserted = actualText ? actualText.parentElement : null;

    const aovValue = aovByMonth[key];
    if (aovValue !== undefined && aovValue !== null) {
        const row = buildInjectedRow(
            "o_forecast_aov_row_aov",
            "Average Order Value",
            formatAov(aovValue),
            actualText
        );
        if (lastInserted) {
            lastInserted.insertAdjacentElement("afterend", row);
        } else {
            tooltip.element.appendChild(row);
        }
        lastInserted = row;
    }

    const modeProduct = modeProductByMonth[key];
    const modeProductPrice = modeProductPriceByMonth[key];
    const modeFrequency = modeFrequencyByMonth[key];
    if (modeProduct !== undefined && modeProduct !== null && modeProduct !== "") {
        // Layout: label "Mode : Products", value "15,000 : HP Monitor"
        // (price first, then product name).
        const priceText =
            modeProductPrice !== undefined && modeProductPrice !== null
                ? formatProductPrice(modeProductPrice)
                : "";
        const productAndPrice = priceText
            ? `${priceText} : ${modeProduct}`
            : String(modeProduct);
        const row = buildInjectedRow(
            "o_forecast_aov_row_mode_product",
            "Mode : Products",
            productAndPrice,
            actualText,
            MODE_PRODUCT_COLOR
        );
        if (lastInserted) {
            lastInserted.insertAdjacentElement("afterend", row);
        } else {
            tooltip.element.appendChild(row);
        }
        lastInserted = row;
    }

    // Frequency is a separate native-style tooltip row with its own marker,
    // label, and right-aligned value, matching the other tooltip entries.
    if (modeFrequency !== undefined && modeFrequency !== null) {
        const row = buildInjectedRow(
            "o_forecast_aov_row_mode_frequency",
            "Frequency",
            String(modeFrequency),
            actualText,
            MODE_FREQUENCY_COLOR
        );
        if (lastInserted) {
            lastInserted.insertAdjacentElement("afterend", row);
        } else {
            tooltip.element.appendChild(row);
        }
        lastInserted = row;
    }

    // Standard deviation is calculated independently for each month from
    // that month's confirmed sales-order totals.
    const monthlyStandardDeviation = standardDeviationByMonth[key];
    if (monthlyStandardDeviation !== undefined && monthlyStandardDeviation !== null) {
        const row = buildInjectedRow(
            "o_forecast_aov_row_standard_deviation",
            "Standard Deviation",
            formatAov(monthlyStandardDeviation),
            actualText,
            STANDARD_DEVIATION_COLOR
        );
        if (lastInserted) {
            lastInserted.insertAdjacentElement("afterend", row);
        } else {
            tooltip.element.appendChild(row);
        }
    }
}

async function updateTooltip() {
    // Rename the ML series only on the eCommerce dashboard, so the Sales
    // dashboard keeps its own labels.
    await loadAovData();
    if (!isEcommerceDashboardActive()) {
        return;
    }
    expandMlTooltipLabels();
    const tooltip = findForecastTooltip();
    if (!tooltip) {
        return;
    }
    injectAov(tooltip, tooltip.key);
}

function startObserver() {
    loadAovData();
    const observer = new MutationObserver(() => {
        updateTooltip();
    });
    observer.observe(document.body, {
        childList: true,
        subtree: true,
        characterData: true,
        attributes: true,
        attributeFilter: ["style", "class"],
    });

    document.addEventListener("mousemove", () => {
        updateTooltip();
    }, { passive: true });
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", startObserver, { once: true });
} else {
    startObserver();
}