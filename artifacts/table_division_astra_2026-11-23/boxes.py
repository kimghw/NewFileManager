import json,gzip,sys,os,re
S=sys.argv[1]; W=os.path.join(os.environ['LOCALAPPDATA'],'NewFileManager','works','51b32f08166c','headings')
doc=json.load(open(S+'/doc_51b32f08166c.json',encoding='utf-8'))
bl=doc['blocks']
g=json.load(gzip.open(W+'/5/graph.json.gz','rt',encoding='utf-8'))
print('graph keys', list(g.keys())[:20])
nodes={n['para']:n for n in g.get('nodes',[]) if n.get('para')}
# 1-cell tables in body
for i,b in enumerate(bl):
  if b['type']=='table' and b.get('nRows')==1 and b.get('nCols')==1:
    c=b['cells'][0]; txt=(c.get('text') or '').strip()
    paras=c.get('paras') or c.get('blocks') or []
    if len(txt)<=40 and txt:
      prev=next((x for x in reversed(bl[:i]) if (x.get('text') or '').strip()),{})
      nxt=next((x for x in bl[i+1:] if (x.get('text') or '').strip() or x['type']=='table'),{})
      pn=nodes.get(prev.get('id'),{}); nn=nodes.get(nxt.get('id'),{})
      pid=[p.get('id') for p in paras]
      inner=[nodes.get(p) for p in pid if nodes.get(p)]
      print(b['id'], repr(txt[:30]), '| prev', (prev.get('text') or '')[:22], pn.get('type'), pn.get('level'), '| next', (nxt.get('text') or '')[:22], nn.get('type'), nn.get('level'), '| inner node', [(x.get('type'),x.get('role'),x.get('kind')) for x in inner])
