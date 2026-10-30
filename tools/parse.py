"""Parse a Sindh Code codified PDF (English, Word-made, text layer) into units.

    python -X utf8 parse.py <file.pdf>      # print the units (for inspection)

Layout rules (from the Law Department's codified PDFs, 2026-10-30):
- The body column is where most body-size text sits; its right edge is the most common right end of body lines.
  Marginal notes (the section headings) are printed to the right of it: they become the heading line of the section
  they stand beside, and are left out of the text.
- The running head (the Act's title and number at the top of every page), the page number, and the verification
  stamp ("SCAN TO VERIFY", "LAW DEPARTMENT", "GOVERNMENT OF SINDH", "www.sindhlaws.gov.pk") are left out, except that
  the head is kept on the page where the Act's own text begins.
- Footnotes (small type under the last body line, each starting with its number) are returned separately; the small
  footnote numbers in the body are dropped. Brackets marking amended words stay as printed.
- The contents pages are left out. A section starts at the left column with "N." (N in sequence); headings centred
  between sections (chapters, parts) go above the next section; schedules start at a SCHEDULE heading.
"""
import re
import sys
import warnings
from collections import Counter

warnings.filterwarnings('ignore')
import pymupdf  # noqa: E402

STAMP = {'SCAN TO VERIFY', 'LAW DEPARTMENT', 'GOVERNMENT OF SINDH', 'www.sindhlaws.gov.pk'}
SEC = re.compile(r'^[\["]{0,2}\s*(\d{1,3})\s*(?:-?\s*([A-Z]{1,2}))?\s*\.(?:\s+|$|(?=[\[(A-Z"]))')
SCHED = re.compile(r'^\[?\s*(THE\s+)?((FIRST|SECOND|THIRD|FOURTH|FIFTH|SIXTH|SEVENTH|EIGHTH|NINTH|TENTH)\s+)?'
                   r'(SCHEDULE|ANNEXURE|APPENDIX)\b', re.I)
CONTENTSLIKE = re.compile(r'^(CONTENTS|C O N T E N T S|SECTIONS?|PREAMBLE|\d{1,3}\s*-?\s*[A-Z]{0,2}\s*\.(\s|$))', re.I)


def norm(s):
    s = s.replace('\xa0', ' ').replace('­', '').replace('﻿', '')
    s = s.replace('’', "'").replace('‘', "'").replace('“', '"').replace('”', '"')
    s = s.replace('―', '"').replace('‖', '"')  # quote marks typed in a symbol font: printed as quotes
    s = s.replace('–', '-').replace('—', '-').replace('−', '-')
    return re.sub(r'\s+', ' ', s).strip()


def key(s):
    return re.sub(r'[^A-Za-z0-9]', '', s).upper()


def lines_of(doc):
    sizes = Counter()
    pages = []
    for page in doc:
        ls = []
        for b in page.get_text('dict')['blocks']:
            if b.get('type') != 0:
                continue
            for ln in b['lines']:
                sp = [s for s in ln['spans'] if s['text'].strip()]
                if not sp:
                    continue
                for s in sp:
                    sizes[round(s['size'])] += len(s['text'].strip())
                ls.append((ln['bbox'], ln['spans']))
        pages.append((page.rect, ls))
    body = sizes.most_common(1)[0][0] if sizes else 12
    return pages, body


def text_of(spans, body, drop_markers=True):
    txt = ''
    prev = None
    for s in spans:
        t = s['text']
        if not t:
            continue
        if drop_markers and s['size'] < body * 0.75 and re.fullmatch(r'\s*\d{1,3}\s*', t):
            continue  # a footnote number
        if prev is not None and txt and not txt.endswith(' ') and not t.startswith(' ') \
                and s['bbox'][0] - prev['bbox'][2] > 0.15 * s['size']:
            txt += ' '
        txt += t
        prev = s
    return norm(txt)


