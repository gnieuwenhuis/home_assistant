"""Shared helpers for rendering templates in tests."""
from homeassistant.helpers.template import Template


def render(hass, source):
    """Render template source against the test hass; returns native types."""
    return Template(source, hass).async_render()


def jlist(values):
    """Format a Python list of numbers as a Jinja list literal."""
    return "[" + ", ".join(str(v) for v in values) + "]"
