import json, os, re, time
from pathlib import Path
from urllib import request

API='https://hub.ag3nts.org/api/zmail'

def load_env(path):
    if not path.exists():
        return
    for line in path.read_text(encoding='utf-8').splitlines():
        s=line.strip()
        if not s or s.startswith('#') or '=' not in s: continue
        k,v=s.split('=',1)
        os.environ.setdefault(k.strip(), v.strip())

load_env(Path('.env')); load_env(Path('Season2/.env'))
key=os.environ.get('HUB_API_KEY','').strip()
if not key: raise SystemExit('No HUB_API_KEY')

def call(action, **kwargs):
    payload={'apikey':key,'action':action}; payload.update(kwargs)
    data=json.dumps(payload).encode('utf-8')
    req=request.Request(API,data=data,headers={'Content-Type':'application/json'},method='POST')
    with request.urlopen(req, timeout=40) as r:
        return json.loads(r.read().decode('utf-8','replace'))

out=Path('Season2/lesson4_mailbox/output_side_scan_all')
out.mkdir(parents=True, exist_ok=True)

all_headers=[]; ids=[]; seen=set()
max_pages=12
for p in range(1,max_pages+1):
    try:
        r=call('getInbox', page=p, perPage=20)
    except Exception as e:
        print('stop inbox page', p, 'err', e)
        break
    items=r.get('items',[])
    print('inbox page',p,'hits',len(items),'totalPages',r.get('pagination',{}).get('totalPages'))
    (out/f'inbox_{p}.json').write_text(json.dumps(r,ensure_ascii=False,indent=2), encoding='utf-8')
    for it in items:
        mid=it.get('messageID')
        if mid and mid not in seen:
            seen.add(mid); ids.append(mid); all_headers.append(it)
    tp=r.get('pagination',{}).get('totalPages')
    if isinstance(tp,int) and p>=tp: break
    time.sleep(0.1)

print('unique ids',len(ids))
msgs=[]
for i in range(0,len(ids),20):
    batch=ids[i:i+20]
    try:
        r=call('getMessages', ids=batch)
    except Exception as e:
        print('batch err', i, e); continue
    msgs.extend(r.get('items',[]))
    time.sleep(0.1)

(out/'messages.json').write_text(json.dumps(msgs,ensure_ascii=False,indent=2), encoding='utf-8')
text='\n\n'.join([f"ID:{m.get('messageID')}\nSUB:{m.get('subject')}\nFROM:{m.get('from')}\nDATE:{m.get('date')}\n{m.get('message','')}" for m in msgs])
(out/'messages.txt').write_text(text, encoding='utf-8')

# checks
for needle in ['Wiktor','somsiad','sąsiad','nigdy nie czytałam','cudzych maili','Mam wiadomość','No nareszcie','Victor']:
    c=text.lower().count(needle.lower())
    if c:
        print('count',needle,c)

flags=sorted(set(re.findall(r'\{FLG:[^}]+\}', text)))
print('flags in message bodies',flags)
print('saved',out)
