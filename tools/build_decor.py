"""Build Komnataria Night Bloom from the user's latest unmodified export.

Decorative squares use the same primitive 211 seen in the Acu reference, with
No Touch enabled. Original game objects are retained verbatim. No art or
trigger groups are copied from Acu.
"""
import base64
import gzip
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def unpack(data):
    if isinstance(data, str):
        data = data.encode('ascii')
    return gzip.decompress(base64.urlsafe_b64decode(data + b'=' * (-len(data) % 4)))


def pack(data):
    return base64.urlsafe_b64encode(gzip.compress(data, mtime=0)).decode('ascii')


def fields(row):
    data = row.split(',')
    assert len(data) % 2 == 0
    return dict(zip(data[::2], data[1::2]))


def read(path):
    xml = unpack(path.read_bytes()).decode()
    nodes = list(ET.fromstring(xml).find('dict'))
    meta = {nodes[i].text: nodes[i+1].text for i in range(0, len(nodes), 2)}
    data = unpack(meta['k4']).decode().split(';')
    return xml, meta, data[0], [s for s in data[1:] if s]


# Each section changes both the structure palette and surrounding atmosphere.
# Transitions are positional, not claimed to be synchronised with the song.
PALETTES = [
    (0,     (25, 18, 40), (77, 53, 106), (241, 133, 163), (130, 215, 204)),
    (3195,  (21, 25, 48), (57, 77, 121), (161, 160, 245), (132, 219, 223)),
    (7455,  (18, 35, 44), (48, 92, 108), (129, 221, 202), (241, 188, 141)),
    (10200, (39, 23, 43), (108, 58, 98), (243, 149, 164), (180, 162, 235)),
    (13755, (28, 21, 49), (80, 59, 130), (184, 155, 243), (142, 208, 225)),
    (18600, (41, 23, 38), (121, 63, 91), (249, 169, 145), (206, 164, 229)),
]


def mix(a, b, factor):
    return tuple(round(x*(1-factor)+y*factor) for x, y in zip(a, b))


def colors(section):
    _, bg, face, warm, cool = section
    return {1000: bg, 1001: mix(bg, face, .3), 1009: mix(bg, face, .2),
            801: face, 802: mix(bg, face, .3), 803: mix(face, warm, .42),
            804: warm, 805: cool, 806: mix(bg, face, .18),
            807: mix(bg, face, .4), 808: mix(bg, face, .65), 809: mix(warm, (255,255,255), .4)}


xml, meta, header, original = read(ROOT / 'levels/komnataria-original.gdlvl')
objects = [fields(row) for row in original]
header_parts = header.split(',')
channel_index = header_parts.index('kS38') + 1
channels = [c for c in header_parts[channel_index].split('|') if c]
used = set()
for o in objects:
    used.update(o.get(k) for k in ('21', '22', '23', '50'))
    if o.get('1') == '1006':
        used.add(o.get('51'))
for c in channels:
    pairs = c.split('_'); d = dict(zip(pairs[::2], pairs[1::2])); used.add(d.get('6'))
assert not ({str(i) for i in range(801, 810)} & used)
initial = colors(PALETTES[0])
new_channels = []
for c in channels:
    pairs = c.split('_'); d = dict(zip(pairs[::2], pairs[1::2]))
    channel = int(d['6'])
    if channel in initial:
        for key, val in zip(('1','2','3'), initial[channel]):
            d[key] = str(val)
        c = '_'.join(v for pair in d.items() for v in pair)
    new_channels.append(c)
for channel in range(801, 810):
    r,g,b = initial[channel]
    new_channels.append(f'1_{r}_2_{g}_3_{b}_4_-1_6_{channel}_7_1_15_1_18_0_8_1')
header_parts[channel_index] = '|'.join(new_channels) + '|'
added = []
category_counts = {}


def add(props, category):
    props['20'] = '20'  # editor layer for new decoration
    props['64'] = '1'
    props['67'] = '1'
    category_counts[category] = category_counts.get(category, 0)+1
    added.append(','.join(str(v) for pair in props.items() for v in pair))


def rect(x, y, w, h, channel, z=5, order=20, angle=0, groups='', category='block_details'):
    props = {'1':211, '2':round(x,4), '3':round(y,4), '21':channel,
             '24':z, '25':order, '128':round(w/30,5), '129':round(h/30,5),
             '121':1, '96':1}
    if angle:
        props['6'] = angle
    if groups:
        props['57'] = groups
    add(props, category)


