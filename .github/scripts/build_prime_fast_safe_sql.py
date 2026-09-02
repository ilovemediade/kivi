#!/usr/bin/env python3
import json, hashlib, gzip, re, sys
from pathlib import Path
from collections import Counter
from urllib.parse import urlparse

CAT=Path(sys.argv[1])
OUT_SQL=Path(sys.argv[2])
OUT_GZ=OUT_SQL.with_suffix(OUT_SQL.suffix+'.gz')

data=json.loads(CAT.read_text(encoding='utf-8'))
report=data['report']; records=data['records']

GENRE_MAP={
'act':('action','Action & Adventure'),'ani':('animation','Animation'),'cmy':('comedy','Comedy'),
'crm':('crime','Crime'),'doc':('documentary','Documentary'),'drm':('drama','Drama'),
'eur':('european','European'),'fml':('family','Family'),'fnt':('fantasy','Fantasy'),
'hrr':('horror','Horror'),'hst':('history','History'),'msc':('music','Music'),
'rly':('reality-tv','Reality TV'),'rma':('romance','Romance'),'scf':('science-fiction','Science Fiction'),
'spt':('sport','Sport'),'trl':('mystery-thriller','Mystery & Thriller'),
'war':('war-military','War & Military'),'wsn':('western','Western')}

assert report['coverage_complete'] is True
assert report['reported_total']==report['enumerated_unique']==report['verified']==9016
assert report['rejected']==0 and not report['errors']
assert report['justwatch_package']['shortName']=='amp'
assert len(records)==9016
assert len({r['justwatch_id'] for r in records})==9016
assert len({r['full_path'] for r in records})==9016
assert all(r.get('verification')=='verified' for r in records)
assert all(r.get('title') and r.get('full_path') for r in records)
assert max(len(r['full_path']) for r in records)<=128
imdb_counts=Counter(r.get('imdb_id') for r in records if r.get('imdb_id'))
assert not imdb_counts or max(imdb_counts.values())==1

def q(v):
    if v is None: return 'NULL'
    s=str(v).replace('\\','\\\\').replace("'","''").replace('\r',' ').replace('\n',' ')
    return "'"+s+"'"
def n(v): return 'NULL' if v is None else str(int(v))
def poster_url(tpl):
    if not tpl: return None
    s=tpl.replace('{profile}','s718').replace('{format}','jpg')
    if not s.startswith('/'): s='/'+s
    return 'https://images.justwatch.com'+s
def choose_offer(r):
    offers=r.get('offers') or []
    assert offers
    def rank(o):
        host=urlparse(o.get('web_url') or '').netloc.lower()
        if host=='watch.amazon.de': return 0
        if host=='www.primevideo.com': return 1
        if host.endswith('amazon.de'): return 2
        return 3
    o=sorted(offers,key=rank)[0]
    assert o.get('web_url')
    return o['web_url']

stage=[]
for r in records:
    genres=[]
    for code in r.get('genres') or []:
        assert code in GENRE_MAP, (r['justwatch_id'],code)
        genres.append(GENRE_MAP[code][0])
    web=choose_offer(r)
    payload='|'.join([r['justwatch_id'],r['full_path'],r.get('imdb_id') or '',r['title'],str(r.get('year') or ''),web])
    stage.append({
      'jw_id':r['justwatch_id'],'jw_path':r['full_path'],'jw_slug':'jw-'+r['justwatch_id'],
      'imdb_id_key':r.get('imdb_id') or None,
      'media_type':'movie' if r['object_type']=='MOVIE' else 'series',
      'title':r['title'],'original_title':r.get('original_title') or None,
      'release_year':r.get('year'),'runtime_minutes':r.get('runtime'),
      'poster_url':poster_url(r.get('poster_url')),'web_url':web,
      'genre_csv':','.join(genres),
      'payload_hash':hashlib.sha256(payload.encode('utf-8')).hexdigest()
    })