def rows_of(doc):
    """Rows of every page: dicts with page, kind (body/margin/foot/head/stamp/pageno), x0, x1, y0, y1, text."""
    pages, body = lines_of(doc)
    n = len(pages)
    # running heads: lines in the top 15% of the page whose letters recur on a third of the pages (at least 2)
    top_keys = Counter()
    for rect, ls in pages:
        seen = set()
        for bb, sp in ls:
            if bb[1] < 0.2 * rect.height:
                k = key(text_of(sp, body))
                if k and k not in seen:
                    seen.add(k)
                    top_keys[k] += 1
    heads = {k for k, c in top_keys.items() if c >= max(2, n / 3) and not k.isdigit()}
    # a running head stands above the page's own text: a recurring word lower down ("The", "of" at the start of a
    # wrapped line or a marginal note) is not one. Per page, the first line that is not a head candidate (nor a page
    # number) bounds the heads.
    head_floor = []
    for rect, ls in pages:
        ys = [bb[1] for bb, sp in ls if (lambda k: k not in heads and not k.isdigit() and k)(key(text_of(sp, body)))]
        head_floor.append(min(ys) if ys else rect.height)
    # body column right edge: the most common right end of long body-size lines
    ends = Counter()
    lefts = Counter()
    for rect, ls in pages:
        for bb, sp in ls:
            if abs(max(s['size'] for s in sp) - body) <= 0.6 and bb[2] - bb[0] > 0.4 * rect.width:
                ends[round(bb[2])] += 1
                lefts[round(bb[0])] += 1
    cx1 = max((e for e, c in ends.items() if c >= max(3, 0.1 * sum(ends.values()))), default=None)
    cx0 = min((e for e, c in lefts.items() if c >= 3), default=72)
    out = []
    page_items = []
    for pi, (rect, ls) in enumerate(pages):
        H, W = rect.height, rect.width
        # footnotes: from the first line in the lower half that starts with a small number and is in small type,
        # every line below it in type smaller than the body
        foot_y = None
        for bb, sp in ls:
            sp2 = [s for s in sp if s['text'].strip()]
            if (bb[1] > 0.5 * H and sp2 and sp2[0]['size'] < body * 0.75 and re.fullmatch(r'\s*(\d{1,3}|\*+)\s*', sp2[0]['text'])
                    and len(sp2) > 1 and max(s['size'] for s in sp2) <= body - 1):
                foot_y = bb[1] if foot_y is None else min(foot_y, bb[1])
            # the footnote number as a line of its own, with the footnote's small-type text beside it on the same row
            elif (bb[1] > 0.5 * H and len(sp2) == 1 and sp2[0]['size'] < body * 0.75
                    and re.fullmatch(r'\s*(\d{1,3}|\*+)\s*', sp2[0]['text'])
                    and any(abs(b2[1] - bb[1]) < 4 and b2[0] >= bb[2] - 1 and b2[0] - bb[2] < 60
                            and max(s['size'] for s in s2 if s['text'].strip()) <= body - 1
                            and not re.fullmatch(r'\s*\d{1,3}\s*', ''.join(s['text'] for s in s2))
                            for b2, s2 in ls if any(s['text'].strip() for s in s2))):
                foot_y = bb[1] if foot_y is None else min(foot_y, bb[1])
        items = []
        for n_, (bb, sp) in enumerate(ls):
            x0, y0, x1, y1 = bb
            mx = max(s['size'] for s in sp if s['text'].strip())
            small = sum(len(s['text'].strip()) for s in sp if s['text'].strip() and s['size'] <= body - 1)
            whole = sum(len(s['text'].strip()) for s in sp if s['text'].strip())
            # a footnote line: in small type, or mostly small type after a small footnote number (a few words in a
            # footnote can be set at body size)
            isfoot = foot_y is not None and y0 >= foot_y - 1 and (
                mx <= body - 1 or (small >= 0.7 * whole and re.match(r'\s*\d{1,3}\s*$', sp[0]['text'])
                                   and sp[0]['size'] < body * 0.75))
            t = text_of(sp, body, drop_markers=not isfoot)
            if not t:
                continue
            if t in STAMP and x1 < cx0:
                kind = 'stamp'
            elif isfoot:
                kind = 'foot'
            elif y0 < 0.2 * H and key(t) in heads and y0 < head_floor[pi]:
                kind = 'head'
            elif (y0 < 0.1 * H or y1 > 0.92 * H) and re.fullmatch(r'[-\s]*\d{1,4}[-\s]*', t):
                kind = 'pageno'
            elif cx1 and x0 >= cx1 - 2 and not re.fullmatch(r'\[[^\]]*\d{4}\s*\]\.?', t):
                kind = 'margin'
            elif cx0 and x1 <= cx0 + 2 and not SEC.match(t):
                kind = 'margin'
            else:
                kind = 'body'
            items.append({'page': pi, 'kind': kind, 'n': n_, 'x0': x0, 'x1': x1, 'y0': y0, 'y1': y1, 'text': t,
                          'size': mx, 'bold': any('Bold' in s['font'] or ',B' in s['font'] for s in sp if s['text'].strip())})
        page_items.append((pi, W, items))
    # designation cells, document-wide: a designation column holds at least two cells at one x position
    cand = {pi: designations(items, W, body, cx1 or W) for pi, W, items in page_items}
    allc = [i for c in cand.values() for i in c.values()]
    for pi, W, items in page_items:
        desig = {k: i for k, i in cand[pi].items() if sum(abs(j['x0'] - i['x0']) < 4 for j in allc) >= 2}
        # group body items into rows by vertical centre
        bi = sorted([i for i in items if i['kind'] == 'body' and id(i) not in desig],
                    key=lambda i: ((i['y0'] + i['y1']) / 2, i['x0']))
        rows = []
        for it in bi:
            yc = (it['y0'] + it['y1']) / 2
            if rows and abs(yc - rows[-1]['yc']) < 0.45 * body:
                rows[-1]['items'].append(it)
            else:
                rows.append({'yc': yc, 'items': [it]})
        place_designations(rows, desig, items, body)
        for r in rows:
            its = sorted(r['items'], key=lambda i: i['x0'])
            out.append({'page': pi, 'kind': 'body', 'x0': its[0]['x0'], 'x1': max(i['x1'] for i in its),
                        'y0': min(i['y0'] for i in its), 'y1': max(i['y1'] for i in its),
                        'text': norm(''.join(d + ' ' for _, d in sorted(r.get('before', []))) +
                                     ' '.join(i['text'] for i in its) + ''.join(' ' + d for _, d in sorted(r.get('after', [])))),
                        'bold': its[0]['bold'], 'W': W, 'cx0': cx0, 'cx1': cx1 or W,
                        'parts': its + r.get('dits', [])})
        for i in items:
            if i['kind'] != 'body':
                out.append({**i, 'W': W, 'cx0': cx0, 'cx1': cx1 or W})
    out.sort(key=lambda r: (r['page'], r['kind'] != 'head', r['y0'] if r['kind'] in ('body', 'head') else 1e9, r['x0']))
    return out, body


