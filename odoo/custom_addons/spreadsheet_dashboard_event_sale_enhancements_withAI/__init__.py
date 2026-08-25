from . import models


def _restore_standard_events_dashboard(env):
    """Restore the Odoo Events dashboard JSON stored by the stock addon."""
    import base64
    import os

    from odoo.modules.module import get_module_path

    module_path = get_module_path("spreadsheet_dashboard_event_sale")
    path = os.path.join(
        module_path, "data", "files", "events_dashboard.json"
    ) if module_path else None
    dashboard = env.ref(
        "spreadsheet_dashboard_event_sale.spreadsheet_dashboard_events",
        raise_if_not_found=False,
    )
    if not path or not dashboard or not os.path.isfile(path):
        return

    with open(path, "rb") as dashboard_file:
        dashboard.write({
            "spreadsheet_binary_data": base64.b64encode(
                dashboard_file.read()
            ),
        })


def post_init_hook(env):
    # The previous version of this module persisted its changes directly
    # into spreadsheet.dashboard. Reset that old persisted state once when
    # the corrected module is installed, then use read-time patching only.
    _restore_standard_events_dashboard(env)


def uninstall_hook(env):
    # Guarantee that uninstall leaves the standard Events dashboard behind.
    _restore_standard_events_dashboard(env)
