"""Prototype of the capture design, structure-only output.

Splits each source document into: model rows (one per <model>, nested ones
referenced from their parent by ordinal), file rows (one per taggedFiles/file),
and a skeleton (everything else, with model/file subtrees replaced by refs and
modelType/taggedFiles child lists omitted). Then recounts elements, attributes
and non-whitespace texts from the captured JSON and compares with an
independent source count. Prints sizes and the comparison, never content.
"""
import sys, json, time, resource, zipfile, hashlib, collections as C
import xml.etree.ElementTree as ET

def ln(t): return t.rsplit('}', 1)[-1]
def src(s):
    if '::' in s:
        z, e = s.split('::', 1); return zipfile.ZipFile(z).open(e)
    return open(s, 'rb')

def enc(el, models_ref):
    """generic element: [tag, attrs|None, text|None, children|None]"""
    kids = []
    for c in el:
        r = models_ref.pop(id(c), None)
        if r is not None:
            kids.append(['@', r])
        else:
            kids.append(enc(c, models_ref))
    t = el.text
    if kids and t is not None and not t.strip():
        t = None   # formatting whitespace between child elements
    return [ln(el.tag), dict((ln(k), v) for k, v in el.attrib.items()) or None, t, kids or None]

def count_tree(node, out):
    if node[0] == '@':
        return
    out['elements'] += 1
    out['attributes'] += len(node[1] or {})
    if node[2] is not None and node[2].strip():
        out['texts'] += 1
    for k in node[3] or []:
        count_tree(k, out)

def main(label, specs):
    t0 = time.time()
    rows = 0; row_bytes = 0; file_rows = 0; file_bytes = 0; skel_bytes = 0
    cap = C.Counter(); srcc = C.Counter(); errors = []
    maxrow = 0; dup_ids = 0; dup_field_names = 0
    omitted = C.Counter()
    for spec in specs:
        stack = []      # (element, local name)
        ordinal = 0
        models_ref = {}
        pending = {}    # id(model el) -> ordinal
        seen_ids = set()
        skel_root = None
        try:
            for ev, el in ET.iterparse(src(spec), events=('start', 'end')):
                name = ln(el.tag)
                if ev == 'start':
                    srcc['elements'] += 1; srcc['attributes'] += len(el.attrib)
                    if skel_root is None: skel_root = el
                    if name == 'model':
                        ordinal += 1; pending[id(el)] = ordinal
                        mid = el.get('id')
                        if mid in seen_ids: dup_ids += 1
                        seen_ids.add(mid)
                    stack.append((el, name))
                    continue
                stack.pop()
                if el.text is not None and el.text.strip(): srcc['texts'] += 1
                parent = stack[-1][1] if stack else None
                if name == 'model':
                    o = pending.pop(id(el))
                    names = [c.get('name') for c in el if ln(c.tag) != 'model' and c.get('name')]
                    if len(names) != len(set(names)): dup_field_names += 1
                    row = enc(el, models_ref)
                    b = json.dumps(row, ensure_ascii=False, separators=(',', ':'))
                    rows += 1; row_bytes += len(b.encode()); maxrow = max(maxrow, len(b))
                    count_tree(row, cap)
                    el.clear()
                    models_ref[id(el)] = o
                    if parent == 'modelType':
                        # skeleton omits modelType children; count recorded
                        omitted['modelType/model'] += 1
                elif name == 'file' and parent == 'taggedFiles':
                    row = enc(el, models_ref)
                    b = json.dumps(row, ensure_ascii=False, separators=(',', ':'))
                    file_rows += 1; file_bytes += len(b.encode())
                    count_tree(row, cap)
                    el.clear(); omitted['taggedFiles/file'] += 1
                    models_ref[id(el)] = -1
                elif name == 'modelType' or name == 'taggedFiles':
                    # drop the (already captured) children from memory
                    for c in list(el):
                        models_ref.pop(id(c), None); el.remove(c)
            # skeleton: root with model/file children removed
        except ET.ParseError as e:
            errors.append(str(e)[:40] + ' open=' + '/'.join(n for _, n in stack[-4:]))
            # capture the open subtree(s) as partial: innermost open file or model
            for oel, oname in reversed(stack):
                if oname in ('file', 'model'):
                    row = enc(oel, models_ref); count_tree(row, cap); cap['partial_rows'] += 1
                    # the open element and ancestors up to it were counted once at start
                    break
            # text of still-open elements is not complete; counted as captured above
        if skel_root is not None:
            # remove captured rows from skeleton then encode
            def strip(e):
                for c in list(e):
                    if id(c) in models_ref: models_ref.pop(id(c)); e.remove(c)
                    else: strip(c)
            strip(skel_root)
            sk = enc(skel_root, {})
            # mark partial subtrees already counted to avoid double count
            if errors:
                def drop_partial(node):
                    if node[3]:
                        node[3] = [k for k in node[3] if not (k[0] in ('file', 'model'))] or None
                        for k in node[3] or []: drop_partial(k)
                drop_partial(sk)
            skel_bytes += len(json.dumps(sk, ensure_ascii=False).encode())
            count_tree(sk, cap)
    out = dict(label=label, seconds=round(time.time() - t0, 1),
        peak_rss_mb=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1048576, 1),
        model_rows=rows, model_json_mb=round(row_bytes / 1e6, 1), largest_row_kb=round(maxrow / 1024, 1),
        file_rows=file_rows, file_json_mb=round(file_bytes / 1e6, 1), skeleton_kb=round(skel_bytes / 1024, 1),
        source=dict(srcc), captured={k: cap[k] for k in ('elements', 'attributes', 'texts', 'partial_rows')},
        equal=all(srcc[k] == cap[k] for k in ('elements', 'attributes', 'texts')),
        duplicate_model_ids=dup_ids, models_with_repeated_field_names=dup_field_names, errors=errors)
    print(json.dumps(out))

main(sys.argv[1], sys.argv[2:])
