import sys,pymupdf; sys.path.insert(0,'../world-law'); import pkmy_fetch as f
d=pymupdf.open(f.path_for(f'https://sindhlaws.gov.pk/DownloadDocument.aspx?PubID={sys.argv[1]}&Lang=EN'))
for pn in map(int,sys.argv[2].split(',')):
  pg=d[pn]; print('PAGE',pn,pg.rect)
  for b in pg.get_text('dict')['blocks']:
    if b['type']!=0: print('IMG',[round(x) for x in b['bbox']]); continue
    for l in b['lines']:
      sp=[s for s in l['spans'] if s['text'].strip()]
      if sp: print([round(x) for x in l['bbox']], [round(s['size'],1) for s in sp][:4], 'B' if 'Bold' in sp[0]['font'] or 'Bo' in sp[0]['font'] else '', repr(''.join(s['text'] for s in sp))[:90])
