import json,urllib.request,urllib.parse,time,datetime,collections,re
UA={'User-Agent':'halflife/1.0 (+https://github.com/Muhammad-Haris-3/Halflife)'}
def gh(url):
    r=urllib.request.Request(url,headers=dict(UA,Accept='application/vnd.github+json'))
    resp=urllib.request.urlopen(r,timeout=45)
    body=json.load(resp)
    nxt=None
    link=resp.headers.get('Link','')
    m=re.search(r'<([^>]+)>;\s*rel="next"',link)
    if m: nxt=m.group(1)
    return body,nxt

adv=[];url='https://api.github.com/advisories?ecosystem=npm&per_page=100&sort=published&direction=desc'
seen=set()
while url and len(adv)<600:
    b,url=gh(url)
    new=[a for a in b if a['ghsa_id'] not in seen]
    for a in new: seen.add(a['ghsa_id'])
    adv+=new
    if not new: break
    time.sleep(0.6)
dates=sorted(a['published_at'][:10] for a in adv)
span=(datetime.date.fromisoformat(dates[-1])-datetime.date.fromisoformat(dates[0])).days
print('UNIQUE advisories=%d  span=%d days  -> %.0f/month'%(len(adv),span,len(adv)/max(span,1)*30.44))
print('window: %s .. %s'%(dates[0],dates[-1]))

advcount=collections.Counter(); meta={}
for a in adv:
    for v in (a.get('vulnerabilities') or []):
        n=(v.get('package') or {}).get('name')
        if n:
            advcount[n]+=1
            meta.setdefault(n,{'sev':a.get('severity'),'fix':bool(v.get('first_patched_version'))})
names=list(advcount); print('distinct advised packages=%d  advisory-package pairs=%d'%(len(names),sum(advcount.values())))

dl={}
uns=[n for n in names if not n.startswith('@')]; sc=[n for n in names if n.startswith('@')]
for i in range(0,len(uns),100):
    ch=uns[i:i+100]
    try:
        d=json.load(urllib.request.urlopen(urllib.request.Request('https://api.npmjs.org/downloads/point/last-week/'+','.join(ch),headers=UA),timeout=45))
        if len(ch)==1: d={ch[0]:d}
        for k,v in d.items(): dl[k]=(v or {}).get('downloads',0) if v else 0
    except Exception as e: print(' bulk fail',str(e)[:40])
    time.sleep(0.25)
for n in sc:
    try: dl[n]=json.load(urllib.request.urlopen(urllib.request.Request('https://api.npmjs.org/downloads/point/last-week/'+urllib.parse.quote(n,safe=''),headers=UA),timeout=30)).get('downloads',0)
    except Exception: dl[n]=0
    time.sleep(0.18)
print('resolved %d/%d (scoped %d)'%(len(dl),len(names),len(sc)))

tot=sum(advcount.values())
print()
print('ADVISORY CAPTURE BY DOWNLOAD THRESHOLD')
print('-'*78)
print('%-12s %10s %10s %12s %10s'%('threshold','pkgs in','% pkgs','% advisories','% w/ fix'))
print('-'*78)
for t,lab in [(1_000_000,'1M'),(100_000,'100k'),(50_000,'50k'),(10_000,'10k'),(5_000,'5k'),(1_000,'1k'),(100,'100')]:
    inn=[n for n in names if dl.get(n,0)>=t]
    wa=sum(advcount[n] for n in inn)
    wf=sum(advcount[n] for n in inn if meta[n]['fix'])
    print('>= %-9s %10d %9.1f%% %11.1f%% %9.1f%%'%(lab,len(inn),100*len(inn)/len(names),100*wa/tot,100*wf/max(wa,1)))
print('-'*78)
print('zero-download advised packages: %d (%.1f%%)'%(sum(1 for n in names if dl.get(n,0)==0),100*sum(1 for n in names if dl.get(n,0)==0)/len(names)))
json.dump({'dl':dl,'advcount':dict(advcount),'meta':meta,'span_days':span,'n_adv':len(adv),'window':[dates[0],dates[-1]]},open('frame_b.json','w'))