assert len(stage)==9016
assert sum(bool(x['imdb_id_key']) for x in stage)==8719
assert sum(bool(x['poster_url']) for x in stage)==8963

lines=[]; w=lines.append
w("""/* what2watch Amazon Prime Video DE FAST+SAFE
   Snapshot: 2026-09-02
   Coverage: 9016/9016 verified JustWatch Amazon Prime Video DE exact amp FLATRATE records
   MariaDB 10.6/phpMyAdmin optimized: one indexed staging table; no COLLATE joins; no correlated identity subqueries.
*/""")
w("SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;")
w("SET @w2w_now := NOW();")
w("SET SESSION innodb_lock_wait_timeout=30;")
w("SET SESSION lock_wait_timeout=30;")
w("INSERT INTO providers (slug,name) VALUES ('prime','Prime Video') ON DUPLICATE KEY UPDATE name=COALESCE(NULLIF(name,''),VALUES(name));")
w("SET @w2w_prime_provider := (SELECT id FROM providers WHERE slug='prime' LIMIT 1);")
w("""INSERT INTO provider_external_ids (provider_id,source,external_id,external_name,last_checked_at)
VALUES (@w2w_prime_provider,'justwatch','amp','Amazon Prime Video',@w2w_now)
ON DUPLICATE KEY UPDATE external_id=VALUES(external_id),external_name=VALUES(external_name),last_checked_at=VALUES(last_checked_at);""")
ST='w2w_amp_20260902_stage'
w(f"DROP TABLE IF EXISTS {ST};")
w(f"""CREATE TABLE {ST} (
 jw_id VARCHAR(32) NOT NULL,
 jw_path VARCHAR(128) NOT NULL,
 jw_slug VARCHAR(190) NOT NULL,
 imdb_id_key VARCHAR(32) NULL,
 media_type ENUM('movie','series') NOT NULL,
 title VARCHAR(255) NOT NULL,
 original_title VARCHAR(512) NULL,
 release_year SMALLINT UNSIGNED NULL,
 runtime_minutes SMALLINT UNSIGNED NULL,
 poster_url VARCHAR(1024) NULL,
 web_url VARCHAR(1024) NOT NULL,
 genre_csv VARCHAR(255) NOT NULL,
 payload_hash CHAR(64) NOT NULL,
 media_id BIGINT UNSIGNED NULL,
 match_source VARCHAR(32) NULL,
 PRIMARY KEY (jw_id),
 UNIQUE KEY uq_w2w_amp_slug (jw_slug),
 KEY idx_w2w_amp_path (jw_path),
 KEY idx_w2w_amp_imdb (imdb_id_key),
 KEY idx_w2w_amp_media (media_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;""")
cols=['jw_id','jw_path','jw_slug','imdb_id_key','media_type','title','original_title','release_year','runtime_minutes','poster_url','web_url','genre_csv','payload_hash','media_id','match_source']
def row(x):
    vals=[q(x['jw_id']),q(x['jw_path']),q(x['jw_slug']),q(x['imdb_id_key']),q(x['media_type']),q(x['title']),q(x['original_title']),n(x['release_year']),n(x['runtime_minutes']),q(x['poster_url']),q(x['web_url']),q(x['genre_csv']),q(x['payload_hash']),'NULL','NULL']
    return '('+','.join(vals)+')'
for i in range(0,len(stage),250):
    ch=stage[i:i+250]
    w(f"INSERT INTO {ST} ({','.join(cols)}) VALUES\n"+',\n'.join(row(x) for x in ch)+';')

