#!/usr/bin/env python3
import json, sys, time
from pathlib import Path
from urllib import request, error

ENDPOINT='https://apis.justwatch.com/graphql'
COUNTRY='DE'; LANGUAGE='de'; PACKAGE=None; PACKAGE_META=None; MONETIZATION='FLATRATE'
PAGE_SIZE=100; HARD_WINDOW=1900
QUERY=r'''
query ProviderCatalog($country: Country!, $language: Language!, $first: Int!, $offset: Int!, $filter: TitleFilter) {
  popularTitles(country:$country, first:$first, offset:$offset, filter:$filter, sortBy:POPULAR) {
    totalCount
    edges { node { __typename
      ... on Movie { id objectType objectId content(country:$country,language:$language){title originalTitle originalReleaseYear runtime fullPath posterUrl genres{shortName} externalIds{imdbId}} offers(country:$country,platform:WEB){monetizationType presentationType standardWebURL package{id packageId clearName shortName technicalName}} }
      ... on Show  { id objectType objectId content(country:$country,language:$language){title originalTitle originalReleaseYear runtime fullPath posterUrl genres{shortName} externalIds{imdbId}} offers(country:$country,platform:WEB){monetizationType presentationType standardWebURL package{id packageId clearName shortName technicalName}} }
    } }
  }
}
'''
PACKAGES_QUERY=r'''
query Packages($country: Country!) {
  packages(country:$country, platform:WEB) { id packageId clearName shortName technicalName }
}
'''

def post(variables, attempts=8, query=QUERY, operation='ProviderCatalog'):
    body=json.dumps({'operationName':operation,'variables':variables,'query':query}).encode()
    for n in range(1,attempts+1):
        req=request.Request(ENDPOINT,data=body,headers={
            'content-type':'application/json','accept':'application/json',
            'user-agent':'what2watch-prime-de/partition-2.1',
            'origin':'https://www.justwatch.com','referer':'https://www.justwatch.com/'},method='POST')
        try:
            with request.urlopen(req,timeout=60) as r: return json.load(r)
        except error.HTTPError as e:
            detail=e.read().decode('utf-8','replace')[:3000]
            if e.code==429:
                delay=min(75,10*n); print(f'RATE_LIMIT retry={n} sleep={delay}',flush=True); time.sleep(delay); continue
            if 400<=e.code<500 or n==attempts: raise RuntimeError(f'HTTP {e.code}: {detail}')
            time.sleep(min(30,2**n))
        except (error.URLError,TimeoutError):
            if n==attempts: raise
            time.sleep(min(30,2**n))
    raise RuntimeError('request attempts exhausted')

def detect_prime_package():
    res=post({'country':COUNTRY},query=PACKAGES_QUERY,operation='Packages')
    if res.get('errors'): raise RuntimeError(json.dumps(res['errors'],ensure_ascii=False))
    packages=(res.get('data') or {}).get('packages') or []
    cand=[]
    for p in packages:
        name=str(p.get('clearName') or '').strip().lower()
        tech=str(p.get('technicalName') or '').strip().lower()
        if name=='amazon prime video' or tech=='amazon prime video' or ('amazon prime video' in name and 'channel' not in name):
            cand.append(p)
    print('PRIME_PACKAGE_CANDIDATES '+json.dumps(cand,ensure_ascii=False),flush=True)
    exact=[p for p in cand if str(p.get('clearName') or '').strip().lower()=='amazon prime video']
    chosen=(exact or cand)
    if len(chosen)!=1:
        raise RuntimeError(f'Could not uniquely resolve Amazon Prime Video DE package: {chosen}')
    p=chosen[0]
    code=str(p.get('shortName') or '').strip()
    if not code: raise RuntimeError(f'Prime package has no shortName: {p}')
    return code,p

def base_filter(extra=None):
    if not PACKAGE: raise RuntimeError('Prime package not initialized')
    f={'packages':[PACKAGE],'monetizationTypes':[MONETIZATION]}
    if extra: f.update(extra)
    return f

def package_matches(pkg):
    if not PACKAGE_META: return False
    short=str(pkg.get('shortName') or '').strip().lower()
    name=str(pkg.get('clearName') or '').strip().lower()
    return short==str(PACKAGE).lower() or name==str(PACKAGE_META.get('clearName') or '').strip().lower()

def norm(node):
    c=node.get('content') or {}; ex=c.get('externalIds') or {}; offers=[]
    for o in node.get('offers') or []:
        if str(o.get('monetizationType') or '').upper()==MONETIZATION and package_matches(o.get('package') or {}):
            offers.append({'monetization_type':o.get('monetizationType'),'presentation_type':o.get('presentationType'),'web_url':o.get('standardWebURL'),'package':o.get('package')})
    return {
        'justwatch_id':node.get('id'),'object_type':node.get('objectType') or node.get('__typename'),'object_id':node.get('objectId'),
        'title':c.get('title'),'original_title':c.get('originalTitle'),'year':c.get('originalReleaseYear'),'runtime':c.get('runtime'),
        'full_path':c.get('fullPath'),'poster_url':c.get('posterUrl'),'genres':[g.get('shortName') for g in (c.get('genres') or []) if g.get('shortName')],
        'imdb_id':ex.get('imdbId'),'offers':offers,'verification':'verified' if offers else 'rejected'
    }

def fetch_page(filt,offset):
    res=post({'country':COUNTRY,'language':LANGUAGE,'first':PAGE_SIZE,'offset':offset,'filter':filt})
    if res.get('errors'): raise RuntimeError(json.dumps(res['errors'],ensure_ascii=False))
    return (res.get('data') or {}).get('popularTitles') or {}