DESIG_WORD = re.compile(r'^(Vice|Co|Ex|Officio|Chair(man|person)?|Members?|Secretary|Convener|Convenor|President|'
                        r'cum|Treasurer)$', re.I)


def designations(items, W, body, cx1):
    """Designation cells of a membership table ("Chairman", "Member", "Member/ Secretary", "Vice-Chairperson"): body
    items in the right half made only of designation words, with left-hand text on the same row. Returns
    {id(item): item}."""
    out = {}
    for i in items:
        if i['kind'] != 'body' or i['x0'] < 0.5 * W:
            continue
        words = [w for w in re.split(r'[\s/\-,.;:]+', i['text']) if w]
        if not words or len(words) > 4 or not all(DESIG_WORD.match(w) for w in words):
            continue
        same = [j for j in items if j is not i and j['kind'] == 'body' and j['y0'] < i['y1'] - 2 and j['y1'] > i['y0'] + 2]
        # the right-most item of its row, ending well short of the body column's right edge (a justified line's last
        # word ends at that edge)
        if any(j['x0'] > i['x0'] for j in same):
            continue
        if not any(j['x1'] < i['x0'] - 5 for j in same):
            # a second line of a designation ("Member/" then "Secretary") has left text too; anything else is not one
            continue
        out[id(i)] = i
    # a designation column: at least two cells start at the same place on the page
    return out


def place_designations(rows, desig, items, body):
    """Each designation cell goes after the last line of the left cell it stands beside, which is the order pdftotext
    prints them in (left cell, then right cell). The left cell runs from the row the designation starts on down
    through the rows indented under it, until a row starting with a label ("(b)"), a row beside the next designation,
    or a gap of more than half a line. A designation of two lines ("Member/" "Secretary") is one cell."""
    if not desig:
        return
    ds = sorted(desig.values(), key=lambda d: (d['y0'], d['x0']))
    cells = []
    for d in ds:
        if cells and abs(d['x0'] - cells[-1][-1]['x0']) < 6 and 0 <= d['y0'] - cells[-1][-1]['y1'] < 0.6 * body                 and not starts_row(rows, d):
            cells[-1].append(d)
        else:
            cells.append([d])
    starts = [min(range(len(rows)), key=lambda k: abs(rows[k]['yc'] - (c[0]['y0'] + c[0]['y1']) / 2)) for c in cells]
    for n, c in enumerate(cells):
        k = starts[n]
        nxt = starts[n + 1] if n + 1 < len(cells) else len(rows)
        k0 = k
        while k + 1 < nxt:
            a, b = rows[k], rows[k + 1]
            ay1 = max(i['y1'] for i in a['items'])
            by0 = min(i['y0'] for i in b['items'])
            b0 = min(b['items'], key=lambda i: i['x0'])
            a0 = min(rows[starts[n]]['items'], key=lambda i: i['x0'])
            if by0 - ay1 > 0.5 * body or re.match(r'^\(?[a-z0-9ivx]{1,4}\)', b0['text']) or b0['x0'] < a0['x0'] - 3:
                break
            k += 1
        # in the left cell's rows (k0..k), after the last one drawn before the designation in the page's content
        # stream: the order pdftotext -raw reads them in (some PDFs draw the cell first, some row by row)
        # (rows below the cell drawn before it count too: then pdftotext reads the designation after them)
        dn = c[0]['n']
        best = max(((i['n'], j) for j in range(k0, len(rows)) for i in rows[j]['items'] if i['n'] < dn), default=None)
        if best:
            rows[best[1]].setdefault('after', []).append((dn, ' '.join(d['text'] for d in c)))
        else:
            rows[k0].setdefault('before', []).append((dn, ' '.join(d['text'] for d in c)))
        rows[best[1] if best else k0].setdefault('dits', []).extend(c)


