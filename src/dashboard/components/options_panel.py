"""Shared options panel component — collapsible accordion for tab-level controls."""

import dash_bootstrap_components as dbc


def create_options_panel(
    panel_id: str,
    title: str,
    children: list,
    always_open: bool = False,
) -> dbc.Accordion:
    """Create a collapsible options panel using dbc.Accordion.

    Parameters
    ----------
    panel_id : str
        Unique ID for the accordion component.
    title : str
        Header text for the accordion item.
    children : list
        Dash components to render inside the panel.
    always_open : bool
        If True, multiple items can be open simultaneously.
    """
    return dbc.Accordion(
        [dbc.AccordionItem(children, title=title, item_id="options")],
        id=panel_id,
        start_collapsed=True,
        flush=True,
        always_open=always_open,
        className="mb-3",
    )
