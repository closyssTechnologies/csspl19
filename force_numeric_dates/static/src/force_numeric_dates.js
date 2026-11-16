/** @odoo-module **/

/*
 * Force Numeric Dates (per-user, by language)
 * -------------------------------------------
 * Odoo 19 defaults date/datetime rendering to a text-month locale format
 * ("Jan 15, 2026"). This module forces numeric output everywhere — using each
 * user's own language date format (localization.dateFormat / dateTimeFormat,
 * derived from res.lang.date_format).
 *
 * Rendering surfaces patched:
 *   1. formatters registry ("date" / "datetime")
 *      -> list cells, search/group-by facets, any consumer using the registry.
 *   2. DateTimeField.defaultProps.numeric = true
 *      -> component-level default so form/kanban views are numeric by default.
 *   3. dateField.extractProps / dateTimeField.extractProps
 *      -> injects numeric:true into options before the stock extractor runs,
 *         so the component prop and placeholder are both formatted correctly.
 *   4. dateField.listViewWidth / dateTimeField.listViewWidth
 *      -> returns the wider numeric_date / numeric_datetime column width so
 *         rendered values are never clipped in list view.
 *      dateRangeField.listViewWidth calls dateField/dateTimeField by reference,
 *      so it benefits from patches (3) and (4) automatically.
 *   5. BankRecStatementLine / BankRecSelectCreateDialog (Bank Reconciliation)
 *      -> patches custom getters bypassing DateTimeField to render numeric date.
 *
 * Opt-out: a field with options="{'numeric': false}" in the view arch will
 * still render in text-month format — explicit false is always respected.
 *
 * Not covered: chatter / activity / mail timestamps — those render through
 * toLocaleDateTimeString() and are intentionally excluded.
 */

import { registry } from "@web/core/registry";
import { DateTimeField, dateField, dateTimeField } from "@web/views/fields/datetime/datetime_field";
import { patch } from "@web/core/utils/patch";
import { formatDate } from "@web/core/l10n/dates";

// ---------------------------------------------------------------------------
// 1) Registry formatters: force numeric output.
//    Delegates to the stock implementation; only injects numeric:true.
//    Preserves show_time / show_date / show_seconds and all other options.
// ---------------------------------------------------------------------------
const formatters = registry.category("formatters");
const _stockDate = formatters.get("date");
const _stockDateTime = formatters.get("datetime");

function numericFormatDate(value, options = {}) {
    return _stockDate(value, { ...options, numeric: true });
}
numericFormatDate.extractOptions = _stockDate.extractOptions;

function numericFormatDateTime(value, options = {}) {
    return _stockDateTime(value, { ...options, numeric: true });
}
numericFormatDateTime.extractOptions = _stockDateTime.extractOptions;

formatters.add("date", numericFormatDate, { force: true });
formatters.add("datetime", numericFormatDateTime, { force: true });

// ---------------------------------------------------------------------------
// 2) Component default props: numeric:true.
//    Spreads over existing defaults to preserve showSeconds, showTime, etc.
//    This ensures getFormattedValue() reads this.props.numeric === true even
//    for components instantiated outside the normal extractProps path.
// ---------------------------------------------------------------------------
DateTimeField.defaultProps = { ...DateTimeField.defaultProps, numeric: true };

// ---------------------------------------------------------------------------
// 3) extractProps: inject numeric:true into arch options before delegating.
//    Uses `options.numeric ?? true` so:
//      - unset (undefined) → true  (our default)
//      - explicit false    → false (view-arch opt-out respected)
//      - explicit true     → true
//    This also corrects the placeholder text shown in empty date inputs.
// ---------------------------------------------------------------------------
const _origDateExtractProps = dateField.extractProps;
dateField.extractProps = ({ options = {}, ...rest }, dynamicInfo) =>
    _origDateExtractProps(
        { options: { ...options, numeric: options.numeric ?? true }, ...rest },
        dynamicInfo
    );

const _origDateTimeExtractProps = dateTimeField.extractProps;
dateTimeField.extractProps = ({ options = {}, ...rest }, dynamicInfo) =>
    _origDateTimeExtractProps(
        { options: { ...options, numeric: options.numeric ?? true }, ...rest },
        dynamicInfo
    );

// ---------------------------------------------------------------------------
// 4) listViewWidth: inject numeric:true so stock logic returns the wider
//    numeric_date / numeric_datetime column widths.
//    dateRangeField.listViewWidth closes over dateField/dateTimeField by name,
//    so it automatically uses these patched versions — no separate patch needed.
// ---------------------------------------------------------------------------
const _origDateLVW = dateField.listViewWidth;
dateField.listViewWidth = ({ options = {}, ...rest }) =>
    _origDateLVW({ options: { ...options, numeric: options.numeric ?? true }, ...rest });

const _origDateTimeLVW = dateTimeField.listViewWidth;
dateTimeField.listViewWidth = ({ options = {}, ...rest }) =>
    _origDateTimeLVW({ options: { ...options, numeric: options.numeric ?? true }, ...rest });

// ---------------------------------------------------------------------------
// 5) Bank Reconciliation widget kanban card: force numeric date.
//    BankRecStatementLine uses custom getters with hardcoded toLocaleString
//    options ({ month: "short", day: "2-digit" }) bypassing standard DateTimeField.
// ---------------------------------------------------------------------------
function patchBankRecStatementLine(statementLineModule) {
    if (!statementLineModule?.BankRecStatementLine) {
        return;
    }
    patch(statementLineModule.BankRecStatementLine.prototype, {
        get formattedDate() {
            return this.recordData.date ? formatDate(this.recordData.date) : "";
        },
        get formattedFullDate() {
            return this.recordData.date ? formatDate(this.recordData.date) : "";
        },
    });
}

function patchBankRecSearchDialog(dialogModule) {
    if (!dialogModule?.BankRecSelectCreateDialog) {
        return;
    }
    patch(dialogModule.BankRecSelectCreateDialog.prototype, {
        get formattedStatementLineDate() {
            return this.props.date ? formatDate(this.props.date) : "";
        },
    });
}

const stLineModName = "@account_accountant/components/bank_reconciliation/statement_line/statement_line";
const searchDialogModName = "@account_accountant/components/bank_reconciliation/search_dialog/search_dialog";

if (globalThis.odoo?.loader?.modules) {
    if (odoo.loader.modules.has(stLineModName)) {
        patchBankRecStatementLine(odoo.loader.modules.get(stLineModName));
    }
    if (odoo.loader.modules.has(searchDialogModName)) {
        patchBankRecSearchDialog(odoo.loader.modules.get(searchDialogModName));
    }

    odoo.loader.bus?.addEventListener("module-started", (e) => {
        if (e.detail.moduleName === stLineModName) {
            patchBankRecStatementLine(e.detail.module);
        } else if (e.detail.moduleName === searchDialogModName) {
            patchBankRecSearchDialog(e.detail.module);
        }
    });
}
