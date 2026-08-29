import json,urllib.request,re,time,sys

UA={'User-Agent':'halflife/1.0 (+https://github.com/Muhammad-Haris-3/Halflife)'}
def get(url,data=None):
    req=urllib.request.Request(url,data=data,headers=dict(UA,**({'Content-Type':'application/json'} if data else {})))
    return json.load(urllib.request.urlopen(req,timeout=30))

def sv(v):
    m=re.match(r'^(\d+)\.(\d+)\.(\d+)',str(v))
    return tuple(int(x) for x in m.groups()) if m else None

def vulnerable(ver, ranges):
    """True if ver falls in any [introduced, fixed) interval."""
    p=sv(ver)
    if not p: return None
    for rg in ranges:
        if rg.get('type') not in ('SEMVER','ECOSYSTEM'): continue
        intro=None
        for ev in rg.get('events',[]):
            if 'introduced' in ev:
                intro=sv(ev['introduced']) or (0,0,0)
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

PKGS=["lodash","minimist","axios","tar","node-fetch","semver","ws","jsonwebtoken",
      "request","glob-parent","ansi-regex","braces","cross-spawn","path-to-regexp",
      "follow-redirects","qs","tough-cookie","ip","micromatch","nth-check",
      "json5","loader-utils","shell-quote","word-wrap","cookie","body-parser","send"]

rows=[]
for p in PKGS:
    try:
        osv=get("https://api.osv.dev/v1/query",json.dumps({"package":{"name":p,"ecosystem":"npm"}}).encode())
        dl=get("https://api.npmjs.org/versions/%s/last-week"%p).get('downloads',{})
    except Exception as e:
        print("  skip %-18s %s"%(p,e)); continue
    if not dl: continue
    adv=[]
    for v in osv.get('vulns',[]):
        sev=(v.get('database_specific',{}) or {}).get('severity')
        for a in v.get('affected',[]):
            if (a.get('package',{}) or {}).get('name')==p and a.get('ranges'):
                adv.append((v['id'],v.get('published',''),sev,a['ranges']))
    if not adv: continue
    tot=sum(dl.values()); vuln=0; unparsed=0
    for ver,n in dl.items():
        hit=False
        for _,_,_,rg in adv:
            r=vulnerable(ver,rg)
            if r is None: unparsed+=n; break
            if r: hit=True; break
        if hit: vuln+=n
    oldest=min((a[1] for a in adv if a[1]),default='')
    rows.append((p,tot,vuln,100*vuln/tot if tot else 0,len(adv),oldest[:10],unparsed))
    time.sleep(0.4)

rows.sort(key=lambda r:-r[3])
print()
print("PILOT — share of CURRENT weekly npm downloads on versions a published advisory calls vulnerable")
print("-"*104)
print("%-18s %>14s %>14s %>8s %>5s  %s".replace('%>','%')%("package","weekly dl","vulnerable dl","%vuln","advs","oldest adv"))
print("-"*104)
for p,tot,vuln,pct,na,old,_ in rows:
    print("%-18s %14s %14s %7.1f%% %5d  %s"%(p,"{:,}".format(tot),"{:,}".format(vuln),pct,na,old))
T=sum(r[1] for r in rows); V=sum(r[2] for r in rows)
print("-"*104)
print("%-18s %14s %14s %7.1f%%   (%d packages)"%("TOTAL","{:,}".format(T),"{:,}".format(V),100*V/T if T else 0,len(rows)))
