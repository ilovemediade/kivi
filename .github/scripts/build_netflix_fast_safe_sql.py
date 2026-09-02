import json, re, hashlib, gzip, os
from pathlib import Path
from collections import Counter

import sys
CAT = Path(sys.argv[1] if len(sys.argv) > 1 else 'netflix-de-catalog.json')
OUT_SQL = Path(sys.argv[2] if len(sys.argv) > 2 else 'what2watch-netflix-de-8397-FAST-SAFE.sql')
OUT_GZ = OUT_SQL.with_suffix(OUT_SQL.suffix + '.gz')

data = json.loads(CAT.read_text(encoding='utf-8'))
records = data['records']
assert len(records) == 8397

GENRE_MAP = {
    'act': ('action', 'Action & Adventure'),
    'ani': ('animation', 'Animation'),
    'cmy': ('comedy', 'Comedy'),
    'crm': ('crime', 'Crime'),
    'doc': ('documentary', 'Documentary'),
    'drm': ('drama', 'Drama'),
    'eur': ('european', 'European'),
    'fml': ('family', 'Family'),
    'fnt': ('fantasy', 'Fantasy'),
    'hrr': ('horror', 'Horror'),
    'hst': ('history', 'History'),
    'msc': ('music', 'Music'),
    'rly': ('reality-tv', 'Reality TV'),
    'rma': ('romance', 'Romance'),
    'scf': ('science-fiction', 'Science Fiction'),
    'spt': ('sport', 'Sport'),
    'trl': ('mystery-thriller', 'Mystery & Thriller'),
    'war': ('war-military', 'War & Military'),
    'wsn': ('western', 'Western'),
}

def netflix_offer(rec):
    matches=[]
    for o in rec.get('offers') or []:
        p=o.get('package') or {}
        if o.get('monetization_type')=='FLATRATE' and p.get('shortName')=='nfx':
            url=(o.get('web_url') or '').strip()
            if url:
                matches.append(url)
    assert matches, rec['justwatch_id']
    url=matches[0]
    m=re.search(r'netflix\.com/(?:[^/]+/)?title/(\d+)', url)
    assert m, (rec['justwatch_id'], url)
    return url, m.group(1)

nf = {}
for r in records:
    url,nid=netflix_offer(r)
    nf[r['justwatch_id']] = (url,nid)

nf_counts=Counter(nid for _,nid in nf.values())
imdb_counts=Counter(r['imdb_id'] for r in records if r.get('imdb_id'))

assert len({r['justwatch_id'] for r in records}) == 8397
assert len({r['full_path'] for r in records}) == 8397
assert all(r.get('verification') == 'verified' for r in records)
assert all(r.get('title') for r in records)
assert all(r.get('object_type') in ('MOVIE','SHOW') for r in records)

def q(v):
    if v is None:
        return 'NULL'
    s=str(v).replace('\\','\\\\').replace("'","''").replace('\r',' ').replace('\n',' ')
    return "'"+s+"'"

def n(v):
    return 'NULL' if v is None else str(int(v))

def poster_url(tpl):
    if not tpl:
        return None
    s=tpl.replace('{profile}','s718').replace('{format}','jpg')
    if not s.startswith('/'):
        s='/'+s
    return 'https://images.justwatch.com'+s

stage=[]
genre_rows=[]
for r in records:
    jw_id=r['justwatch_id']
    path=r['full_path']
    url,nid_raw=nf[jw_id]
    imdb_raw=r.get('imdb_id') or None
    nid_key=nid_raw if nf_counts[nid_raw]==1 else None
    imdb_key=imdb_raw if imdb_raw and imdb_counts[imdb_raw]==1 else None
    path_key=path if len(path)<=128 else None
    media_type='movie' if r['object_type']=='MOVIE' else 'series'
    slug='jw-'+jw_id
    payload='|'.join([jw_id,path,imdb_raw or '',r['title'],str(r.get('year') or ''),url])
    ph=hashlib.sha256(payload.encode('utf-8')).hexdigest()
    stage.append({
        'jw_id':jw_id,'jw_path':path,'jw_path_key':path_key,'jw_slug':slug,
        'netflix_id_raw':nid_raw,'netflix_id_key':nid_key,
        'imdb_id_raw':imdb_raw,'imdb_id_key':imdb_key,
        'media_type':media_type,'title':r['title'],'original_title':r.get('original_title') or None,
        'release_year':r.get('year'),'runtime_minutes':r.get('runtime'),
        'poster_url':poster_url(r.get('poster_url')),'web_url':url,'payload_hash':ph,
    })
    for code in r.get('genres') or []:
        if code not in GENRE_MAP:
            raise AssertionError(f'Unknown genre code {code} for {jw_id}')
        genre_rows.append((jw_id, GENRE_MAP[code][0]))

