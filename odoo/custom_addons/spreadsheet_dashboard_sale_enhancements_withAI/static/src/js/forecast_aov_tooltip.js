
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
let aovPromise = null;

function loadAovData() {
    if (!aovPromise) {
        aovPromise = rpc("/web/dataset/call_kw", {
            model: "sale.forecast.point",
            method: "get_monthly_aov_tooltip_data",
            args: [],
            kwargs: {},
        }).then((result) => {
            aovByMonth = (result && result.values) || {};
            currencySymbol = (result && result.currency_symbol) || "";
            modeProductByMonth = (result && result.mode_product) || {};
            modeFrequencyByMonth = (result && result.mode_frequency) || {};
            modeProductPriceByMonth =
                (result && result.mode_product_price) || {};
            standardDeviationByMonth =
                (result && result.standard_deviation) || {};

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
    "ARIMA": "ARIMA Forecasted Revenue",
    "Exponential Smoothing":
        "Exponential Smoothing Forecasted Revenue",
    "Linear Regression": "Linear Forecasted Revenue",
    "Polynomial Regression": "Polynomial Forecasted Revenue",
};

/**
 * Expand short ML graph labels only inside the native chart tooltip.
 * Graph legend labels remain unchanged.
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

            if (
                rect.width > 0 &&
                rect.width <= 500 &&
                rect.height > 0 &&
                rect.height <= 250 &&
                /\b20\d{2}\b/.test(text)
            ) {
                element.textContent = fullLabel;
                break;
            }

            if (rect.width > 500 || rect.height > 250) {
                break;
            }

            ancestor = ancestor.parentElement;
        }
    }
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

    return (
        style.display !== "none" &&
        style.visibility !== "hidden" &&
        rect.width > 0 &&
        rect.height > 0
    );
}

function findForecastTooltip() {
    const candidates = document.querySelectorAll("body *");

    for (const element of candidates) {
        if (!isVisible(element)) {
            continue;
        }

        const text = element.textContent || "";

        if (
            !text.includes("Actual Revenue") ||
            !/\b20\d{2}\b/.test(text)
        ) {
            continue;
        }

        const key = monthKeyFromText(text);

        if (!key) {
            continue;
        }

        const rect = element.getBoundingClientRect();

        // Avoid selecting large dashboard or chart containers.
        if (rect.width > 500 || rect.height > 250) {
            continue;
        }

        return { element, key };
    }

    return null;
}

function formatAov(value) {
    const amount = Number(value) || 0;

    if (Math.abs(amount) >= 1000) {
        const compact = Math.floor(Math.abs(amount) / 1000);

        return `${amount < 0 ? "-" : ""}${compact}k`;
    }

    return new Intl.NumberFormat(undefined, {
        maximumFractionDigits: 0,
    }).format(amount);
}

/**
 * Format the product price as a plain number with two decimal places.
 * No currency symbol is displayed in the Mode Product row.
 */
function formatModeProductPrice(value) {
    const amount = Number(value);

    if (!Number.isFinite(amount)) {
        return "";
    }

    return amount.toFixed(2);
}

/**
 * Find the native color marker next to the Actual Revenue label.
 */
function findNativeMarker(labelEl) {
    if (!labelEl || !labelEl.parentElement) {
        return null;
    }

    const isMarkerCandidate = (el) =>
        el.nodeType === 1 &&
        el !== labelEl &&
        (el.textContent || "").trim() === "";

    const row = labelEl.parentElement;

    let marker = Array.from(row.children).find(isMarkerCandidate);

    if (marker) {
        return marker;
    }

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

/**
 * Check whether an element paints a visible color.
 */
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
 * Find the smallest painted element inside the native marker container.
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

/**
 * Recolor the cloned marker without changing its size or shape.
 */
function recolorMarkerClone(clone, color) {
    clone.style.setProperty("background", color, "important");
    clone.style.setProperty("border-color", color, "important");
    clone.style.setProperty("color", color, "important");

    if (clone.hasAttribute("fill")) {
        clone.setAttribute("fill", color);
    }

    clone.querySelectorAll("[fill]").forEach((node) => {
        node.setAttribute("fill", color);
    });

    return clone;
}

/**
 * Clone the native Actual Revenue marker and apply the requested color.
 */
function buildAovMarker(actualLabelEl, color = AOV_COLOR) {
    const container = findNativeMarker(actualLabelEl);

    const target = container
        ? (findColoredLeaf(container) || container)
        : null;

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
 * Create a tooltip row using the native marker style.
 */
function buildInjectedRow(
    rowClass,
    labelText,
    valueText,
    anchorLabelEl,
    markerColor = AOV_COLOR
) {
    const row = document.createElement("div");

    row.className = `o_forecast_aov_row ${rowClass}`;

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

/**
 * Inject AOV, Mode Product, Frequency, and Standard Deviation
 * into the native monthly revenue tooltip.
 */
function injectAov(tooltip, key) {
    if (
        !tooltip ||
        !key ||
        tooltip.element.querySelector(".o_forecast_aov_row")
    ) {
        return;
    }

    const actualText = Array.from(
        tooltip.element.querySelectorAll("div, span")
    ).find(
        (node) => (node.textContent || "").trim() === "Actual Revenue"
    );

    let lastInserted = actualText
        ? actualText.parentElement
        : null;

    // Average Order Value
    const aovValue = aovByMonth[key];

    if (aovValue !== undefined && aovValue !== null) {
        const row = buildInjectedRow(
            "o_forecast_aov_row_aov",
            "Average Order Value",
            formatAov(aovValue),
            actualText,
            AOV_COLOR
        );

        if (lastInserted) {
            lastInserted.insertAdjacentElement("afterend", row);
        } else {
            tooltip.element.appendChild(row);
        }

        lastInserted = row;
    }

    // Mode Product
    // Desired output:
    // Mode : Product          1927.86 : USB Keyboard
    const modeProduct = modeProductByMonth[key];
    const modeProductPrice = modeProductPriceByMonth[key];

    if (
        modeProduct !== undefined &&
        modeProduct !== null &&
        modeProduct !== ""
    ) {
        let productAndPrice;

        if (
            modeProductPrice !== undefined &&
            modeProductPrice !== null &&
            Number.isFinite(Number(modeProductPrice))
        ) {
            productAndPrice =
                `${formatModeProductPrice(modeProductPrice)} : ${modeProduct}`;
        } else {
            productAndPrice = String(modeProduct);
        }

        const row = buildInjectedRow(
            "o_forecast_aov_row_mode_product",
            "Mode : Product",
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

    // Frequency
    const modeFrequency = modeFrequencyByMonth[key];

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

    // Standard Deviation
    const monthlyStandardDeviation = standardDeviationByMonth[key];

    if (
        monthlyStandardDeviation !== undefined &&
        monthlyStandardDeviation !== null
    ) {
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
    expandMlTooltipLabels();

    const tooltip = findForecastTooltip();

    if (!tooltip) {
        return;
    }

    await loadAovData();

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

    document.addEventListener(
        "mousemove",
        () => {
            updateTooltip();
        },
        { passive: true }
    );
}

if (document.readyState === "loading") {
    document.addEventListener(
        "DOMContentLoaded",
        startObserver,
        { once: true }
    );
} else {
    startObserver();
}
