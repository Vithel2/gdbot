"""Build a reversible decoration variant; retain every original object record."""
from pathlib import Path
import base64
import gzip
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def unpack(value):
    if isinstance(value, str):
        value = value.encode('ascii')
    return gzip.decompress(base64.urlsafe_b64decode(value + b'=' * (-len(value) % 4)))


def pack(value):
    return base64.urlsafe_b64encode(gzip.compress(value, mtime=0)).decode('ascii')


def read_level(path):
    xml = unpack(path.read_bytes()).decode('utf8')
    children = list(ET.fromstring(xml).find('dict'))
    values = {children[i].text: children[i+1].text for i in range(0, len(children), 2)}
    return xml, values, unpack(values['k4']).decode('utf8')


xml, values, level = read_level(ROOT / 'levels/komnataria-original.gdlvl')
parts = level.split(';')
original = [s for s in parts[1:] if s]
header = parts[0].split(',')
idx = header.index('kS38') + 1
channels = header[idx].split('|')
# Independent channels, absent from the source. No group references or triggers.
palette = {
    801: (21, 9, 35), 802: (37, 13, 49), 803: (74, 20, 67),
    804: (126, 26, 84), 805: (200, 51, 125), 806: (91, 138, 165),
    807: (46, 17, 56), 808: (29, 11, 43),
}
for entry in channels:
    fields = entry.split('_')
    d = dict(zip(fields[::2], fields[1::2]))
    assert d.get('6') not in {str(x) for x in palette}
for channel, (r, g, b) in palette.items():
    channels.append(f'1_{r}_2_{g}_3_{b}_4_-1_6_{channel}_7_1_15_1_18_0_8_1')
# Dark surrounding air; original ground and object colours are untouched.
for i, entry in enumerate(channels):
    f = entry.split('_')
    if dict(zip(f[::2], f[1::2])).get('6') == '1000':
        for key, value in [('1','39'), ('2','10'), ('3','47')]:
            f[f.index(key)+1] = value
        channels[i] = '_'.join(f)
header[idx] = '|'.join(c for c in channels if c) + '|'
added = []


def panel(x, y, width, height, color, order=0, rotation=0):
    # 581 is already used as scaled decorative fill in the source level.
    # Put new art on B4, behind the original gameplay, and editor layer 20.
    fields = {'1':'581', '2':f'{x:g}', '3':f'{y:g}', '21':str(color),
              '24':'-3', '25':str(order), '20':'20', '155':'20',
              '128':f'{width/30:.4f}', '129':f'{height/30:.4f}',
              '64':'1', '67':'1'}
    if rotation:
        fields['6'] = str(rotation)
    added.append(','.join(v for pair in fields.items() for v in pair))


def label(x, text):
    encoded = base64.urlsafe_b64encode(text.encode()).decode()
    added.append(f'1,914,2,{x},3,390,31,{encoded},21,804,24,-3,25,6,32,0.45,20,20,155,20')


# Architectural bays across the whole level, with three different wall motifs.
for n, x in enumerate(range(180, 22801, 480)):
    panel(x, 225, 438, 390, 801, -10)
    panel(x, 225, 394, 346, 802, -9)
    panel(x, 225, 372, 324, 808, -8)
    for side in (-1, 1):
        panel(x + side*218, 225, 6, 390, 803, -6)
        panel(x + side*206, 225, 2, 340, 804, -5)
        panel(x + side*218, 420, 26, 6, 805, -4)
    for y in (42, 408):
        panel(x, y, 438, 3, 804, -4)
    if n % 3 == 0:
        for dx in (-118, 0, 118):
            panel(x+dx, 235, 86, 220, 807, -7)
            panel(x+dx, 344, 86, 2, 803, -5)
            panel(x+dx, 126, 86, 2, 803, -5)
    elif n % 3 == 1:
        for y in (145, 205, 265, 325):
            panel(x, y, 300, 2, 803, -5)
        panel(x, 235, 2, 270, 803, -5)
    else:
        for dx in (-110, 110):
            panel(x+dx, 245, 92, 92, 803, -6, 45)
            panel(x+dx, 245, 83, 83, 808, -5, 45)
    # Ceiling light fixture, with a muted blue core; no white hazard outlines.
    panel(x, 432, 124, 16, 803, -4)
    panel(x, 432, 108, 8, 804, -3)
    panel(x, 432, 94, 2, 806, -2)
for x, name in [(180,'KOMNATARIA'), (4600,'CHAMBERS'), (9200,'PRESSURE'),
                (13800,'DESCENT'), (18400,'AFTERLIGHT'), (22600,'EXIT')]:
    label(x, name)

new_level = ','.join(header) + ';' + ';'.join(original + added) + ';'
new_xml = xml.replace(values['k4'], pack(new_level.encode()), 1)
new_xml = new_xml.replace('<k>k2</k><s>komnataria</s>', '<k>k2</k><s>komnataria deco</s>', 1)
out = ROOT / 'levels/komnataria-deco.gdlvl'
out.write_text(pack(new_xml.encode()), encoding='ascii')
_, _, verified = read_level(out)
rows = verified.split(';')[1:]
assert rows[:len(original)] == original
assert len([r for r in rows if r]) == len(original)+len(added)
print(f'Original records preserved: {len(original)}; added decor: {len(added)}')