assert len(stage)==8397
assert len({x['jw_id'] for x in stage})==8397
assert len({x['jw_slug'] for x in stage})==8397
assert sum(1 for x in stage if x['netflix_id_key'])==8393
assert sum(1 for x in stage if x['imdb_id_raw'])==8024
assert sum(1 for x in stage if x['imdb_id_key'])==8022
assert sum(1 for x in stage if x['jw_path_key'] is None)==1
assert len(genre_rows)==len(set(genre_rows))

lines=[]
w=lines.append
w("/* what2watch Netflix DE FAST+SAFE import\n"
  "   Snapshot: 2026-09-01\n"
  "   Source coverage: 8397/8397 verified JustWatch Netflix-DE nfx FLATRATE records\n"
  "   Optimized for MariaDB 10.6 / phpMyAdmin: indexed single-stage identity resolution, no COLLATE joins, no correlated identity subqueries.\n"
  "*/")
w("SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;")
w("SET @w2w_now := NOW();")
w("INSERT INTO providers (slug,name) VALUES ('netflix','Netflix') ON DUPLICATE KEY UPDATE name=VALUES(name);")
w("SET @w2w_netflix_provider := (SELECT id FROM providers WHERE slug='netflix' LIMIT 1);")
w("INSERT INTO provider_external_ids (provider_id,source,external_id,external_name,last_checked_at) VALUES (@w2w_netflix_provider,'justwatch','nfx','Netflix',@w2w_now) ON DUPLICATE KEY UPDATE external_name=VALUES(external_name),last_checked_at=VALUES(last_checked_at);")

ST='w2w_nfx_20260902_stage'
SG='w2w_nfx_20260902_genres'
w(f"DROP TABLE IF EXISTS {SG};")
w(f"DROP TABLE IF EXISTS {ST};")
w(f"""CREATE TABLE {ST} (
  jw_id VARCHAR(32) NOT NULL,
  jw_path VARCHAR(512) NOT NULL,
  jw_path_key VARCHAR(128) NULL,
  jw_slug VARCHAR(190) NOT NULL,
  netflix_id_raw VARCHAR(32) NOT NULL,
  netflix_id_key VARCHAR(32) NULL,
  imdb_id_raw VARCHAR(32) NULL,
  imdb_id_key VARCHAR(32) NULL,
  media_type ENUM('movie','series') NOT NULL,
  title VARCHAR(255) NOT NULL,
  original_title VARCHAR(512) NULL,
  release_year SMALLINT UNSIGNED NULL,
  runtime_minutes SMALLINT UNSIGNED NULL,
  poster_url VARCHAR(1024) NULL,
  web_url VARCHAR(1024) NOT NULL,
  payload_hash CHAR(64) NOT NULL,
  media_id BIGINT UNSIGNED NULL,
  match_source VARCHAR(32) NULL,
  PRIMARY KEY (jw_id),
  UNIQUE KEY uq_w2w_nfx_slug (jw_slug),
  KEY idx_w2w_nfx_path (jw_path_key),
  KEY idx_w2w_nfx_netflix (netflix_id_key),
  KEY idx_w2w_nfx_imdb (imdb_id_key),
  KEY idx_w2w_nfx_media (media_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;""")

cols=['jw_id','jw_path','jw_path_key','jw_slug','netflix_id_raw','netflix_id_key','imdb_id_raw','imdb_id_key','media_type','title','original_title','release_year','runtime_minutes','poster_url','web_url','payload_hash','media_id','match_source']