def starts_row(rows, d):
    """True when designation item d is the first designation beside a labelled row ("(c) ...")."""
    yc = (d['y0'] + d['y1']) / 2
    for r in rows:
        if abs(r['yc'] - yc) < 0.45 * 12:
            first = min(r['items'], key=lambda i: i['x0'])
            return bool(re.match(r'^\(?[a-z0-9ivx]{1,4}\)', first['text']))
    return False


def parse(path):
    doc = pymupdf.open(str(path))
    rows, body = rows_of(doc)
    B = [r for r in rows if r['kind'] == 'body']
    # section 1 proper: "1." followed within 300 characters by the short-title words
    start = None
    for k, r in enumerate(B):
        m = SEC.match(r['text'])
        if m and m.group(1) == '1' and not m.group(2):
            nxt = ' '.join(x['text'] for x in B[k:k + 4])[:400]
            if re.search(r'may be (called|cited)|shall be (called|cited)|This (Act|Ordinance)', nxt, re.I):
                start = k
                break
    if start is None:
        raise ValueError('no section 1 found')
    # the title block: after the last contents-like row before section 1
    cut = 0
    for k in range(start):
        if CONTENTSLIKE.match(B[k]['text']) or SCHED.match(B[k]['text']):
            cut = k + 1
    first_page = B[cut]['page'] if cut < len(B) else B[start]['page']
    head_rows = [r for r in rows if r['kind'] == 'head' and r['page'] == first_page]
    title = [r['text'] for r in head_rows] + [r['text'] for r in B[cut:start]]
    units = []
    cur = None
    buf = []
    prev_num = 0
    in_sched = False
    n_sched = 0
    seen = Counter()
    margins = [r for r in rows if r['kind'] == 'margin']

    def heading_for(r, nxt):
        ms = [m['text'] for m in sorted(margins, key=lambda m: (round(m['y0'] / 5), m['x0'])) if m['page'] == r['page'] and r['y0'] - 3 <= m['y0']
              and (nxt is None or nxt['page'] != r['page'] or m['y0'] < nxt['y0'] - 1)]
        return re.sub(r'(\w)- ([a-z])', r'\1\2', norm(' '.join(ms)))

    starts = []
    for k in range(start, len(B)):
        r = B[k]
        t = r['text']
        if (SCHED.match(t) and k > start and len(t) < 90 and not re.search(r'\bto this\b|;$', t)
                and (re.match(r'^\W{0,2}(THE\s+)?([A-Z]+\s+)?(SCHEDULE|ANNEXURE|APPENDIX)', t) or (r['bold'] and len(t) < 40))):
            in_sched = True
            n_sched += 1
            starts.append((k, 'sched', str(n_sched)))
            continue
        if in_sched:
            continue
        m = SEC.match(t)
        if m and r['x0'] <= r['cx0'] + 45:
            num = int(m.group(1))
            suf = (m.group(2) or '')
            if (num == prev_num + 1 and not suf) or (suf and num == prev_num) or (prev_num < num <= prev_num + 3) \
                    or (k == start):
                if k == start or num != prev_num or suf:
                    starts.append((k, 'sec', f'{num:03d}' + (f'-{suf.lower()}' if suf else '')))
                    prev_num = num
    # assemble
    bounds = starts + [(len(B), None, None)]
    # headings centred above a section belong to it: move trailing centred rows of the previous unit
    def centred(r):
        mid = (r['cx0'] + r['cx1']) / 2
        return (abs((r['x0'] + r['x1']) / 2 - mid) < 20 and r['x0'] > r['cx0'] + 25 and r['x1'] < r['cx1'] - 25
                and (r['bold'] or re.sub(r'[^A-Za-z]', '', r['text']).isupper()))

    pending = []
    for idx in range(len(starts)):
        k0, kind, num = starts[idx]
        k1 = bounds[idx + 1][0]
        seg = B[k0:k1]
        tail = []
        if idx + 1 < len(starts) and starts[idx + 1][1] == 'sec':
            while seg and centred(seg[-1]) and not SEC.match(seg[-1]['text']):
                tail.insert(0, seg.pop())
        nxt = B[k1] if k1 < len(B) else None
        uid = ('sec-' if kind == 'sec' else 'sched-') + (num if kind == 'sec' else f'{int(num):02d}')
        seen[uid] += 1
        if seen[uid] > 1:
            uid += f'-{seen[uid]}'
        label = (f'Section {num.lstrip("0").replace("-", "")}' if kind == 'sec' else f'Schedule {num}')
        head = heading_for(seg[0], nxt) if kind == 'sec' and seg else ''
        if kind == 'sched' and SCHEDULE_STREAM:
            seg = stream_rows(seg)
        lines = [p['text'] for p in pending] + paragraphs(seg)
        units.append({'key': uid, 'label': label, 'kind': 'section' if kind == 'sec' else 'schedule',
                      'heading': head, 'lines': lines})
        pending = tail
    # the centred rows directly above section 1 (chapter heading) go with it rather than the title
    feet = []
    fr = sorted((r for r in rows if r['kind'] == 'foot'), key=lambda r: (r['page'], round(r['y0']), r['x0']))
    for q, r in enumerate(fr):
        if (feet and re.fullmatch(r'(\d{1,3}|\*+)', feet[-1]) and q and fr[q - 1]['page'] == r['page']
                and abs(fr[q - 1]['y0'] - r['y0']) < 4):
            feet[-1] = feet[-1] + ' ' + r['text']   # a footnote number printed as its own line, then its text
        else:
            feet.append(r['text'])
    aside = [r['text'] for r in rows if r['kind'] in ('margin', 'foot', 'head', 'stamp', 'pageno')]
    # margin pieces printed on one line (word by word), and each section's whole marginal note
    band = {}
    for m in sorted(margins, key=lambda m: (m['page'], round(m['y0'] / 5), m['x0'])):
        band.setdefault((m['page'], round(m['y0'] / 5), m['x0'] > m['cx1'] - 2), []).append(m['text'])
    aside += [' '.join(v) for v in band.values()] + [u['heading'] for u in units if u['heading']]
    return {'title': title, 'units': units, 'feet': feet, 'aside': aside, 'pages': len(doc), 'body': body}


