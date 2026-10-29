"""Structure-only element-level counter prototype. Prints counts, never content.

usage: python3 -I measure_counter.py <label> <xml path | zip path::entry> [more sources]
"""
import sys, time, json, hashlib, resource, zipfile, collections as C
import xml.etree.ElementTree as ET

def ln(t):
    return t.rsplit('}', 1)[-1] if isinstance(t, str) else str(t)

def open_src(spec):
    if '::' in spec:
        z, e = spec.split('::', 1)
        return zipfile.ZipFile(z).open(e)
    return open(spec, 'rb')

def run(label, specs):
    t0 = time.time()
    paths = C.Counter()          # qualified path -> element count
    attrs = C.Counter()          # (path, attr) -> count
    texts = C.Counter()          # path -> non-whitespace text count
    textchars = C.Counter()
    vhash = C.Counter()          # path -> sum of 64-bit value hashes mod 2^64
    tails = 0; ws_text = 0; comments = 0; pis = 0
    local = C.Counter(); maxdepth = 0; total_text_bytes = 0
    total_attr = 0; errors = []
    top_models = 0; nested_models = 0; values = 0
    longest = 0
    for spec in specs:
        stack = []
        try:
            with open_src(spec) as fh:
                it = ET.iterparse(fh, events=('start', 'end', 'comment', 'pi'))
                for ev, el in it:
                    if ev == 'start':
                        name = ln(el.tag)
                        q = name
                        if name in ('model', 'modelType'):
                            q = name + '[' + str(el.get('type')) + ']'
                        elif name in ('field', 'multiField', 'modelField', 'multiModelField', 'nodeField', 'dataField', 'item', 'section') or (name == 'metadata' and el.get('section')):
                            q = name + '[' + str(el.get('name') or el.get('section')) + ']'
                        path = (stack[-1] + '/' if stack else '') + q
                        stack.append(path)
                        paths[path] += 1
                        local[name] += 1
                        if len(stack) > maxdepth: maxdepth = len(stack)
                        for a in el.attrib:
                            attrs[(path, ln(a))] += 1
                            total_attr += 1
                        if name == 'model':
                            if 'Field' in stack[-2].rsplit('/', 1)[-1]:
                                nested_models += 1
                            else:
                                top_models += 1
                        if name == 'value':
                            values += 1
                    elif ev == 'end':
                        path = stack.pop()
                        t = el.text
                        if t is not None:
                            if t.strip():
                                texts[path] += 1
                                n = len(t)
                                textchars[path] += n
                                total_text_bytes += len(t.encode('utf-8'))
                                if n > longest: longest = n
                                h = int.from_bytes(hashlib.blake2b(t.encode('utf-8'), digest_size=8).digest(), 'big')
                                vhash[path] = (vhash[path] + h) % (1 << 64)
                            else:
                                ws_text += 1
                        if el.tail is not None and el.tail.strip():
                            tails += 1
                        el.clear()
                        # drop references held by the parent to keep memory flat
                    elif ev == 'comment':
                        comments += 1
                    elif ev == 'pi':
                        pis += 1
        except ET.ParseError as e:
            errors.append(spec.rsplit('/', 1)[-1][-12:] + ': ' + str(e) + ' open=' + '/'.join(p.rsplit('/', 1)[-1] for p in stack[-4:]))
    dt = time.time() - t0
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    out = dict(label=label, seconds=round(dt, 1), peak_rss_mb=round(rss / 1024 / 1024, 1),
        elements=sum(paths.values()), distinct_paths=len(paths), attributes=total_attr,
        distinct_attr_paths=len(attrs), text_nodes=sum(texts.values()), text_bytes=total_text_bytes,
        longest_text_chars=longest, ws_only_text=ws_text, nonws_tails=tails, comments=comments, pis=pis,
        maxdepth=maxdepth, top_models=top_models, nested_models=nested_models, values=values,
        local=dict(local.most_common()), errors=errors,
        digest=hashlib.sha256(json.dumps(sorted((k, v, attrs.get(k), texts.get(k), textchars.get(k), vhash.get(k)) for k, v in paths.items()) , default=str).encode()).hexdigest()[:16])
    print(json.dumps(out))

if __name__ == '__main__':
    run(sys.argv[1], sys.argv[2:])
