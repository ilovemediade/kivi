#!/usr/bin/env python3
"""Build the Disney+ DE import using the already MariaDB-tested FAST+SAFE provider-import template."""
from pathlib import Path

src=Path(__file__).with_name('build_prime_fast_safe_sql.py').read_text(encoding='utf-8')
repls=[
("Amazon Prime Video DE FAST+SAFE","Disney+ DE FAST+SAFE"),
("Coverage: 9016/9016 verified JustWatch Amazon Prime Video DE exact amp FLATRATE records","Coverage: 3545/3545 verified JustWatch Disney+ DE exact dnp FLATRATE records"),
("report['reported_total']==report['enumerated_unique']==report['verified']==9016","report['reported_total']==report['enumerated_unique']==report['verified']==3545"),
("report['justwatch_package']['shortName']=='amp'","report['justwatch_package']['shortName']=='dnp'"),
("len(records)==9016","len(records)==3545"),
("len({r['justwatch_id'] for r in records})==9016","len({r['justwatch_id'] for r in records})==3545"),
("len({r['full_path'] for r in records})==9016","len({r['full_path'] for r in records})==3545"),
("if host=='watch.amazon.de': return 0\n        if host=='www.primevideo.com': return 1\n        if host.endswith('amazon.de'): return 2\n        return 3","if host=='www.disneyplus.com': return 0\n        if host.endswith('disneyplus.com'): return 1\n        return 2"),
("assert len(stage)==9016","assert len(stage)==3545"),
("assert sum(bool(x['imdb_id_key']) for x in stage)==8719","assert sum(bool(x['imdb_id_key']) for x in stage)==3258"),
("assert sum(bool(x['poster_url']) for x in stage)==8963","assert sum(bool(x['poster_url']) for x in stage)==3522"),
("INSERT INTO providers (slug,name) VALUES ('prime','Prime Video')","INSERT INTO providers (slug,name) VALUES ('disney','Disney+')"),
("@w2w_prime_provider","@w2w_disney_provider"),
("WHERE slug='prime'","WHERE slug='disney'"),
("VALUES (@w2w_disney_provider,'justwatch','amp','Amazon Prime Video',@w2w_now)","VALUES (@w2w_disney_provider,'justwatch','dnp','Disney Plus',@w2w_now)"),
("ST='w2w_amp_20260902_stage'","ST='w2w_dnp_20260902_stage'"),
("uq_w2w_amp_slug","uq_w2w_dnp_slug"),
("idx_w2w_amp_path","idx_w2w_dnp_path"),
("idx_w2w_amp_imdb","idx_w2w_dnp_imdb"),
("idx_w2w_amp_media","idx_w2w_dnp_media"),
("'Amazon Prime Video','Complete Amazon Prime Video DE snapshot 2026-09-02; exact amp FLATRATE 9016/9016'","'Disney Plus','Complete Disney+ DE snapshot 2026-09-02; exact dnp FLATRATE 3545/3545'"),
("'justwatch-prime-de'","'justwatch-disney-plus-de'"),
("'Not present in complete Amazon Prime Video DE snapshot 2026-09-02'","'Not present in complete Disney+ DE snapshot 2026-09-02'"),
("SELECT 9016 expected_snapshot_records","SELECT 3545 expected_snapshot_records"),
("active_prime_de_subscription_rows","active_disney_de_subscription_rows"),
("COUNT(*) FROM w2w_amp_20260902_stage","COUNT(*) FROM w2w_dnp_20260902_stage"),
("assert len(stmts)==71","assert len(stmts)==49"),
]
for old,new in repls:
    if old not in src:
        raise RuntimeError('Disney builder template token missing: '+old[:100])
    src=src.replace(old,new)
exec(compile(src,'build_disney_fast_safe_sql.generated.py','exec'),globals(),globals())
