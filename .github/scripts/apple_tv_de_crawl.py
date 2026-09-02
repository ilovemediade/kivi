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
            'user-agent':'what2watch-apple-tv-de/full-1.0',
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

def detect_apple_package():
    res=post({'country':COUNTRY},query=PACKAGES_QUERY,operation='Packages')
    if res.get('errors'): raise RuntimeError(json.dumps(res['errors'],ensure_ascii=False))
    packages=(res.get('data') or {}).get('packages') or []
    all_apple=[]; cand=[]
    for p in packages:
        name=str(p.get('clearName') or '').strip().lower()
        tech=str(p.get('technicalName') or '').strip().lower()
        short=str(p.get('shortName') or '').strip().lower()
        if 'apple' in name or 'apple' in tech:
            all_apple.append(p)
        excluded=('store' in name or 'amazon' in name or 'channel' in name or 'itunes' in name or 'store' in tech or 'amazon' in tech or 'channel' in tech or 'itunes' in tech)
        service=(name in ('apple tv','apple tv+','apple tv plus') or 'appletvplus' in tech.replace('_','').replace('-','').replace(' ','') or 'apple tv plus' in tech)
        if service and not excluded:
            cand.append(p)
    print('APPLE_PACKAGES '+json.dumps(all_apple,ensure_ascii=False),flush=True)
    print('APPLE_SUBSCRIPTION_CANDIDATES '+json.dumps(cand,ensure_ascii=False),flush=True)
    exact=[p for p in cand if str(p.get('clearName') or '').strip().lower() in ('apple tv','apple tv+','apple tv plus')]
    chosen=exact or cand
    if len(chosen)!=1:
        raise RuntimeError(f'Could not uniquely resolve Apple TV subscription DE package: {chosen}')
    p=chosen[0]
    code=str(p.get('shortName') or '').strip()
    if not code: raise RuntimeError(f'Apple TV package has no shortName: {p}')
    return code,p

def base_filter():
    return {'packages':[PACKAGE],'monetizationTypes':[MONETIZATION]}

def package_matches(pkg):
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

def fetch_page(offset):
    res=post({'country':COUNTRY,'language':LANGUAGE,'first':PAGE_SIZE,'offset':offset,'filter':base_filter()})
    if res.get('errors'): raise RuntimeError(json.dumps(res['errors'],ensure_ascii=False))
    return (res.get('data') or {}).get('popularTitles') or {}

def main():
    global PACKAGE,PACKAGE_META
    out=Path('out-apple-tv'); out.mkdir(exist_ok=True)
    PACKAGE,PACKAGE_META=detect_apple_package()
    print(f'APPLE_PACKAGE {PACKAGE} {PACKAGE_META.get("clearName")}',flush=True)
    first=fetch_page(0); target=first.get('totalCount')
    if not target or target<200 or target>HARD_WINDOW:
        raise SystemExit(f'implausible or non-enumerable Apple TV DE target total: {target} package={PACKAGE_META}')
    print(f'TARGET {target}',flush=True)
    rows={}; errors=[]; offset=0
    while offset<target:
        conn=first if offset==0 else fetch_page(offset)
        if conn.get('totalCount')!=target:
            errors.append({'offset':offset,'error':f'total changed {target}->{conn.get("totalCount")}'})
            break
        edges=conn.get('edges') or []
        if not edges:
            errors.append({'offset':offset,'error':'empty page'})
            break
        for e in edges:
            r=norm(e.get('node') or {}); key=r.get('justwatch_id')
            if key: rows[key]=r
        offset += len(edges)
        time.sleep(.3)
    records=list(rows.values()); verified=[r for r in records if r['verification']=='verified']; rejected=[r for r in records if r['verification']!='verified']
    report={
      'provider':'Apple TV','region':'DE','scope':f'Apple TV subscription catalog / JustWatch {PACKAGE} FLATRATE only',
      'justwatch_package':PACKAGE_META,'source':'JustWatch public website GraphQL','reported_total':target,
      'enumerated_unique':len(records),'verified':len(verified),'rejected':len(rejected),'coverage_complete':len(records)==target==len(verified) and not rejected and not errors,
      'errors':errors,'movie_count':sum(r['object_type']=='MOVIE' for r in verified),'show_count':sum(r['object_type']=='SHOW' for r in verified),
      'with_imdb_id':sum(bool(r.get('imdb_id')) for r in verified),'with_poster':sum(bool(r.get('poster_url')) for r in verified),
      'genre_codes':sorted({g for r in verified for g in (r.get('genres') or [])})
    }
    (out/'apple-tv-de-catalog.json').write_text(json.dumps({'report':report,'records':records},ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'apple-tv-de-crawl-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)
    if not report['coverage_complete']:
        print('COVERAGE_COMPLETE=false',file=sys.stderr); sys.exit(2)
    print('COVERAGE_COMPLETE=true',flush=True)

if __name__=='__main__': main()
