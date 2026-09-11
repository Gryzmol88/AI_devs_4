import json, os, re
from pathlib import Path
from urllib import request, error

API='https://hub.ag3nts.org/api/zmail'
queries=[
 'Wiktor', 'somsiad', 'sąsiad', 'nigdy nie czytałam', 'cudzych maili',
 'Mam wiadomość', 'No nareszcie', 'vik4tor', 'proton.me', 'subject:Wiktor'
]

def load_env(path):
    if not path.exists():
        return
    for line in path.read_text(encoding='utf-8').splitlines():
        s=line.strip()
        if not s or s.startswith('#') or '=' not in s: continue
        k,v=s.split('=',1)
        os.environ.setdefault(k.strip(), v.strip())

load_env(Path('.env'))
load_env(Path('Season2/.env'))
key=os.environ.get('HUB_API_KEY','').strip()
if not key:
    raise SystemExit('missing HUB_API_KEY')


def call(action, **kwargs):
    payload={'apikey':key,'action':action}
    payload.update(kwargs)
    data=json.dumps(payload).encode('utf-8')
    req=request.Request(API,data=data,headers={'Content-Type':'application/json'},method='POST')
    with request.urlopen(req, timeout=40) as r:
        return json.loads(r.read().decode('utf-8','replace'))

out_dir=Path('Season2/lesson4_mailbox/output_side_scan')
out_dir.mkdir(parents=True, exist_ok=True)

hits=[]
ids=[]
seen_ids=set()
for q in queries:
    try:
        resp=call('search', query=q, page=1, perPage=20)
    except Exception as e:
        print('search error', q, e)
        continue
    (out_dir / f"search_{re.sub(r'[^A-Za-z0-9]+','_',q)[:40]}.json").write_text(json.dumps(resp,ensure_ascii=False,indent=2), encoding='utf-8')
    items=resp.get('items',[])
    print(f"query={q!r} hits={len(items)}")
    for it in items:
        mid=it.get('messageID')
        if mid and mid not in seen_ids:
            seen_ids.add(mid)
            ids.append(mid)
            hits.append(it)

# include inbox page1 as fallback
try:
    inbox=call('getInbox', page=1, perPage=20)
    (out_dir / 'inbox_page1.json').write_text(json.dumps(inbox,ensure_ascii=False,indent=2), encoding='utf-8')
    for it in inbox.get('items',[]):
        mid=it.get('messageID')
        if mid and mid not in seen_ids:
            seen_ids.add(mid); ids.append(mid); hits.append(it)
except Exception as e:
    print('inbox error', e)

print('unique messageIDs to fetch:', len(ids))
msgs=[]
for i in range(0, len(ids), 10):
    batch=ids[i:i+10]
    try:
        r=call('getMessages', ids=batch)
    except Exception as e:
        print('getMessages error batch', i, e)
        continue
    for m in r.get('items',[]):
        msgs.append(m)

(out_dir / 'messages.json').write_text(json.dumps(msgs,ensure_ascii=False,indent=2), encoding='utf-8')

text='\n\n'.join([f"ID:{m.get('messageID')}\nSUB:{m.get('subject')}\nFROM:{m.get('from')}\nDATE:{m.get('date')}\n{m.get('message','')}" for m in msgs])
(out_dir / 'messages.txt').write_text(text, encoding='utf-8')

# quick findings
flag_re=re.compile(r'\{FLG:[^}]+\}')
flags=flag_re.findall(text)
print('flags found in messages:', sorted(set(flags)))
for needle in ['Wiktor','somsiad','sąsiad','nigdy nie czytałam','cudzych maili','Mam wiadomość','No nareszcie']:
    if needle.lower() in text.lower():
        print('FOUND phrase:', needle)

print('saved to', out_dir)