w(f"UPDATE {ST} s JOIN media_external_ids e ON e.source='justwatch-node' AND e.external_id=s.jw_id SET s.media_id=e.media_id,s.match_source='justwatch-node' WHERE s.media_id IS NULL;")
w(f"UPDATE {ST} s JOIN media_external_ids e ON e.source='justwatch' AND e.external_id=s.jw_path SET s.media_id=e.media_id,s.match_source='justwatch-path' WHERE s.media_id IS NULL;")
w(f"UPDATE {ST} s JOIN media_external_ids e ON e.source='imdb' AND e.external_id=s.imdb_id_key SET s.media_id=e.media_id,s.match_source='imdb-external' WHERE s.media_id IS NULL AND s.imdb_id_key IS NOT NULL;")
w(f"""UPDATE {ST} s
JOIN (
  SELECT imdb_id,MIN(id) AS media_id FROM media
  WHERE imdb_id IS NOT NULL AND imdb_id<>''
  GROUP BY imdb_id HAVING COUNT(*)=1
) m ON m.imdb_id=s.imdb_id_key
SET s.media_id=m.media_id,s.match_source='imdb-legacy'
WHERE s.media_id IS NULL AND s.imdb_id_key IS NOT NULL;""")
w(f"UPDATE {ST} s JOIN media m ON m.slug=s.jw_slug SET s.media_id=m.id,s.match_source='jw-slug' WHERE s.media_id IS NULL;")
w(f"""INSERT INTO media (slug,title,title_de,original_title,media_type,year,runtime_minutes,poster_url,imdb_id,german_available,is_active)
SELECT jw_slug,title,title,original_title,media_type,release_year,runtime_minutes,poster_url,imdb_id_key,0,1
FROM {ST} WHERE media_id IS NULL;""")
w(f"UPDATE {ST} s JOIN media m ON m.slug=s.jw_slug SET s.media_id=m.id,s.match_source='created' WHERE s.media_id IS NULL;")
w(f"""UPDATE media m JOIN {ST} s ON s.media_id=m.id
SET m.title=COALESCE(NULLIF(m.title,''),s.title),m.title_de=COALESCE(NULLIF(m.title_de,''),s.title),
    m.original_title=COALESCE(NULLIF(m.original_title,''),s.original_title),m.year=COALESCE(m.year,s.release_year),
    m.runtime_minutes=COALESCE(m.runtime_minutes,s.runtime_minutes),m.poster_url=COALESCE(NULLIF(m.poster_url,''),s.poster_url),
    m.imdb_id=COALESCE(NULLIF(m.imdb_id,''),s.imdb_id_key),m.is_active=1
WHERE s.media_id IS NOT NULL;""")
w(f"""INSERT INTO media_external_ids (media_id,source,external_id,canonical_url,last_checked_at)
SELECT media_id,'justwatch-node',jw_id,CONCAT('https://www.justwatch.com',jw_path),@w2w_now FROM {ST} WHERE media_id IS NOT NULL
ON DUPLICATE KEY UPDATE canonical_url=VALUES(canonical_url),last_checked_at=VALUES(last_checked_at);""")
w(f"""INSERT INTO media_external_ids (media_id,source,external_id,canonical_url,last_checked_at)
SELECT media_id,'justwatch',jw_path,CONCAT('https://www.justwatch.com',jw_path),@w2w_now FROM {ST} WHERE media_id IS NOT NULL
ON DUPLICATE KEY UPDATE canonical_url=VALUES(canonical_url),last_checked_at=VALUES(last_checked_at);""")
w(f"""INSERT INTO media_external_ids (media_id,source,external_id,canonical_url,last_checked_at)
SELECT media_id,'imdb',imdb_id_key,CONCAT('https://www.imdb.com/title/',imdb_id_key,'/'),@w2w_now FROM {ST} WHERE media_id IS NOT NULL AND imdb_id_key IS NOT NULL
ON DUPLICATE KEY UPDATE canonical_url=VALUES(canonical_url),last_checked_at=VALUES(last_checked_at);""")
w(f"""INSERT INTO media_titles (media_id,language_code,title_type,title,is_primary,source)
SELECT media_id,'de','display',title,1,'justwatch' FROM {ST} WHERE media_id IS NOT NULL
ON DUPLICATE KEY UPDATE is_primary=GREATEST(is_primary,VALUES(is_primary)),source=VALUES(source);""")
w(f"""INSERT INTO media_titles (media_id,language_code,title_type,title,is_primary,source)
SELECT media_id,'und','original',original_title,0,'justwatch' FROM {ST}
WHERE media_id IS NOT NULL AND original_title IS NOT NULL AND original_title<>'' AND original_title<>title
ON DUPLICATE KEY UPDATE is_primary=GREATEST(is_primary,VALUES(is_primary)),source=VALUES(source);""")
seed=',\n'.join(f"({q(slug)},{q(name)})" for slug,name in GENRE_MAP.values())
w("INSERT INTO genres (slug,name) VALUES\n"+seed+"\nON DUPLICATE KEY UPDATE name=VALUES(name);")
w(f"""INSERT INTO media_genres (media_id,genre_id)
SELECT s.media_id,g.id FROM {ST} s JOIN genres g ON FIND_IN_SET(g.slug,s.genre_csv)>0
WHERE s.media_id IS NOT NULL AND s.genre_csv<>''
ON DUPLICATE KEY UPDATE media_id=VALUES(media_id);""")
w(f"""INSERT INTO media_assets (media_id,asset_type,language_code,url,source,is_primary,sort_order,last_checked_at,removed_at)
SELECT s.media_id,'poster',NULL,s.poster_url,'justwatch',1,10,@w2w_now,NULL FROM {ST} s
LEFT JOIN media_assets a ON a.media_id=s.media_id AND a.asset_type='poster' AND a.removed_at IS NULL
WHERE s.media_id IS NOT NULL AND s.poster_url IS NOT NULL AND a.id IS NULL;""")
w(f"""INSERT INTO media_availability (media_id,provider_id,country_code,offer_type,added_at,removed_at,web_url,deeplink_url,last_checked_at)
SELECT media_id,@w2w_prime_provider,'DE','subscription',CURDATE(),NULL,web_url,web_url,@w2w_now FROM {ST} WHERE media_id IS NOT NULL
ON DUPLICATE KEY UPDATE removed_at=NULL,web_url=VALUES(web_url),deeplink_url=VALUES(deeplink_url),last_checked_at=VALUES(last_checked_at);""")
w(f"""INSERT INTO media_availability_reconcile (media_id,provider_id,country_code,offer_type,source,status,consecutive_misses,first_seen_at,last_seen_at,last_checked_at,external_url,live_provider_name,note)
SELECT media_id,@w2w_prime_provider,'DE','subscription','justwatch','confirmed',0,@w2w_now,@w2w_now,@w2w_now,web_url,'Amazon Prime Video','Complete Amazon Prime Video DE snapshot 2026-09-02; exact amp FLATRATE 9016/9016'
FROM {ST} WHERE media_id IS NOT NULL
ON DUPLICATE KEY UPDATE status='confirmed',consecutive_misses=0,first_seen_at=COALESCE(first_seen_at,VALUES(first_seen_at)),last_seen_at=VALUES(last_seen_at),last_checked_at=VALUES(last_checked_at),external_url=VALUES(external_url),live_provider_name=VALUES(live_provider_name),note=VALUES(note);""")
w(f"""INSERT INTO media_source_records (media_id,source,source_record_id,payload_hash,imported_at,last_checked_at,status)
SELECT media_id,'justwatch-prime-de',jw_id,payload_hash,@w2w_now,@w2w_now,'active' FROM {ST} WHERE media_id IS NOT NULL
ON DUPLICATE KEY UPDATE source_record_id=VALUES(source_record_id),payload_hash=VALUES(payload_hash),last_checked_at=VALUES(last_checked_at),status='active';""")
w(f"""UPDATE media_availability a
JOIN media_source_records sr ON sr.media_id=a.media_id AND sr.source='justwatch-prime-de'
LEFT JOIN {ST} s ON s.media_id=a.media_id
SET a.removed_at=CURDATE(),a.last_checked_at=@w2w_now
WHERE a.provider_id=@w2w_prime_provider AND a.country_code='DE' AND a.offer_type='subscription'
  AND a.removed_at IS NULL AND s.media_id IS NULL;""")
