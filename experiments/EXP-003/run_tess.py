import os,time,json,subprocess
os.makedirs('results/tesseract',exist_ok=True); T={}
for f in sorted(os.listdir('crops')):
    k=f[:-4]; t=time.time()
    out=subprocess.run(['tesseract',f'crops/{f}','-','-l','kor','--psm','6'],capture_output=True,text=True).stdout
    T[k]=round(time.time()-t,2); open(f'results/tesseract/{k}.txt','w',encoding='utf-8').write(out)
json.dump({'seconds':T,'cost':0},open('results/tesseract/meta.json','w',encoding='utf-8')); print(T)
