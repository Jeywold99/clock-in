from django import template

register = template.Library()


@register.filter
def hm(delta):
    """Format a timedelta as H:MM (e.g. 7:05)."""
    if delta is None:
        return "—"
    total_minutes = int(delta.total_seconds()) // 60
    return f"{total_minutes // 60}:{total_minutes % 60:02d}"


@register.filter
def money(value):
    if value is None:
        return "—"
    return f"{value:,.2f}"