# Dress the existing solid blocks. Details remain inside their footprints.
# Decorations inherit movement/alpha groups so moving or hidden blocks match.
for o in objects:
    if o.get('1') != '1' or '131' in o or '132' in o:
        continue
    x, y = float(o['2']), float(o['3'])
    sx = float(o.get('128', o.get('32', 1)))
    sy = float(o.get('129', o.get('32', 1)))
    angle = float(o.get('6',0))
    groups = o.get('57','')
    def local(dx, dy, w, h, ch, order):
        # GD rotation uses clockwise degrees.
        a = math.radians(-angle)
        dx *= sx; dy *= sy
        tx = x + dx*math.cos(a)-dy*math.sin(a)
        ty = y + dx*math.sin(a)+dy*math.cos(a)
        rect(tx,ty,w*sx,h*sy,ch,order=order,angle=angle,groups=groups)
    local(0,0,25,25,801,20)
    local(0,-9.5,25,5,802,21)
    local(-10,0,3,25,803,22)
    # Small restrained inlays, placed on a repeating diagonal pattern.
    tile_x, tile_y = round(x/30), round(y/30)
    if (tile_x + tile_y) % 4 == 0:
        local(4,6,8,2,805,23)
        local(7,3,2,4,805,23)

# Edge light accents follow actual exposed block runs, rather than wallpaper.
blocks = [o for o in objects if o.get('1') == '1' and not o.get('57')
          and float(o.get('6',0)) % 360 == 0 and '128' not in o and '32' not in o]
positions = {(round(float(o['2']),2), round(float(o['3']),2)) for o in blocks}
for x,y in sorted(positions):
    if (x,y+30) not in positions:
        rect(x,y+11.5,24,1.5,804,order=25,category='edge_lights')

# Inset details reuse each original silhouette, so slopes and spikes keep
# their readable outer boundary. Only static shape IDs are eligible.
for o in objects:
    if o.get('1') not in ('8','83','1743','1744','468','5','502','188'):
        continue
    inset = dict(o)
    inset['121'] = '1'
    inset['24'] = '5'
    inset['25'] = '19'
    inset['96'] = '1'
    inset['21'] = '803' if o['1'] == '8' else '801'
    inset['22'] = inset['21']
    factor = .55 if o['1'] == '8' else .72
    inset['128'] = str(round(float(o.get('128',o.get('32',1))) * factor,5))
    inset['129'] = str(round(float(o.get('129',o.get('32',1))) * factor,5))
    inset.pop('32',None)
    for key in ('41','42','43','44','108'):
        inset.pop(key,None)
    add(inset, 'silhouette_inlays')

# Sparse backdrop islands placed in relation to large gameplay structures.
# Broad soft silhouettes stay behind obstacles; no foreground flashing.
for n,x in enumerate(range(600, 22600, 900)):
    y = 350 + (n%3)*18
    width = 180 + (n%4)*35
    rect(x,y,width,65,806,z=-3,order=-10,category='background')
    rect(x+35,y-10,width*.65,55,807,z=-3,order=-9,category='background')
    rect(x-60,y+35,55,28,808,z=-3,order=-8,category='background')
    # An asymmetrical suspended accent with generous empty space.
    rect(x-65,y+60,23,23,807,z=-3,order=-7,angle=45,category='background')
    rect(x-65,y+60,16,16,806,z=-3,order=-6,angle=45,category='background')
    rect(x+35,y-37,width*.65,2,808,z=-3,order=-5,category='background')

# Intro and exit marks only; no repeated captions across the challenge.
for x,y,title in [(150,330,'KOMNATARIA'), (22830,385,'NIGHT BLOOM')]:
    add({'1':914, '2':x, '3':y, '31':base64.urlsafe_b64encode(title.encode()).decode(),
         '32':.45, '21':809, '24':-1, '25':10, '121':1}, 'titles')

for section in PALETTES[1:]:
    for channel,(r,g,b) in colors(section).items():
        add({'1':899, '2':section[0], '3':-120-(channel%12)*15,
             '23':channel, '7':r, '8':g, '9':b, '10':1.2, '35':1}, 'color_transitions')
    # A single gentle accent pulse after each palette transition.
    _, _, _, warm, _ = section
    r,g,b = mix(warm, (255,255,255), .12)
    add({'1':1006, '2':section[0]+420, '3':-180, '51':804, '52':0,
         '48':0, '45':.25, '46':.05, '47':.8, '7':r, '8':g, '9':b}, 'accent_pulses')

level = ','.join(header_parts) + ';' + ';'.join(original+added) + ';'
new_xml = xml.replace(meta['k4'], pack(level.encode()), 1)
new_xml = new_xml.replace('<k>k2</k><s>komnataria</s>', '<k>k2</k><s>komnataria bloom</s>', 1)
out = ROOT / 'levels/komnataria-deco.gdlvl'
out.write_text(pack(new_xml.encode()), encoding='ascii')
# Round-trip validation and exact preservation of all original game objects.
_, _, _, verified = read(out)
assert verified[:len(original)] == original
assert len(verified) == len(original)+len(added)
for row in verified[len(original):]:
    o = fields(row)
    if o['1'] in ('211','914','8','83','1743','1744','468','5','502','188'):
        assert o['121'] == '1'
    else:
        assert o['1'] in ('899','1006')
    assert float(o['2']) <= max(float(o['2']) for o in objects)
report = {'source_records':len(original),'added':len(added),'total_records':len(verified),
          'categories':category_counts,'original_records_preserved':True,
          'decorative_no_touch':True,'validated_in_game':False}
(ROOT/'levels/decor-report.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
