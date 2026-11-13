/** @odoo-module **/

import { DateTimeField, dateField, dateRangeField } from "@web/views/fields/datetime/datetime_field";
import { registry } from "@web/core/registry";
import { deserializeDate } from "@web/core/l10n/dates";

export class MonthRangeField extends DateTimeField {
    static template = "web.DateTimeField";

    /**
     * Override: format value as "MMM yyyy" (e.g. "Feb 2026")
     */
    getFormattedValue(valueIndex) {
        const values = this.values;
        let value = values[valueIndex];
        if (!value) {
            return "";
        }
        if (typeof value === "string") {
            value = deserializeDate(value);
        }
        if (value && typeof value.toFormat === "function") {
            return value.toFormat("MMM yyyy");
        }
        return String(value);
    }
}

export const monthRangeField = {
    ...dateRangeField,
    component: MonthRangeField,
};

export const monthField = {
    ...dateField,
    component: MonthRangeField,
};

registry.category("fields").add("month_range_field", monthRangeField);
registry.category("fields").add("month_field", monthField);