def stage_tuple(x):
    vals=[q(x['jw_id']),q(x['jw_path']),q(x['jw_path_key']),q(x['jw_slug']),q(x['netflix_id_raw']),q(x['netflix_id_key']),q(x['imdb_id_raw']),q(x['imdb_id_key']),q(x['media_type']),q(x['title']),q(x['original_title']),n(x['release_year']),n(x['runtime_minutes']),q(x['poster_url']),q(x['web_url']),q(x['payload_hash']),'NULL','NULL']
    return '('+','.join(vals)+')'

BATCH=250
for i in range(0,len(stage),BATCH):
    chunk=stage[i:i+BATCH]
    w(f"INSERT INTO {ST} ({','.join(cols)}) VALUES\n" + ',\n'.join(stage_tuple(x) for x in chunk) + ';')

w(f"""CREATE TABLE {SG} (
  jw_id VARCHAR(32) NOT NULL,
  genre_slug VARCHAR(100) NOT NULL,
  PRIMARY KEY (jw_id,genre_slug),
  KEY idx_w2w_nfx_genre_slug (genre_slug)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;""")
for i in range(0,len(genre_rows),500):
    chunk=genre_rows[i:i+500]
    w(f"INSERT INTO {SG} (jw_id,genre_slug) VALUES\n" + ',\n'.join(f"({q(a)},{q(b)})" for a,b in chunk) + ';')

w(f"UPDATE {ST} s JOIN media_external_ids e ON e.source='justwatch-node' AND e.external_id=s.jw_id SET s.media_id=e.media_id,s.match_source='justwatch-node' WHERE s.media_id IS NULL;")
w(f"UPDATE {ST} s JOIN media_external_ids e ON e.source='justwatch' AND e.external_id=s.jw_path_key SET s.media_id=e.media_id,s.match_source='justwatch-path' WHERE s.media_id IS NULL AND s.jw_path_key IS NOT NULL;")
w(f"UPDATE {ST} s JOIN media_external_ids e ON e.source='netflix' AND e.external_id=s.netflix_id_key SET s.media_id=e.media_id,s.match_source='netflix' WHERE s.media_id IS NULL AND s.netflix_id_key IS NOT NULL;")
w(f"UPDATE {ST} s JOIN media_external_ids e ON e.source='imdb' AND e.external_id=s.imdb_id_key SET s.media_id=e.media_id,s.match_source='imdb' WHERE s.media_id IS NULL AND s.imdb_id_key IS NOT NULL;")
w(f"UPDATE {ST} s JOIN media m ON m.slug=s.jw_slug SET s.media_id=m.id,s.match_source='jw-slug' WHERE s.media_id IS NULL;")

w(f"""INSERT INTO media (slug,title,title_de,original_title,media_type,year,runtime_minutes,poster_url,imdb_id,german_available,is_active)
SELECT s.jw_slug,s.title,s.title,s.original_title,s.media_type,s.release_year,s.runtime_minutes,s.poster_url,s.imdb_id_key,0,1
FROM {ST} s
WHERE s.media_id IS NULL;""")
w(f"UPDATE {ST} s JOIN media m ON m.slug=s.jw_slug SET s.media_id=m.id,s.match_source='created' WHERE s.media_id IS NULL;")

w(f"""UPDATE media m JOIN {ST} s ON s.media_id=m.id
SET m.title=COALESCE(NULLIF(m.title,''),s.title),
    m.title_de=COALESCE(NULLIF(m.title_de,''),s.title),
    m.original_title=COALESCE(NULLIF(m.original_title,''),s.original_title),
    m.year=COALESCE(m.year,s.release_year),
    m.runtime_minutes=COALESCE(m.runtime_minutes,s.runtime_minutes),
    m.poster_url=COALESCE(NULLIF(m.poster_url,''),s.poster_url),
    m.imdb_id=COALESCE(NULLIF(m.imdb_id,''),s.imdb_id_key),
    m.is_active=1
WHERE s.media_id IS NOT NULL;""")

