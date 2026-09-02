#!/usr/bin/env python3
import json, time
from pathlib import Path
from urllib import request, error

ENDPOINT='https://apis.justwatch.com/graphql'
COUNTRY='DE'; LANGUAGE='de'
IDS=json.loads(Path('.github/data/rating_ids_480.json').read_text(encoding='utf-8'))
assert len(IDS)==480 and len(set(IDS))==480

QUERY=r'''
query RatingDetails($country: Country!, $language: Language!, $id: ID!) {
  node(id:$id) {
    __typename
    ... on Movie {
      id objectType objectId
      content(country:$country, language:$language) {
        title originalTitle originalReleaseYear runtime fullPath
        genres { shortName }
        externalIds { imdbId }
        shortDescription
        scoring { imdbVotes imdbScore tmdbPopularity tmdbScore tomatoMeter certifiedFresh jwRating }
      }
    }
    ... on Show {
      id objectType objectId
      content(country:$country, language:$language) {
        title originalTitle originalReleaseYear runtime fullPath
        genres { shortName }
        externalIds { imdbId }
        shortDescription
        scoring { imdbVotes imdbScore tmdbPopularity tmdbScore tomatoMeter certifiedFresh jwRating }
      }
    }
  }
}
'''

def post(variables, attempts=7):
    body=json.dumps({'operationName':'RatingDetails','variables':variables,'query':QUERY}).encode()
    for n in range(1,attempts+1):
        req=request.Request(ENDPOINT,data=body,headers={
          'content-type':'application/json','accept':'application/json',
          'user-agent':'what2watch-rating-enrich/1.0',
          'origin':'https://www.justwatch.com','referer':'https://www.justwatch.com/'},method='POST')
        try:
            with request.urlopen(req,timeout=45) as r:return json.load(r)
        except error.HTTPError as e:
            detail=e.read().decode('utf-8','replace')[:1200]
            if e.code==429:
                time.sleep(min(45,5*n)); continue
            if n==attempts: raise RuntimeError(f'HTTP {e.code}: {detail}')
            time.sleep(min(15,n*2))
        except Exception:
            if n==attempts: raise
            time.sleep(min(15,n*2))
    raise RuntimeError('request attempts exhausted')

def norm(jid,node):
    c=node.get('content') or {}; ex=c.get('externalIds') or {}
    return {
      'justwatch_id':jid,
      'object_type':node.get('objectType') or node.get('__typename'),
      'title':c.get('title'),'original_title':c.get('originalTitle'),
      'year':c.get('originalReleaseYear'),'runtime':c.get('runtime'),
      'full_path':c.get('fullPath'),
      'genres':[g.get('shortName') for g in (c.get('genres') or []) if g.get('shortName')],
      'imdb_id':ex.get('imdbId'),'short_description':c.get('shortDescription'),
      'scoring':c.get('scoring')
    }

out=[]; errors=[]
for i,jid in enumerate(IDS,1):
    try:
        res=post({'country':COUNTRY,'language':LANGUAGE,'id':jid})
        if res.get('errors'):
            errors.append({'id':jid,'errors':res['errors']}); continue
        node=(res.get('data') or {}).get('node')
        if not node:
            errors.append({'id':jid,'error':'node null'}); continue
        out.append(norm(jid,node))
    except Exception as e:
        errors.append({'id':jid,'error':repr(e)})
    if i%25==0: print(f'PROGRESS {i}/480 ok={len(out)} errors={len(errors)}',flush=True)
    time.sleep(.10)

byid={r['justwatch_id']:r for r in out}
report={
 'requested':480,'unique_requested':len(set(IDS)),
 'returned':len(out),'unique_returned':len(byid),
 'missing':[x for x in IDS if x not in byid],'errors':errors,
 'with_short_description':sum(bool(r.get('short_description')) for r in out),
 'with_genres':sum(bool(r.get('genres')) for r in out),
 'with_imdb':sum(bool(r.get('imdb_id')) for r in out)
}
Path('out-rating-enrich').mkdir(exist_ok=True)
Path('out-rating-enrich/rating-details-480.json').write_text(json.dumps({'report':report,'records':out},ensure_ascii=False,indent=2),encoding='utf-8')
Path('out-rating-enrich/rating-details-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)
if report['returned'] != 480 or errors: raise SystemExit(2)
