import json,urllib.request,urllib.parse,re,time,datetime,statistics
UA={'User-Agent':'halflife/1.0 (+https://github.com/Muhammad-Haris-3/Halflife)'}
def get(u,data=None):
    r=urllib.request.Request(u,data=data,headers=dict(UA,**({'Content-Type':'application/json'} if data else {})))
    return json.load(urllib.request.urlopen(r,timeout=40))
def sv(v):
    m=re.match(r'^(\d+)\.(\d+)\.(\d+)(?:[-+].*)?$',str(v))
    return tuple(int(x) for x in m.groups()) if m else None
def advised(ver,ranges):
    p=sv(ver)
    if not p: return None
    for rg in ranges:
        intro=None
        for ev in rg.get('events',[]):
            if 'introduced' in ev: intro=sv(ev['introduced']) or (0,0,0)
            elif 'fixed' in ev:
                f=sv(ev['fixed'])
                if intro is not None and f and intro<=p<f: return True
                intro=None
            elif 'last_affected' in ev:
                la=sv(ev['last_affected'])
                if intro is not None and la and intro<=p<=la: return True
                intro=None
        if intro is not None and p>=intro: return True
    return False

PKGS=["js-yaml","axios","lodash","tar","ws","qs","semver","braces","micromatch",
      "cross-spawn","cookie","body-parser","node-fetch","minimist","json5","tough-cookie"]
NOW=datetime.datetime(2026,8,28,tzinfo=datetime.timezone.utc)
tot_r=tot_ok=0; pairs=0; rows=[]
for p in PKGS:
    try:
        reg=get("https://registry.npmjs.org/"+urllib.parse.quote(p,safe=''))
        dl=get("https://api.npmjs.org/versions/%s/last-week"%urllib.parse.quote(p,safe='')).get('downloads',{})
        osv=get("https://api.osv.dev/v1/query",json.dumps({"package":{"name":p,"ecosystem":"npm"}}).encode())
    except Exception as e:
        print("skip",p,e); continue
    ranges=[a['ranges'] for v in osv.get('vulns',[]) for a in v.get('affected',[])
            if (a.get('package',{}) or {}).get('name')==p and a.get('ranges')]
    flat=[r for rs in ranges for r in rs]
    for r in flat:
        tot_r+=1
        if all(sv(e.get('fixed') or e.get('introduced') or e.get('last_affected') or '0.0.0') or (e.get('introduced')=='0')
               for e in r.get('events',[])): tot_ok+=1
    times={v:ts for v,ts in reg.get('time',{}).items() if v not in ('created','modified')}
    latest=reg.get('dist-tags',{}).get('latest')
    A=[];C=[]
    for ver,n in dl.items():
        if ver==latest or ver not in times or not sv(ver): continue
        age=(NOW-datetime.datetime.fromisoformat(times[ver].replace('Z','+00:00'))).days
        isadv=any(advised(ver,rs) for rs in ranges)
        (A if isadv else C).append((age,n,ver))
    if not A or not C: continue
    aA=[a for a,_,_ in A]; aC=[a for a,_,_ in C]
    lo,hi=max(min(aA),min(aC)),min(max(aA),max(aC))
    ovA=[x for x in A if lo<=x[0]<=hi]; ovC=[x for x in C if lo<=x[0]<=hi]
    if ovA and ovC: pairs+=1
    rows.append((p,len(A),len(C),statistics.median(aA),statistics.median(aC),len(ovA),len(ovC),
                 sum(n for _,n,_ in ovC)))
    time.sleep(0.3)

print()
print("MATCHED-CONTROL FEASIBILITY — superseded versions only (latest excluded)")
print("-"*108)
print("%-16s %5s %5s %9s %9s %7s %7s %14s"%("package","adv","ctrl","medAgeA","medAgeC","ovlpA","ovlpC","ctrl wk dl"))
print("-"*108)
for p,na,nc,ma,mc,oa,oc,d in rows:
    print("%-16s %5d %5d %9.0f %9.0f %7d %7d %14s"%(p,na,nc,ma,mc,oa,oc,"{:,}".format(d)))
print("-"*108)
print("packages with an age-overlapping control arm: %d / %d"%(pairs,len(rows)))
print("OSV range events fully semver-parseable: %d / %d = %.1f%%"%(tot_ok,tot_r,100*tot_ok/max(tot_r,1)))
