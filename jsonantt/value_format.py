"""Opt-in display formatting; never changes source amounts or allocations."""
from decimal import Decimal, ROUND_HALF_EVEN

SCALES = {'units': (1, ''), 'thousands': (1000, 'K'), 'millions': (1000000, 'M'), 'billions': (1000000000, 'B')}


def value_format_active(style, field):
    if field in {'task', 'id', 'name', 'description', 'start', 'end', 'date', 'effective_start', 'effective_end', 'milestone_date', 'duration', 'not_before', 'offset', 'marker_size'}:
        return False
    fields = style.value_fields
    return (not fields or field in fields) and (
        style.value_prefix is not None or style.value_suffix is not None
        or style.value_scale != 'units' or style.value_decimals is not None)


def validate_value_format(style):
    if style.value_scale not in SCALES:
        raise ValueError('value_scale must be units, thousands, millions, or billions')
    if style.value_decimals is not None and (type(style.value_decimals) is not int or not 0 <= style.value_decimals <= 8):
        raise ValueError('value_decimals must be an integer from 0 to 8')
    if not isinstance(style.value_fields, list) or any(not isinstance(field, str) or not field.strip() for field in style.value_fields):
        raise ValueError('value_fields must be a list of field names')
    for value in (style.value_prefix, style.value_suffix):
        if value is not None and not isinstance(value, str):
            raise ValueError('value_prefix and value_suffix must be strings')


def format_value(amount, style, field, spec=None):
    """Return formatted text, or None to retain the existing renderer format."""
    if not value_format_active(style, field):
        return None
    spec = spec or {}
    divisor, unit = SCALES[style.value_scale]
    places = 2 if style.value_decimals is None else style.value_decimals
    value = (Decimal(str(amount)) / Decimal(divisor)).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_EVEN)
    prefix = style.value_prefix if style.value_prefix is not None else spec.get('prefix', '')
    suffix = style.value_suffix if style.value_suffix is not None else spec.get('suffix', '')
    text = f'{abs(value):,.{places}f}'
    if style.value_decimals is None and '.' in text:
        text = text.rstrip('0').rstrip('.')
    return f'{"-" if value < 0 else ""}{prefix}{text}{unit}{(" " + suffix) if suffix else ""}'


def value_unit_label(style, field, spec=None):
    if not value_format_active(style, field):
        return ''
    spec = spec or {}
    prefix = style.value_prefix if style.value_prefix is not None else spec.get('prefix', '')
    suffix = style.value_suffix if style.value_suffix is not None else spec.get('suffix', '')
    scale = '' if style.value_scale == 'units' else style.value_scale
    return ' '.join(value for value in (prefix, scale, suffix) if value)
