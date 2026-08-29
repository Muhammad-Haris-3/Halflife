import json,urllib.request,urllib.parse,random,time,math
UA={'User-Agent':'halflife-frame/0.1 (hariskhokhar975@gmail.com)'}
random.seed(20260828)
def req(u,t=60):
    return json.load(urllib.request.urlopen(urllib.request.Request(u,headers=UA),timeout=t))
def allkeys(sk,limit):
    return req('https://replicate.npmjs.com/_all_docs?limit=%d&startkey=%s'%(limit,urllib.parse.quote(json.dumps(sk))))

TOTAL=4335856; SCOPED=1653334; UNSCOPED=TOTAL-SCOPED
CH='abcdefghijklmnopqrstuvwxyz0123456789-'
def rand_unscoped(): return ''.join(random.choice(CH) for _ in range(2))
def rand_scoped():   return '@'+''.join(random.choice(CH) for _ in range(2))

def sample(kind,n_loc,run):
    names=[]
    for i in range(n_loc):
        sk=rand_unscoped() if kind=='u' else rand_scoped()
        try:
            d=allkeys(sk,run)
            got=[r['id'] for r in d['rows']]
            if kind=='u': got=[g for g in got if not g.startswith('@')]
            else:         got=[g for g in got if g.startswith('@')]
            names+=got
        except Exception as e: pass
        time.sleep(0.25)
    return names

print('sampling unscoped localities...',flush=True)
uns=sample("u",90,30)
print('sampling scoped localities...',flush=True)
sco=sample("s",45,20)
print('sampled: unscoped=%d scoped=%d'%(len(uns),len(sco)),flush=True)

dl_u={}
for i in range(0,len(uns),100):
    ch=uns[i:i+100]
    try:
        d=req('https://api.npmjs.org/downloads/point/last-week/'+','.join(urllib.parse.quote(c,safe='') for c in ch))
        if len(ch)==1: d={ch[0]:d}
        for k,v in d.items(): dl_u[k]=(v or {}).get('downloads',0) if v else 0
    except Exception as e: print(' bulkfail',str(e)[:40],flush=True)
    time.sleep(0.2)
print('unscoped resolved %d'%len(dl_u),flush=True)
dl_s={}
for n in sco:
    try: dl_s[n]=req('https://api.npmjs.org/downloads/point/last-week/'+urllib.parse.quote(n,safe=''),30).get('downloads',0)
    except Exception: dl_s[n]=0
    time.sleep(0.12)
print('scoped resolved %d'%len(dl_s),flush=True)

print()
print('ESTIMATED npm PACKAGES ABOVE EACH WEEKLY-DOWNLOAD THRESHOLD')
print('  strata: unscoped N=%s (sample %d) | scoped N=%s (sample %d)'%('{:,}'.format(UNSCOPED),len(dl_u),'{:,}'.format(SCOPED),len(dl_s)))
print('-'*86)
print('%-10s %8s %8s %14s %26s'%('threshold','hits_u','hits_s','est. packages','95% CI'))
print('-'*86)
out={}
for t,lab in [(1_000_000,'1M'),(100_000,'100k'),(50_000,'50k'),(10_000,'10k'),(5_000,'5k'),(1_000,'1k')]:
    hu=sum(1 for v in dl_u.values() if v>=t); hs=sum(1 for v in dl_s.values() if v>=t)
    pu=hu/max(len(dl_u),1); ps=hs/max(len(dl_s),1)
    est=UNSCOPED*pu+SCOPED*ps
    vu=UNSCOPED**2*pu*(1-pu)/max(len(dl_u),1); vs=SCOPED**2*ps*(1-ps)/max(len(dl_s),1)
    se=math.sqrt(vu+vs)
    out[lab]=(est,se)
    print('>= %-7s %8d %8d %14s   %s'%(lab,hu,hs,'{:,.0f}'.format(est),'{:,.0f} - {:,.0f}'.format(max(0,est-1.96*se),est+1.96*se)))
print('-'*86)
for lab,(est,se) in out.items():
    print('  cohort >=%-5s poll time @0.85s/pkg: %5.1f hours   weekly raw @14.1KB: %6.0f MB'%(lab,est*0.85/3600,est*14.1/1024))
json.dump({'dl_u':dl_u,'dl_s':dl_s},open('cohort_sample.json','w'))
