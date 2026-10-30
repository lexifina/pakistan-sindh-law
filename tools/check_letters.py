"""Independent letters-and-digits check of a part against the source PDFs, read by a second engine (xpdf pdftotext
-raw). Private. Copied from scripts/india-maharashtra-law/check_letters.py (same rules): each Act's units (heading
lines left out) reduced to letters and digits must be found, in order, in the PDF's text reduced the same way; source
text may be passed over only for footnote numbers, a stretch across one page break, or (within a page) lines that
parse.py's layout rules set aside (margin notes, footnotes, running heads, page numbers, the verification stamp).

    python -X utf8 check_letters.py corpus.d/20-acts-01.json [...]
"""
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'world-law'))
FF = ''


def ld(s):
    return ''.join(ch for ch in s if ch.isalnum() or ch == FF)


def source(pdf, mode='-raw'):
    """pdftotext's reading: '-raw' (content-stream order) or '' (its default physical reading order, which reads
    tables row by row)."""
    out = subprocess.run(['pdftotext', *([mode] if mode else []), '-enc', 'UTF-8', str(pdf), '-'],
                         capture_output=True).stdout
    return ld(out.decode('utf-8', 'replace'))


def check_pdf(units, pdf, aside):
    """Passes when the record matches either of pdftotext's two readings of the PDF."""
    ok, msg = check_act(units, source(pdf), aside)
    if ok:
        return ok, 'raw: ' + msg
    ok2, msg2 = check_act(units, source(pdf, ''), aside)
    return (True, 'default order: ' + msg2) if ok2 else (False, msg)


def pat(s):
    return re.compile(r'\d{0,3}'.join(map(re.escape, s)))


def tiled(gap, aside):
    """True when gap is a concatenation of set-aside lines and runs of up to 4 digits."""
    ok = [False] * (len(gap) + 1)
    ok[0] = True
    for i in range(len(gap)):
        if not ok[i]:
            continue
        for a in aside:
            if gap.startswith(a, i):
                ok[i + len(a)] = True
        k = i
        while k < len(gap) and k - i < 4 and gap[k].isdigit():
            k += 1
            ok[k] = True
    return ok[len(gap)]


def align(U, S, body_at=0, aside=()):
    """body_at: where in U the first section starts. The record starts at the Act's title page, which is the last
    place its opening words occur before the first section's words (the cover and contents repeat the title).
    aside: the letters and digits of each line the parser left out of the text, longest first."""
    i = j = 0
    first = None
    skips = 0
    m = pat(U[body_at:body_at + 30]).search(S)
    limit = m.start() if m else len(S)
    for n in (40, 16):
        p = [x.start() for x in pat(U[:n]).finditer(S, 0, limit)]
        if p:
            j = first = p[-1]
            break
    while i < len(U):
        if j < len(S) and S[j] == U[i]:
            if first is None:
                first = j
            i += 1; j += 1
            continue
        hit = None
        for L in (1, 2, 3, 4):
            if j + L <= len(S) and S[j:j + L].isdigit() and S[j + L:j + L + 8] == U[i:i + 8]:
                hit = j + L; break
        if hit is not None:
            j = hit; skips += 1
            continue
        # the next 16 characters of the record, footnote numbers (up to 3 digits) allowed between them in the source
        m = re.compile(r'\d{0,3}'.join(map(re.escape, U[i:i + 16]))).search(S, j)
        pos = m.start() if m else -1
        if m:
            # a digit run before the match may belong to the skipped text (a page head ending in a year): start as
            # late as the record's own text still matches there
            rx = re.compile(r'\d{0,3}'.join(map(re.escape, U[i:i + 16])))
            for d in (4, 3, 2, 1):
                if rx.match(S, pos + d):
                    pos += d
                    break
        if pos < 0:
            return False, f'record text not found in the PDF from here: {U[i:i + 60]!r}'
        gap = S[j:pos]

        def ok_gap(g):
            # only set-aside lines (margin notes, footnotes, running heads, page numbers, the stamp) and runs of up
            # to 4 digits, on any number of pages
            return all(not x or tiled(x, aside) for x in g.split(FF))
        if first is None or (len(gap) <= 4 and gap.isdigit()) or ok_gap(gap):
            j = pos; skips += 1
            continue
        # the two engines may put a set-aside line on the other side of the record's last few letters
        if any(i >= k and pos - k >= j - k >= 0 and U[i - k:i] == S[pos - k:pos] and ok_gap(S[j - k:pos - k])
               for k in range(1, 7)):
            j = pos; skips += 1
            continue
        return False, f'source passed over within a page ({len(gap)} chars): {gap[:80]!r} before {U[i:i + 40]!r}'
    # nothing of the body may be left over after the record ends: only set-aside lines and digits
    left = [g for g in S[j:].split(FF) if g and not tiled(g, aside)]
    if left:
        return False, f'source text after the end of the record: {left[0][:80]!r}'
    return True, f'{len(U)} chars matched, {skips} skips'


def aside_of(pdf):
    import parse
    out = {ld(t) for t in parse.parse(pdf)['aside']}
    return sorted((a for a in out if len(a) >= 2), key=lambda a: (-len(a), a))


def check_act(units, S, aside=()):
    U, body_at = '', 0
    for k, u in units.items():
        if k.startswith('sec-') and not body_at:
            body_at = len(U)
        U += ld(re.sub(r'(?m)^# .*$', '', u['text']))
    return align(U, S, body_at, aside)


def pdf_of(url):
    import pkmy_fetch
    return pkmy_fetch.path_for(url)


def main(paths):
    bad = total = 0
    for p in paths:
        c = json.load(open(p, encoding='utf-8'))
        for a in c['acts']:
            v = a['versions'][-1]
            pdf = pdf_of(v['source_url'])
            ok, msg = check_pdf(v['units'], pdf, aside_of(pdf))
            total += 1
            if not ok:
                bad += 1
                print(f'MISMATCH {a["slug"]}: {msg}')
    print(f'{total} acts checked, {bad} mismatches')
    return bad


if __name__ == '__main__':
    sys.exit(1 if main(sys.argv[1:] or sorted(str(p) for p in (HERE / 'corpus.d').glob('*.json'))) else 0)