# Schedules are read in the order the PDF draws their lines (a table cell by cell: each cell's wrapped lines
# together, as the independent pdftotext -raw reading gives them), not row by row across the page.
SCHEDULE_STREAM = True


def stream_rows(seg):
    """The schedule's rows taken apart into the lines the PDF draws, in drawing order page by page (its heading
    row stays first)."""
    if len(seg) < 2:
        return seg
    out = [seg[0]]
    by_page = {}
    for r in seg[1:]:
        for it in r.get('parts') or [r]:
            by_page.setdefault(r['page'], []).append(it)
    for pg in sorted(by_page):
        for it in sorted(by_page[pg], key=lambda i: i.get('n', 0)):
            out.append({**it, 'page': pg, 'W': seg[0]['W'], 'cx0': seg[0]['cx0'], 'cx1': seg[0]['cx1']})
    return out


def paragraphs(seg):
    """Join rows into paragraphs: a new one after a row that ends short of the column, on a row starting with a label
    ("(a)", "(1)", "2."), or on a row indented past the row before (unless that row began with a section number)."""
    out = []
    prev = None
    for r in seg:
        t = r['text']
        new = prev is None
        if prev is not None:
            first = t.split(' ', 1)[0]
            short = prev['x1'] + 0.5 * 12 * len(first) + 6 < prev['cx1']
            LAB = r'^\[?(\(\w{1,5}\)|\d{1,3}\s*-?[A-Z]{0,2}\.\s|[ivx]+\))'
            indented = r['x0'] > prev['x0'] + 12 and not SEC.match(prev['text']) and not re.match(LAB, prev['text'])
            label = re.match(LAB, t)
            new = short or indented or bool(label)
        if new or not out:
            out.append(t)
        else:
            out[-1] = out[-1] + ' ' + t
        prev = r
    return out


if __name__ == '__main__':
    r = parse(sys.argv[1])
    print('== TITLE'); print('\n'.join(r['title']))
    for u in r['units']:
        print('==', u['key'], '|', u['heading']); print('\n'.join(u['lines']))
    print('== FEET'); print('\n'.join(r['feet']))
