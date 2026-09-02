#!/usr/bin/env python3
"""Build the Apple TV DE import using the MariaDB-tested FAST+SAFE provider-import template."""
from pathlib import Path

src=Path(__file__).with_name('build_prime_fast_safe_sql.py').read_text(encoding='utf-8')
repls=[
("Amazon Prime Video DE FAST+SAFE","Apple TV DE FAST+SAFE"),
("Coverage: 9016/9016 verified JustWatch Amazon Prime Video DE exact amp FLATRATE records","Coverage: 333/333 verified JustWatch Apple TV DE exact atp FLATRATE records"),
("report['reported_total']==report['enumerated_unique']==report['verified']==9016","report['reported_total']==report['enumerated_unique']==report['verified']==333"),
("report['justwatch_package']['shortName']=='amp'","report['justwatch_package']['shortName']=='atp'"),
("len(records)==9016","len(records)==333"),
("len({r['justwatch_id'] for r in records})==9016","len({r['justwatch_id'] for r in records})==333"),
("len({r['full_path'] for r in records})==9016","len({r['full_path'] for r in records})==333"),
("if host=='watch.amazon.de': return 0\n        if host=='www.primevideo.com': return 1\n        if host.endswith('amazon.de'): return 2\n        return 3","if host=='tv.apple.com': return 0\n        if host.endswith('apple.com'): return 1\n        return 2"),
("assert len(stage)==9016","assert len(stage)==333"),
("assert sum(bool(x['imdb_id_key']) for x in stage)==8719","assert sum(bool(x['imdb_id_key']) for x in stage)==328"),
("assert sum(bool(x['poster_url']) for x in stage)==8963","assert sum(bool(x['poster_url']) for x in stage)==333"),
("INSERT INTO providers (slug,name) VALUES ('prime','Prime Video')","INSERT INTO providers (slug,name) VALUES ('apple','Apple TV')"),
("@w2w_prime_provider","@w2w_apple_provider"),
("WHERE slug='prime'","WHERE slug='apple'"),
("VALUES (@w2w_apple_provider,'justwatch','amp','Amazon Prime Video',@w2w_now)","VALUES (@w2w_apple_provider,'justwatch','atp','Apple TV',@w2w_now)"),
("ST='w2w_amp_20260902_stage'","ST='w2w_atp_20260902_stage'"),
("uq_w2w_amp_slug","uq_w2w_atp_slug"),
("idx_w2w_amp_path","idx_w2w_atp_path"),
("idx_w2w_amp_imdb","idx_w2w_atp_imdb"),
("idx_w2w_amp_media","idx_w2w_atp_media"),
("'Amazon Prime Video','Complete Amazon Prime Video DE snapshot 2026-09-02; exact amp FLATRATE 9016/9016'","'Apple TV','Complete Apple TV DE snapshot 2026-09-02; exact atp FLATRATE 333/333'"),
("'justwatch-prime-de'","'justwatch-apple-tv-de'"),
("'Not present in complete Amazon Prime Video DE snapshot 2026-09-02'","'Not present in complete Apple TV DE snapshot 2026-09-02'"),
("SELECT 9016 expected_snapshot_records","SELECT 333 expected_snapshot_records"),
("active_prime_de_subscription_rows","active_apple_de_subscription_rows"),
("COUNT(*) FROM w2w_amp_20260902_stage","COUNT(*) FROM w2w_atp_20260902_stage"),
("assert len(stmts)==71","assert len(stmts)==36"),
]
for old,new in repls:
    if old not in src:
        raise RuntimeError('Apple builder template token missing: '+old[:100])
    src=src.replace(old,new)
exec(compile(src,'build_apple_fast_safe_sql.generated.py','exec'),globals(),globals())