w(f"""UPDATE media_availability_reconcile ar
JOIN media_source_records sr ON sr.media_id=ar.media_id AND sr.source='justwatch-prime-de'
LEFT JOIN {ST} s ON s.media_id=ar.media_id
SET ar.status='remove_ready',ar.consecutive_misses=3,ar.last_checked_at=@w2w_now,
    ar.note='Not present in complete Amazon Prime Video DE snapshot 2026-09-02'
WHERE ar.provider_id=@w2w_prime_provider AND ar.country_code='DE' AND ar.offer_type='subscription'
  AND ar.source='justwatch' AND s.media_id IS NULL;""")
w(f"""UPDATE media_source_records sr LEFT JOIN {ST} s ON s.media_id=sr.media_id
SET sr.status='removed',sr.last_checked_at=@w2w_now
WHERE sr.source='justwatch-prime-de' AND s.media_id IS NULL;""")
w(f"""SELECT 9016 expected_snapshot_records,COUNT(*) staged_records,SUM(media_id IS NOT NULL) mapped_records,
COUNT(DISTINCT media_id) distinct_canonical_media,SUM(match_source='created') newly_created,
SUM(match_source<>'created') matched_existing,SUM(media_id IS NULL) unresolved FROM {ST};""")
w("""SELECT COUNT(*) active_prime_de_subscription_rows FROM media_availability
WHERE provider_id=@w2w_prime_provider AND country_code='DE' AND offer_type='subscription' AND removed_at IS NULL;""")
w(f"DROP TABLE IF EXISTS {ST};")