w(f"INSERT IGNORE INTO media_external_ids (media_id,source,external_id,canonical_url,last_checked_at) SELECT s.media_id,'justwatch-node',s.jw_id,CONCAT('https://www.justwatch.com',s.jw_path),@w2w_now FROM {ST} s WHERE s.media_id IS NOT NULL;")
w(f"INSERT IGNORE INTO media_external_ids (media_id,source,external_id,canonical_url,last_checked_at) SELECT s.media_id,'justwatch',s.jw_path_key,CONCAT('https://www.justwatch.com',s.jw_path),@w2w_now FROM {ST} s WHERE s.media_id IS NOT NULL AND s.jw_path_key IS NOT NULL;")
w(f"INSERT IGNORE INTO media_external_ids (media_id,source,external_id,canonical_url,last_checked_at) SELECT s.media_id,'imdb',s.imdb_id_key,CONCAT('https://www.imdb.com/title/',s.imdb_id_key,'/'),@w2w_now FROM {ST} s WHERE s.media_id IS NOT NULL AND s.imdb_id_key IS NOT NULL;")
w(f"INSERT IGNORE INTO media_external_ids (media_id,source,external_id,canonical_url,last_checked_at) SELECT s.media_id,'netflix',s.netflix_id_key,s.web_url,@w2w_now FROM {ST} s WHERE s.media_id IS NOT NULL AND s.netflix_id_key IS NOT NULL;")

w(f"INSERT IGNORE INTO media_titles (media_id,language_code,title_type,title,is_primary,source) SELECT s.media_id,'de','display',s.title,1,'justwatch' FROM {ST} s WHERE s.media_id IS NOT NULL;")
w(f"INSERT IGNORE INTO media_titles (media_id,language_code,title_type,title,is_primary,source) SELECT s.media_id,'und','original',s.original_title,0,'justwatch' FROM {ST} s WHERE s.media_id IS NOT NULL AND s.original_title IS NOT NULL AND s.original_title<>'' AND s.original_title<>s.title;")

seed=',\n'.join(f"({q(slug)},{q(name)})" for slug,name in GENRE_MAP.values())
w("INSERT INTO genres (slug,name) VALUES\n"+seed+"\nON DUPLICATE KEY UPDATE name=VALUES(name);")
w(f"INSERT IGNORE INTO media_genres (media_id,genre_id) SELECT s.media_id,g.id FROM {SG} sg JOIN {ST} s ON s.jw_id=sg.jw_id JOIN genres g ON g.slug=sg.genre_slug WHERE s.media_id IS NOT NULL;")

w(f"""INSERT INTO media_assets (media_id,asset_type,language_code,url,source,is_primary,sort_order,last_checked_at,removed_at)
SELECT s.media_id,'poster',NULL,s.poster_url,'justwatch',1,10,@w2w_now,NULL
FROM {ST} s
LEFT JOIN media_assets a ON a.media_id=s.media_id AND a.asset_type='poster' AND a.removed_at IS NULL
WHERE s.media_id IS NOT NULL AND s.poster_url IS NOT NULL AND a.id IS NULL;""")

w(f"""INSERT INTO media_availability (media_id,provider_id,country_code,offer_type,added_at,removed_at,web_url,deeplink_url,last_checked_at)
SELECT s.media_id,@w2w_netflix_provider,'DE','subscription',CURDATE(),NULL,s.web_url,s.web_url,@w2w_now
FROM {ST} s WHERE s.media_id IS NOT NULL
ON DUPLICATE KEY UPDATE removed_at=NULL,web_url=VALUES(web_url),deeplink_url=VALUES(deeplink_url),last_checked_at=VALUES(last_checked_at);""")

w(f"""INSERT INTO media_availability_reconcile (media_id,provider_id,country_code,offer_type,source,status,consecutive_misses,first_seen_at,last_seen_at,last_checked_at,external_url,live_provider_name,note)
SELECT s.media_id,@w2w_netflix_provider,'DE','subscription','justwatch','confirmed',0,@w2w_now,@w2w_now,@w2w_now,s.web_url,'Netflix','Complete Netflix DE snapshot 2026-09-01; JustWatch nfx FLATRATE 8397/8397'
FROM {ST} s WHERE s.media_id IS NOT NULL
ON DUPLICATE KEY UPDATE status='confirmed',consecutive_misses=0,first_seen_at=COALESCE(first_seen_at,VALUES(first_seen_at)),last_seen_at=VALUES(last_seen_at),last_checked_at=VALUES(last_checked_at),external_url=VALUES(external_url),live_provider_name=VALUES(live_provider_name),note=VALUES(note);""")

