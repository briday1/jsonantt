"""Pair renderer-authored outputs without redrawing their contents."""
import csv
import io
from itertools import zip_longest
import xml.etree.ElementTree as ET


def pair_outputs(planned, actual, fmt, dpi=150, background='white'):
    if fmt == 'csv':
        left = list(csv.reader(io.StringIO(planned.decode('utf-8'))))
        right = list(csv.reader(io.StringIO(actual.decode('utf-8'))))
        left[0] = ['Baseline: '+item for item in left[0]]
        right[0] = ['Current: '+item for item in right[0]]
        output = io.StringIO(newline='')
        writer = csv.writer(output)
        for a, b in zip_longest(left, right):
            writer.writerow((a or [''] * len(left[0])) + (b or [''] * len(right[0])))
        return output.getvalue().encode('utf-8')
    if fmt == 'png':
        from PIL import Image
        from matplotlib.colors import to_rgba
        left, right = (Image.open(io.BytesIO(item)).convert('RGBA') for item in (planned, actual))
        gap = round(dpi / 6)
        output = Image.new('RGBA', (left.width + right.width + gap, max(left.height, right.height)),
                           tuple(round(channel * 255) for channel in to_rgba(background)))
        output.paste(left, (0, 0)); output.paste(right, (left.width + gap, 0))
        buffer = io.BytesIO()
        output.save(buffer, format='PNG', dpi=(dpi, dpi))
        return buffer.getvalue()
    namespace = 'http://www.w3.org/2000/svg'
    ET.register_namespace('', namespace)
    ET.register_namespace('xlink', 'http://www.w3.org/1999/xlink')
    panels = [ET.fromstring(item) for item in (planned, actual)]
    widths, heights = [], []
    for prefix, panel in zip(('baseline-', 'current-'), panels):
        _, _, width, height = map(float, panel.attrib['viewBox'].split())
        widths.append(width); heights.append(height)
        ids = {node.attrib['id']: prefix + node.attrib['id'] for node in panel.iter() if 'id' in node.attrib}
        for node in panel.iter():
            for key, value in list(node.attrib.items()):
                if key == 'id':
                    value = ids[value]
                elif key.endswith('href') and value.startswith('#'):
                    value = '#'+ids.get(value[1:], value[1:])
                elif 'url(#' in value:
                    for old, new in ids.items():
                        value = value.replace(f'url(#{old})', f'url(#{new})')
                node.set(key, value)
        panel.set('width', str(width)); panel.set('height', str(height))
    width, height = sum(widths) + 12, max(heights)
    root = ET.Element(f'{{{namespace}}}svg', {'viewBox': f'0 0 {width} {height}', 'width':f'{width}pt', 'height':f'{height}pt'})
    ET.SubElement(root, f'{{{namespace}}}rect', {'width':'100%', 'height':'100%', 'fill':background})
    panels[0].set('x', '0'); panels[1].set('x', str(widths[0] + 12))
    root.extend(panels)
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)