sql='\n\n'.join(lines)+'\n'

def split_sql(text):
    out=[]; buf=[]; ins=False; inc=False; i=0
    while i<len(text):
        ch=text[i]; nx=text[i+1] if i+1<len(text) else ''
        if inc:
            buf.append(ch)
            if ch=='*' and nx=='/': buf.append(nx); i+=2; inc=False; continue
            i+=1; continue
        if not ins and ch=='/' and nx=='*': buf.extend([ch,nx]); i+=2; inc=True; continue
        if ch=="'":
            buf.append(ch)
            if ins and nx=="'": buf.append(nx); i+=2; continue
            ins=not ins; i+=1; continue
        if ch==';' and not ins:
            buf.append(ch); s=''.join(buf).strip()
            if s: out.append(s)
            buf=[]; i+=1; continue
        buf.append(ch); i+=1
    assert not ins and not inc
    tail=''.join(buf).strip()
    if tail: out.append(tail)
    return out

stmts=split_sql(sql)
assert len(stmts)==71
assert max(len(x.encode('utf-8')) for x in stmts)<120000
assert 'TEMPORARY TABLE' not in sql.upper()
assert 'INSERT IGNORE' not in sql.upper()
assert not re.search(r'\bJOIN\b[^\n;]*\bCOLLATE\b',sql,re.I)
assert 'COUNT(*) FROM w2w_amp_20260902_stage' not in sql

OUT_SQL.write_text(sql,encoding='utf-8',newline='\n')
with gzip.open(OUT_GZ,'wt',encoding='utf-8',compresslevel=9,newline='\n') as f: f.write(sql)
with gzip.open(OUT_GZ,'rt',encoding='utf-8') as f: assert f.read()==sql
print(json.dumps({
 'records':len(stage),'imdb_keys':sum(bool(x['imdb_id_key']) for x in stage),
 'posters':sum(bool(x['poster_url']) for x in stage),'sql_statements':len(stmts),
 'max_statement_bytes':max(len(x.encode('utf-8')) for x in stmts),
 'sql_bytes':OUT_SQL.stat().st_size,'gzip_bytes':OUT_GZ.stat().st_size,
 'sha256_gz':hashlib.sha256(OUT_GZ.read_bytes()).hexdigest(),
 'no_collate_joins':True,'no_correlated_identity_subqueries':True,
 'no_temporary_tables':True,'no_insert_ignore':True,'gzip_roundtrip':True
},indent=2))
