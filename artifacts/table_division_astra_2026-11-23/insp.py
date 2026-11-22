import json,gzip,sys,os
S=sys.argv[1]; W=os.path.join(os.environ['LOCALAPPDATA'],'NewFileManager','works','51b32f08166c','headings')
doc=json.load(open(S+'/doc_51b32f08166c.json',encoding='utf-8'))
bl=doc['blocks']
st=json.load(gzip.open(W+'/6/tables.json.gz','rt',encoding='utf-8'))
T={t['id']:t for t in st['tables']}
m=json.load(open(S+'/mem_51b32f08166c.json',encoding='utf-8'))
gt={}
for g in m['groups']:
  if g['where'].get('table'): gt.setdefault(g['where']['table'],[]).append((g['dim'],g['count'],[it['text'] for it in g['items']][:5]))
key=sys.argv[2]; n=int(sys.argv[3])
start=[i for i,b in enumerate(bl) if (b.get('text') or '').strip().startswith(key)]
print(key,'at',start)
i0=start[-1]
for b in bl[i0:i0+n]:
  if b['type']=='table':
    t=T.get(b['id'],{})
    heads=[(c['id'],c.get('role'),c.get('basis'),c.get('basisKind'),(c.get('text') or '')[:14]) for c in t.get('cells',[]) if c.get('basis')]
    print('TABLE',b['id'],b['nRows'],'x',b['nCols'],'owner',(t.get('owner') or {}).get('text','')[:30],'basis',t.get('basis'),'groups',gt.get(b['id']))
    print('   basis cells', heads[:14])
    print('   first cells', [(c['id'],(c.get('text') or '')[:12]) for c in b['cells'][:10]])
  elif (b.get('text') or '').strip():
    print('P',b['id'],(b.get('text') or '')[:60])
