import os,time,json,easyocr
def order(res):
    items=[(min(p[1] for p in b),max(p[1] for p in b),min(p[0] for p in b),t) for b,t,c in res]
    items.sort(key=lambda x:(x[0]+x[1])/2); lines=[]
    for it in items:
        yc=(it[0]+it[1])/2
        if lines and abs(yc-lines[-1]['yc'])<0.5*(it[1]-it[0]): lines[-1]['w'].append(it)
        else: lines.append({'yc':yc,'w':[it]})
    return '\n'.join(' '.join(w[3] for w in sorted(l['w'],key=lambda w:w[2])) for l in lines)
r=easyocr.Reader(['ko','en'],gpu=False,download_enabled=False)
os.makedirs('results/easyocr_2x',exist_ok=True); T={}
for f in sorted(os.listdir('crops2x')):
    k=f[:-4]; t=time.time()
    res=r.readtext(f'crops2x/{f}',paragraph=False)
    T[k]=round(time.time()-t,2)
    # sort into reading order: by line (y center) then x
    open(f'results/easyocr_2x/{k}.txt','w',encoding='utf-8').write(order(res))
    print(k,T[k],flush=True)
json.dump({'seconds':T,'cost':0},open('results/easyocr_2x/meta.json','w',encoding='utf-8'))