w(f"""INSERT INTO media_source_records (media_id,source,source_record_id,payload_hash,imported_at,last_checked_at,status)
SELECT s.media_id,'justwatch-netflix-de',s.jw_id,s.payload_hash,@w2w_now,@w2w_now,'active'
FROM {ST} s WHERE s.media_id IS NOT NULL
ON DUPLICATE KEY UPDATE source_record_id=VALUES(source_record_id),payload_hash=VALUES(payload_hash),last_checked_at=VALUES(last_checked_at),status='active';""")

w(f"""UPDATE media_availability a
JOIN media_source_records sr ON sr.media_id=a.media_id AND sr.source='justwatch-netflix-de'
LEFT JOIN {ST} s ON s.media_id=a.media_id
SET a.removed_at=CURDATE(),a.last_checked_at=@w2w_now
WHERE a.provider_id=@w2w_netflix_provider AND a.country_code='DE' AND a.offer_type='subscription' AND a.removed_at IS NULL AND s.media_id IS NULL;""")
w(f"""UPDATE media_availability_reconcile ar
JOIN media_source_records sr ON sr.media_id=ar.media_id AND sr.source='justwatch-netflix-de'
LEFT JOIN {ST} s ON s.media_id=ar.media_id
SET ar.status='remove_ready',ar.consecutive_misses=3,ar.last_checked_at=@w2w_now,ar.note='Not present in complete Netflix DE snapshot 2026-09-01'
WHERE ar.provider_id=@w2w_netflix_provider AND ar.country_code='DE' AND ar.offer_type='subscription' AND ar.source='justwatch' AND s.media_id IS NULL;""")
w(f"""UPDATE media_source_records sr
LEFT JOIN {ST} s ON s.media_id=sr.media_id
SET sr.status='removed',sr.last_checked_at=@w2w_now
WHERE sr.source='justwatch-netflix-de' AND s.media_id IS NULL;""")

w(f"""SELECT 8397 AS expected_snapshot_records,
       COUNT(*) AS staged_records,
       SUM(media_id IS NOT NULL) AS mapped_records,
       COUNT(DISTINCT media_id) AS distinct_canonical_media,
       SUM(match_source='created') AS newly_created,
       SUM(match_source<>'created') AS matched_existing,
       SUM(media_id IS NULL) AS unresolved
FROM {ST};""")
w(f"""SELECT COUNT(*) AS active_netflix_de_subscription_rows
FROM media_availability a
WHERE a.provider_id=@w2w_netflix_provider AND a.country_code='DE' AND a.offer_type='subscription' AND a.removed_at IS NULL;""")

w(f"DROP TABLE IF EXISTS {SG};")
w(f"DROP TABLE IF EXISTS {ST};")

sql='\n\n'.join(lines)+'\n'

assert sql.count('COLLATE utf8mb4_unicode_ci') == 1
assert sql.count('COLLATE=utf8mb4_unicode_ci') == 2
assert ' COLLATE utf8mb4_unicode_ci=' not in sql
assert 'COUNT(*) FROM '+ST not in sql
assert 'NOT EXISTS' not in sql.upper()
assert 'TEMPORARY TABLE' not in sql.upper()
assert 'DELETE FROM' not in sql.upper()
assert 'DROP TABLE IF EXISTS w2w_nf_' not in sql

identity_statements=[x for x in lines if x.startswith('UPDATE '+ST+' s JOIN')]
assert len(identity_statements)==6
for st in identity_statements:
    on=st.split(' SET ',1)[0]
    assert 'COLLATE' not in on and 'CONCAT(' not in on and 'CAST(' not in on

assert max(len(x['title']) for x in stage) <= 255
assert max(len(x['original_title'] or '') for x in stage) <= 512
assert max(len(x['jw_id']) for x in stage) <= 32
assert max(len(x['jw_path_key'] or '') for x in stage) <= 128
assert max(len(x['netflix_id_raw']) for x in stage) <= 32
assert max(len(x['imdb_id_raw'] or '') for x in stage) <= 32
assert max(len(x['poster_url'] or '') for x in stage) <= 1024
assert max(len(x['web_url']) for x in stage) <= 1024

