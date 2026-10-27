# 用法：python3 app.py 批次文件 < 新条目（若干 dict(...), ），可选 FLAG 行以 "FLAG " 开头
import sys
p=sys.argv[1]; t=sys.stdin.read()
flags=[l[5:] for l in t.splitlines() if l.startswith('FLAG ')]
body='\n'.join(l for l in t.splitlines() if not l.startswith('FLAG ')).strip()
s=open(p,encoding='utf-8').read().rstrip()
assert s.endswith(']'); s=s[:-1].rstrip()+'\n'+body+'\n]\n'
open(p,'w',encoding='utf-8').write(s)
if flags: open('/home/user/finetuning/data/cot_v2/label_flags.txt','a',encoding='utf-8').write('\n'.join(flags)+'\n')
