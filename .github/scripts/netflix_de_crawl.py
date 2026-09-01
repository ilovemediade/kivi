#!/usr/bin/env python3
import json, sys, time
from pathlib import Path
from urllib import request, error

ENDPOINT='https://apis.justwatch.com/graphql'; COUNTRY='DE'; LANGUAGE='de'; PACKAGE='nfx'; MONETIZATION='FLATRATE'; PAGE_SIZE=100; HARD_WINDOW=1900
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
def post(variables, attempts=4):
  body=json.dumps({'operationName':'ProviderCatalog','variables':variables,'query':QUERY}).encode()
  for n in range(1,attempts+1):
    req=request.Request(ENDPOINT,data=body,headers={'content-type':'application/json','accept':'application/json','user-agent':'what2watch-netflix-de/partition-1.0','origin':'https://www.justwatch.com','referer':'https://www.justwatch.com/'},method='POST')
    try:
      with request.urlopen(req,timeout=60) as r:return json.load(r)
    except error.HTTPError as e:
      detail=e.read().decode('utf-8','replace')[:3000]
      if 400<=e.code<500 or n==attempts: raise RuntimeError(f'HTTP {e.code}: {detail}')
      time.sleep(min(12,2**n))
    except (error.URLError,TimeoutError):
      if n==attempts: raise
      time.sleep(min(12,2**n))
def base_filter(extra=None):
  f={'packages':[PACKAGE],'monetizationTypes':[MONETIZATION]}
  if extra:f.update(extra)
  return f
def package_matches(pkg):
  vals=[str(pkg.get(k) or '').lower() for k in ('shortName','technicalName','clearName','packageId','id')]
  return PACKAGE in vals or any('netflix' in x for x in vals)
def norm(node):
  c=node.get('content') or {}; ex=c.get('externalIds') or {}; offers=[]
  for o in node.get('offers') or []:
    if str(o.get('monetizationType') or '').upper()==MONETIZATION and package_matches(o.get('package') or {}):
      offers.append({'monetization_type':o.get('monetizationType'),'presentation_type':o.get('presentationType'),'web_url':o.get('standardWebURL'),'package':o.get('package')})
  return {'justwatch_id':node.get('id'),'object_type':node.get('objectType') or node.get('__typename'),'object_id':node.get('objectId'),'title':c.get('title'),'original_title':c.get('originalTitle'),'year':c.get('originalReleaseYear'),'runtime':c.get('runtime'),'full_path':c.get('fullPath'),'poster_url':c.get('posterUrl'),'genres':[g.get('shortName') for g in (c.get('genres') or []) if g.get('shortName')],'imdb_id':ex.get('imdbId'),'offers':offers,'verification':'verified' if offers else 'rejected'}
def fetch_page(filt,offset):
  v={'country':COUNTRY,'language':LANGUAGE,'first':PAGE_SIZE,'offset':offset,'filter':filt}; res=post(v)
  if res.get('errors'):raise RuntimeError(json.dumps(res['errors'],ensure_ascii=False))
  return (res.get('data') or {}).get('popularTitles') or {}
def crawl_partition(name,filt,global_rows,global_seen,errors,stats):
  first=fetch_page(filt,0); total=first.get('totalCount',0); stats.append({'name':name,'total':total})
  print(f'PARTITION {name} total={total}',flush=True)
  if total>HARD_WINDOW:
    print(f'SKIP_OVERSIZE {name} total={total}',flush=True); return total,False
  offset=0; local_seen=set()
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
      local_seen.add(key)
      if key not in global_seen: global_seen.add(key); global_rows[key]=r
    offset+=len(edges); time.sleep(.12)
  ok=len(local_seen)==total
  if not ok: errors.append({'partition':name,'error':f'local unique {len(local_seen)} != total {total}'})
  print(f'DONE {name} local={len(local_seen)} global={len(global_seen)}',flush=True); return total,ok
def main():
  out=Path('out'); out.mkdir(exist_ok=True)
  rows={}; seen=set(); errors=[]; stats=[]
  baseline=fetch_page(base_filter(),0); target=baseline.get('totalCount')
  if not target: raise SystemExit('no target total')
  # Build a live genre vocabulary from the first 100 records, then expand it from the first 1900 window.
  genres=set()
  offset=0
  while offset<HARD_WINDOW and offset<target:
    conn=baseline if offset==0 else fetch_page(base_filter(),offset)
    edges=conn.get('edges') or []
    if not edges: break
    for e in edges:
      r=norm(e.get('node') or {}); key=r.get('justwatch_id')
      if key and key not in seen: seen.add(key); rows[key]=r
      genres.update(r.get('genres') or [])
    offset+=len(edges); time.sleep(.10)
  print('GENRES '+','.join(sorted(genres)),flush=True)
  # Genre x object type partitions. Most are well below JustWatch's 1900-result window.
  oversized=[]
  for typ in ('MOVIE','SHOW'):
    for g in sorted(genres):
      name=f'{typ}:genre:{g}'; total,ok=crawl_partition(name,base_filter({'objectTypes':[typ],'genres':[g]}),rows,seen,errors,stats)
      if total>HARD_WINDOW: oversized.append((typ,g,total))
  # Close remaining gaps with search-query partitions inside each object type. Single characters are intentionally overlapping;
  # correctness is established only by final union == target, never by assuming search semantics.
  search_terms=list('abcdefghijklmnopqrstuvwxyz0123456789')+['ä','ö','ü','ß']
  for typ in ('MOVIE','SHOW'):
    if len(seen)>=target: break
    for term in search_terms:
      name=f'{typ}:search:{term}'; total,ok=crawl_partition(name,base_filter({'objectTypes':[typ],'searchQuery':term}),rows,seen,errors,stats)
      if len(seen)>=target: break
  records=list(rows.values()); verified=[r for r in records if r['verification']=='verified']; rejected=[r for r in records if r['verification']!='verified']
  coverage=(len(seen)==target and len(records)==target and len(verified)==target and not rejected)
  report={'provider':'Netflix','region':'DE','source':'JustWatch public website GraphQL','reported_total':target,'enumerated_unique':len(records),'verified':len(verified),'rejected':len(rejected),'coverage_complete':coverage,'genre_codes':sorted(genres),'oversized_partitions':oversized,'errors':errors,'partition_stats':stats,'movie_count':sum(r['object_type']=='MOVIE' for r in verified),'show_count':sum(r['object_type']=='SHOW' for r in verified),'with_imdb_id':sum(bool(r.get('imdb_id')) for r in verified),'with_poster':sum(bool(r.get('poster_url')) for r in verified)}
  (out/'netflix-de-catalog.json').write_text(json.dumps({'report':report,'records':records},ensure_ascii=False,indent=2),encoding='utf-8')
  (out/'netflix-de-crawl-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
  print(json.dumps({k:v for k,v in report.items() if k!='partition_stats'},ensure_ascii=False,indent=2),flush=True)
  if not coverage: print('COVERAGE_COMPLETE=false',file=sys.stderr); sys.exit(2)
  print('COVERAGE_COMPLETE=true',flush=True)
if __name__=='__main__':main()