allowed={
 'providers':{'slug','name'},
 'provider_external_ids':{'provider_id','source','external_id','external_name','last_checked_at'},
 'media':{'slug','title','title_de','original_title','media_type','year','runtime_minutes','poster_url','imdb_id','german_available','is_active'},
 'media_external_ids':{'media_id','source','external_id','canonical_url','last_checked_at'},
 'media_titles':{'media_id','language_code','title_type','title','is_primary','source'},
 'genres':{'slug','name'},
 'media_genres':{'media_id','genre_id'},
 'media_assets':{'media_id','asset_type','language_code','url','source','is_primary','sort_order','last_checked_at','removed_at'},
 'media_availability':{'media_id','provider_id','country_code','offer_type','added_at','removed_at','web_url','deeplink_url','last_checked_at'},
 'media_availability_reconcile':{'media_id','provider_id','country_code','offer_type','source','status','consecutive_misses','first_seen_at','last_seen_at','last_checked_at','external_url','live_provider_name','note'},
 'media_source_records':{'media_id','source','source_record_id','payload_hash','imported_at','last_checked_at','status'},
}
for m in re.finditer(r'INSERT(?: IGNORE)? INTO\s+([a-zA-Z0-9_]+)\s*\(([^)]*)\)',sql,re.I):
    table=m.group(1)
    if table in (ST,SG):
        continue
    if table not in allowed:
        raise AssertionError('Unknown target table '+table)
    cols2={c.strip() for c in m.group(2).split(',')}
    bad=cols2-allowed[table]
    if bad: raise AssertionError((table,bad))

def split_sql(text):
    out=[];buf=[];ins=False;inc=False;i=0
    while i<len(text):
        ch=text[i];nx=text[i+1] if i+1<len(text) else ''
        if inc:
            buf.append(ch)
            if ch=='*' and nx=='/':buf.append(nx);i+=2;inc=False;continue
            i+=1;continue
        if not ins and ch=='/' and nx=='*':buf.extend([ch,nx]);i+=2;inc=True;continue
        if ch=="'":
            buf.append(ch)
            if ins and nx=="'":buf.append(nx);i+=2;continue
            ins=not ins;i+=1;continue
        if ch==';' and not ins:
            buf.append(ch); st=''.join(buf).strip()
            if st:out.append(st)
            buf=[];i+=1;continue
        buf.append(ch);i+=1
    tail=''.join(buf).strip()
    if tail:out.append(tail)
    assert not ins and not inc
    return out

def balanced(st):
    ins=False;inc=False;bal=0;i=0
    while i<len(st):
        ch=st[i];nx=st[i+1] if i+1<len(st) else ''
        if inc:
            if ch=='*' and nx=='/':i+=2;inc=False;continue
            i+=1;continue
        if not ins and ch=='/' and nx=='*':i+=2;inc=True;continue
        if ch=="'":
            if ins and nx=="'":i+=2;continue
            ins=not ins;i+=1;continue
        if not ins:
            if ch=='(':bal+=1
            elif ch==')':
                bal-=1
                if bal<0:return False
        i+=1
    return bal==0 and not ins and not inc

stmts=split_sql(sql)
assert all(balanced(s) for s in stmts)
assert len(stage)==8397
assert len(genre_rows)>0

OUT_SQL.write_text(sql,encoding='utf-8',newline='\n')
with gzip.open(OUT_GZ,'wt',encoding='utf-8',compresslevel=9,newline='\n') as g:g.write(sql)
with gzip.open(OUT_GZ,'rt',encoding='utf-8') as g:assert g.read()==sql

report={
 'records':len(stage),
 'genre_links':len(genre_rows),
 'unique_netflix_ids':sum(1 for x in stage if x['netflix_id_key']),
 'unique_imdb_ids':sum(1 for x in stage if x['imdb_id_key']),
 'raw_imdb_ids':sum(1 for x in stage if x['imdb_id_raw']),
 'long_justwatch_paths_skipped_as_path_identity':sum(1 for x in stage if x['jw_path_key'] is None),
 'sql_statements':len(stmts),
 'sql_bytes':OUT_SQL.stat().st_size,
 'gzip_bytes':OUT_GZ.stat().st_size,
 'sha256_gz':hashlib.sha256(OUT_GZ.read_bytes()).hexdigest(),
 'no_collate_joins':True,
 'no_correlated_identity_subqueries':True,
 'no_temporary_tables':True,
 'schema_columns_validated':True,
 'gzip_roundtrip':True,
}
print(json.dumps(report,ensure_ascii=False,indent=2))
