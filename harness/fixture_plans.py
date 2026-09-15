"""Initial source translations only. No oracle imports or task answers.

Facts not explicitly mapped below remain verbatim in the source packet. Values
required by SQLite but absent from the episode are declared adapter placeholders
or native defaults, never business evidence. No post-task SQL is permitted.
"""
import hashlib
import json
import sqlite3
from pathlib import Path


def prepare_database(app: Path, scenario: Path, destination: Path):
    facts = json.loads((scenario / 'input/stage-1/fixtures.json').read_text())
    sid = facts['scenario_id']
    statements = {r['id']: r['statement'] for r in facts['records']}
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise ValueError('Refusing to replace an existing fixture database')
    db = sqlite3.connect(destination)
    db.execute('PRAGMA foreign_keys=ON')
    db.executescript((app / 'server/db/schema.sql').read_text())
    mappings = []
    ids = {}

    def row(table, key, values, source, placeholders=None):
        refs = [f'{sid}-F{n}' for n in source]
        if not refs or any(r not in statements for r in refs):
            raise ValueError(f'Invalid public source refs: {refs}')
        columns = ','.join('"' + k + '"' for k in values)
        marks = ','.join('?' for _ in values)
        cursor = db.execute(f'INSERT INTO "{table}" ({columns}) VALUES ({marks})', list(values.values()))
        ids[key] = cursor.lastrowid
        info = db.execute(f'PRAGMA table_info("{table}")').fetchall()
        defaults = {c[1]: c[4] for c in info if c[1] not in values and c[4] is not None}
        mappings.append(dict(table=table, id=cursor.lastrowid, key=key,
                             supplied_values=values, source_refs=refs,
                             source_statements={r: statements[r] for r in refs},
                             adapter_placeholders=placeholders or {}, native_defaults=defaults))
        return cursor.lastrowid

    # Login identities are harness-only duty roles. Their software permissions
    # confer no episode authority. Administrator credentials are not provisioned.
    # These are accounts, not new approved work/resource allocations.
    salt = hashlib.sha256((sid + ':pilot-account').encode()).hexdigest()[:32]
    password_hash = salt + ':' + hashlib.scrypt(b'frostline', salt=salt.encode(), n=16384, r=8, p=1, dklen=32).hex()
    roles = ['coordinator', 'manager', 'sales', 'stores', 'engineer']
    accounts = []
    for role in roles:
        email = f'{role}@pilot.invalid'
        uid = db.execute('INSERT INTO users(name,email,password_hash,role,job_title) VALUES(?,?,?,?,?)',
                         (f'Pilot duty role: {role}', email, password_hash, role,
                          'Sandbox account; use only episode-established authority')).lastrowid
        accounts.append(dict(id=uid, role=role, email=email, password='frostline',
                             authority='None supplied by this account; episode evidence governs every action'))

    def customer(name, source, **values):
        key = 'customer:' + name
        return row('customers', key, dict(account_no=f'{sid}-{len(ids)+1}', name=name, **values), source,
                   {'account_no': 'Stable sandbox reference, not a customer-issued identifier'})

    def site(name, customer_id, source, **values):
        return row('sites', 'site:' + name, dict(name=name, customer_id=customer_id, **values), source)

    def asset(tag, site_id, source, **values):
        return row('assets', 'asset:' + tag, dict(tag=tag, site_id=site_id,
                   category='unspecified-source-category', **values), source,
                   {'category': 'Schema requires a category; none established in source. Does not assert competence or plant type.'})

    def engineer(name, source, **values):
        # A named engineer login is linked faithfully, without adding tickets,
        # skills or certification expiry dates absent from the episode.
        email = name.lower().replace(' ', '.') + '@pilot.invalid'
        uid = db.execute('INSERT INTO users(name,email,password_hash,role,job_title) VALUES(?,?,?,?,?)',
                         (name,email,password_hash,'engineer','Source-named engineer; source controls scope')).lastrowid
        accounts.append(dict(id=uid, role='engineer', name=name, email=email, password='frostline', authority='See episode source'))
        return row('engineers', 'engineer:' + name, dict(name=name,user_id=uid,
                   notes='Competence, authorisation, availability and restrictions: see exact episode source. Empty skill/ticket fields do not establish absence.', **values), source)

    # Native pre-state is intentionally conservative: no newly approved
    # quotations, mobilisation, work completion, custody release or invoice.
    if sid == 'B001':
        c = customer('Northbank Property Holdings Ltd', [1], status='active')
        s = site('Northbank House', c, [1], town='Manchester')
        row('contacts','contact:Priya Shah',dict(customer_id=c,site_id=s,name='Priya Shah',job_title='Facilities manager'),[1,5])
        engineer('Samir',[4]); engineer('Ellie',[4])
    elif sid == 'B002':
        c = customer('Willow Foods Ltd',[1])
        s = site('Willow Bakery',c,[1],town='Bolton')
        row('contacts','contact:Jo',dict(customer_id=c,site_id=s,name='Jo',job_title='Site manager',notes=statements[sid+'-F1']),[1])
        a = asset('A-W2',s,[2],status='faulty')
        e = engineer('Mae',[3])
        # The quotation/appointment/stock reservation are supplied pre-state,
        # not operator-created actions. No price allocation to individual parts
        # is inferred from the inclusive accepted total.
        q = row('quotes','quote:Q-W2-r2',dict(quote_no='Q-W2 revision 2',customer_id=c,site_id=s,title='Specified condensate pump replacement',status='accepted',scope=statements[sid+'-F2']),[2])
        row('quote_lines','quote-total',dict(quote_id=q,kind='other',description='Source accepted inclusive total; no component allocation supplied',qty=1,unit_price=420),[2],{'unit_cost':'Native zero default is not an established cost'})
        j = row('jobs','job:approved-repair',dict(job_no=sid+'-SOURCE',customer_id=c,site_id=s,kind='quoted',title='Approved A-W2 pump repair',status='scheduled',charge_type='quoted',quote_id=q,description=statements[sid+'-F2']+'\n'+statements[sid+'-F3']),[2,3],{'job_no':'Stable harness reference; no job number supplied'})
        db.execute('INSERT INTO job_assets VALUES(?,?)',(j,a))
        # No dated native visit is fabricated from the relative Tuesday slot.
    elif sid == 'B003':
        c = customer('Cedar Academy Trust',[1])
        s = site('Manchester campus',c,[1],town='Manchester')
        asset('AHU-1',s,[1,2]); asset('AHU-2',s,[1,3])
        # Do not resolve duplicate B-1 physical identity by choosing one row.
        engineer('Arun',[2,4])
    elif sid == 'B004':
        c = customer('Alder Care Ltd',[1])
        site('Site D',c,[1,2])
    elif sid == 'B006':
        engineer('Rae',[2]); engineer('Ben',[2,3]); engineer('Kit',[3],grade='apprentice'); engineer('Noor',[3],grade='senior')
    elif sid == 'B007':
        customer('Brook Hotel Ltd',[1],on_stop=1,on_stop_reason='Finance-controlled stop for serious overdue debt; see source limited emergency authority')
        engineer('Lee',[2])
    elif sid == 'B008':
        customer('Harbour Tenant Ltd',[2]); customer('Harbour Estates Ltd',[2])
        # Do not choose a payer/site customer link while it is disputed.
    elif sid == 'B014':
        row('suppliers','supplier:S-Fast',dict(name='S-Fast',notes=statements[sid+'-F2']),[2])
    elif sid == 'B016':
        customer('Lake Group',[1]); engineer('Dana',[2]); engineer('Omar',[2])
        # Native stock has no custody/reservation representation; do not load
        # encumbered or unverified quantities as freely available stock.
    elif sid == 'B021':
        engineer('Eli',[2],grade='senior'); engineer('Fen',[2],grade='apprentice'); engineer('Gia',[3])
    elif sid == 'B026':
        engineer('Rina',[3]); engineer('Sol',[3])

    # Full initial source is in the native inbox as well as the operator source
    # portal. It is marked as supplied material, not a candidate decision.
    packet = (scenario / 'input/stage-1/case.md').read_text()
    row('enquiries','source-packet',dict(channel='web',subject=f'{sid} supplied initial source records',
        body=packet,received_at='2026-09-15T00:00:00Z',status='new'),list(range(1,len(statements)+1)),
        {'channel':'Harness source delivery, not an asserted customer communication channel',
         'received_at':'Harness receipt metadata, not contractual desk receipt or episode clock start',
         'status':'Source packet unread state, not a business task outcome'})

    db.commit()
    integrity = db.execute('PRAGMA integrity_check').fetchone()[0]
    foreign_keys = db.execute('PRAGMA foreign_key_check').fetchall()
    db.close()
    if integrity != 'ok' or foreign_keys:
        raise ValueError('Invalid initial database')
    mapped = {ref for m in mappings if m['table'] != 'enquiries' for ref in m['source_refs']}
    return dict(scenario_id=sid, strategy='Conservative native pre-state plus full verbatim source packet',
                accounts=accounts, mappings=mappings, source_only=[
                    dict(id=r['id'],statement=r['statement'],reason='Preserved verbatim; no exact complete native translation without unestablished fields or semantic loss')
                    for r in facts['records']],
                material_limits=[
                    'Mapped rows are partial projections; the complete source packet remains authoritative.',
                    'Native schema defaults and required placeholders are not established business facts.',
                    'Skills, certification dates, rate breakdowns and relative appointment dates are not invented.',
                    'Source-supported business operations remain available through normal app interaction; this is not a claim that source-only facts are unsupported capabilities.',
                    'Operator must acknowledge fidelity, resolve any representational ambiguity using available source, and log adaptations before task execution.'],
                initial_database_sha256=hashlib.sha256(destination.read_bytes()).hexdigest())
