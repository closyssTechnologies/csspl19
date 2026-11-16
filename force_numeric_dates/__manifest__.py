{
    "name": "Force Numeric Dates (Per-User by Language)",
    "version": "19.0.1.2.0",
    "category": "Productivity",
    "summary": "Render all backend dates numerically (e.g. 15/01/2026) "
               "using each user's language date format, instead of the "
               "Odoo 19 default text-month format (e.g. Jan 15, 2026).",
    "author": "Odoo Nerd",
    "website": "https://www.odoo.com",
    "license": "LGPL-3",
    "depends": ["web"],
    "assets": {
        "web.assets_backend": [
            "force_numeric_dates/static/src/force_numeric_dates.js",
            "force_numeric_dates/static/src/force_numeric_dates.scss",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}