def save(out,target,rows,seen,errors,stats,genres,final=False):
    records=list(rows.values()); verified=[r for r in records if r['verification']=='verified']; rejected=[r for r in records if r['verification']!='verified']
    coverage=final and target>8000 and len(seen)==target and len(records)==target and len(verified)==target and not rejected and not errors
    report={
        'provider':'Amazon Prime Video','region':'DE','scope':f'Prime membership included / JustWatch {PACKAGE} FLATRATE only',
        'justwatch_package':PACKAGE_META,'source':'JustWatch public website GraphQL','reported_total':target,'enumerated_unique':len(records),'verified':len(verified),'rejected':len(rejected),
        'coverage_complete':coverage,'genre_codes':sorted(genres),'errors':errors,'partition_stats':stats,
        'movie_count':sum(r['object_type']=='MOVIE' for r in verified),'show_count':sum(r['object_type']=='SHOW' for r in verified),
        'with_imdb_id':sum(bool(r.get('imdb_id')) for r in verified),'with_poster':sum(bool(r.get('poster_url')) for r in verified)
    }
    (out/'prime-de-catalog.json').write_text(json.dumps({'report':report,'records':records},ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'prime-de-crawl-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report

def crawl_partition(name,filt,rows,seen,errors,stats,out,target,genres):
    first=fetch_page(filt,0); total=first.get('totalCount',0); stats.append({'name':name,'total':total}); print(f'PARTITION {name} total={total}',flush=True)
    if total>HARD_WINDOW:
        print(f'SKIP_OVERSIZE {name} total={total}',flush=True); return total,False
    offset=0; local=set()
    while offset<total:
        conn=first if offset==0 else fetch_page(filt,offset)
        if conn.get('totalCount')!=total:
            errors.append({'partition':name,'offset':offset,'error':f'total changed {total}->{conn.get("totalCount")}' }); return total,False
        edges=conn.get('edges') or []
        if not edges:
            errors.append({'partition':name,'offset':offset,'error':'empty page'}); return total,False
        for e in edges:
            r=norm(e.get('node') or {}); key=r.get('justwatch_id')
            if not key: continue
            local.add(key); genres.update(r.get('genres') or [])
            if key not in seen: seen.add(key); rows[key]=r
        offset+=len(edges); time.sleep(.32)
    ok=len(local)==total
    if not ok: errors.append({'partition':name,'error':f'local unique {len(local)} != total {total}'})
    save(out,target,rows,seen,errors,stats,genres,False)
    print(f'DONE {name} local={len(local)} global={len(seen)}',flush=True)
    return total,ok

def main():
    global PACKAGE,PACKAGE_META
    out=Path('out-prime'); out.mkdir(exist_ok=True); rows={}; seen=set(); errors=[]; stats=[]; genres=set()
    PACKAGE,PACKAGE_META=detect_prime_package()
    print(f'PRIME_PACKAGE {PACKAGE} {PACKAGE_META.get("clearName")}',flush=True)
    baseline=fetch_page(base_filter(),0); target=baseline.get('totalCount')
    if not target or target<=8000: raise SystemExit(f'implausible Prime DE target total: {target} package={PACKAGE_META}')
    print(f'TARGET {target}',flush=True)

    offset=0
    while offset<HARD_WINDOW and offset<target:
        conn=baseline if offset==0 else fetch_page(base_filter(),offset); edges=conn.get('edges') or []
        if not edges: break
        for e in edges:
            r=norm(e.get('node') or {}); key=r.get('justwatch_id')
            if key and key not in seen: seen.add(key); rows[key]=r
            genres.update(r.get('genres') or [])
        offset+=len(edges); time.sleep(.28)
    print('GENRES '+','.join(sorted(genres)),flush=True)

    crawl_partition('SHOW:all',base_filter({'objectTypes':['SHOW']}),rows,seen,errors,stats,out,target,genres)

    current=2026
    for start in range(1800,current+1,5):
        end=min(current,start+4)
        filt=base_filter({'objectTypes':['MOVIE'],'releaseYear':{'min':start,'max':end}})
        total,ok=crawl_partition(f'MOVIE:year:{start}-{end}',filt,rows,seen,errors,stats,out,target,genres)
        if total>HARD_WINDOW:
            for y in range(start,end+1):
                crawl_partition(f'MOVIE:year:{y}',base_filter({'objectTypes':['MOVIE'],'releaseYear':{'min':y,'max':y}}),rows,seen,errors,stats,out,target,genres)

    if len(seen)!=target:
        print(f'YEAR_UNION_GAP target={target} seen={len(seen)} gap={target-len(seen)} -> genre fallback',flush=True)
        for typ in ('MOVIE','SHOW'):
            for g in sorted(genres):
                crawl_partition(f'{typ}:genre:{g}',base_filter({'objectTypes':[typ],'genres':[g]}),rows,seen,errors,stats,out,target,genres)
            crawl_partition(f'{typ}:no-known-genre',base_filter({'objectTypes':[typ],'excludeGenres':sorted(genres)}),rows,seen,errors,stats,out,target,genres)

    report=save(out,target,rows,seen,errors,stats,genres,True)
    print(json.dumps({k:v for k,v in report.items() if k!='partition_stats'},ensure_ascii=False,indent=2),flush=True)
    if not report['coverage_complete']:
        print('COVERAGE_COMPLETE=false',file=sys.stderr); sys.exit(2)
    print('COVERAGE_COMPLETE=true',flush=True)

if __name__=='__main__': main()
