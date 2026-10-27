# 用法：python3 -I dump2.py 起 止   （按 data/cot_v2/todo.txt 的序号）
import json,hashlib,re,sys,os
os.chdir('/home/user/finetuning')
a,b=int(sys.argv[1]),int(sys.argv[2])
todo=open('data/cot_v2/todo.txt').read().split()[a:b]
src={}
for x in json.load(open('data/train_v2/audit_train_think.json',encoding='utf-8')):
    u=x['conversations'][0]['value']; src.setdefault(hashlib.md5(u.encode()).hexdigest()[:8],(u,x['conversations'][1]['value']))
for l in open('data/out_fix/samples_fix.jsonl',encoding='utf-8'):
    r=json.loads(l); src['fix:'+r['id']]=(r['messages'][0]['content'],r['messages'][1]['content'])
for i,s in enumerate(todo,a):
    u,ans=src[s]
    sec=re.search(r'【报告段落】\n(.*?)\n\n【',u,re.S); fc=re.search(r'【事实卡】\n(.*?)\n\n【',u,re.S)
    foc=re.search(r'【审核重点】(.*?)\n',u)
    cl=re.findall(r'\[(P[^｜]+)｜',u)
    th=re.search(r'<think>(.*?)</think>',ans,re.S).group(1).strip()
    F=json.loads(re.search(r'</think>\s*(.*)$',ans,re.S).group(1))['findings']
    print(f'##### {i} {s}')
    print('段落:',(sec.group(1) if sec else '')[:900].replace('\n',' '))
    if fc and '无相关' not in fc.group(1): print('事实卡:',fc.group(1)[:300].replace('\n',' '))
    print('条文:',' '.join(cl)); print('重点:',foc.group(1) if foc else '')
    print('旧推理:',th[:700].replace('\n',' '))
    for j,f in enumerate(F):
        print(f" F{j+1} {f['rule_id']} [{f.get('issue_type')}] {f.get('clause_ids')} Q:",' ‖ '.join(e['quote'][:80] for e in f.get('evidence') or [] if isinstance(e,dict) and e.get('quote')))
        print('   S:',(f.get('problem','')+f.get('suggestion',''))[:200])
