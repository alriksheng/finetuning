"""Clause pack for the general (政府采购投诉) data bucket. Usage: build_clauses_general.py <law_dir> <out_json>"""
import sys, re, json, os, html, subprocess
LAW, OUT = sys.argv[1], sys.argv[2]
def norm(s): return re.sub(r'\s+', ' ', s).strip()
g94 = norm(open(os.path.join(LAW, 'g94.txt'), encoding='utf-8').read())
t = open(os.path.join(LAW, 'sl3.html'), encoding='utf-8', errors='ignore').read()
t = re.sub(r'(?is)<(script|style)[^>]*>.*?</\1>', ' ', t); t = re.sub(r'(?i)</(p|div|br|li|tr)>|<br\s*/?>', '\n', t)
sl = norm(html.unescape(re.sub(r'<[^>]+>', ' ', t)))
D94 = dict(doc_no='财政部令第94号', title='政府采购质疑和投诉办法', eff='2018-03-01')
D658 = dict(doc_no='国务院令第658号', title='中华人民共和国政府采购法实施条例', eff='2015-03-01')
C = [
 ('G94-11', g94, D94, '第十一条 质疑主体与期限', '第十一条 提出质疑的供应商', '7个工作日内提出。'),
 ('G94-15', g94, D94, '第十五条 质疑答复内容', '第十五条 质疑答复应当包括下列内容', '质疑答复的内容不得涉及商业秘密。'),
 ('G94-16', g94, D94, '第十六条 质疑处理', '第十六条 采购人、采购代理机构认为供应商质疑不成立', '否则应当重新开展采购'),
 ('G94-18', g94, D94, '第十八条 投诉的条件', '第十八条 投诉人投诉时', None),
 ('G94-19', g94, D94, '第十九条 投诉的受理条件', '第十九条 投诉人应当根据本办法第七条第二款规定', '（五）财政部规定的其他条件。'),
 ('G94-20', g94, D94, '第二十条 投诉范围', '第二十条 供应商投诉的事项不得超出已质疑事项的范围', '但基于质疑答复内容提出的投诉事项除外。'),
 ('G94-25', g94, D94, '第二十五条 举证责任', '第二十五条 应当由投诉人承担举证责任的投诉事项', '依法承担不利后果。'),
 ('G94-29', g94, D94, '第二十九条 驳回投诉', '第二十九条 投诉处理过程中，有下列情形之一的，财政部门应当驳回投诉', '视为以非法手段取得证明材料。'),
 ('G94-30', g94, D94, '第三十条 撤回投诉', '第三十条 财政部门受理投诉后', '并书面告知相关当事人。'),
 ('G94-31', g94, D94, '第三十一条 采购文件投诉', '第三十一条 投诉人对采购文件提起的投诉事项', '由责任人承担赔偿责任。'),
 ('G94-32', g94, D94, '第三十二条 采购过程或结果投诉', '第三十二条 投诉人对采购过程或者采购结果提起的投诉事项', '财政部门应当认定废标行为无效。'),
 ('G658-20', sl, D658, '第二十条 差别待遇或者歧视待遇', '第二十条 采购人或者采购代理机构有下列情形之一的', '以其他不合理条件限制或者排斥潜在供应商。'),
 ('G658-34', sl, D658, '第三十四条 评标方法', '第三十四条 政府采购招标评标方法分为', '招标文件中没有规定的评标标准不得作为评审的依据。'),
 ('G658-68', sl, D658, '第六十八条 采购人、采购代理机构法律责任', '第六十八条 采购人、采购代理机构有下列情形之一的', '（十）未按照规定组织对供应商履约情况进行验收。'),
]
res, bad = [], []
for cid, src, d, loc, a, b in C:
    i = src.find(a)
    if i < 0: bad.append((cid, 'start')); continue
    if b is None:
        # up to next article heading
        m = re.search(r'第[一二三四五六七八九十百]+条 ', src[i + 8:])
        text = src[i:i + 8 + m.start()] if m else src[i:i + 400]
    else:
        j = src.find(b, i)
        if j < 0: bad.append((cid, 'end')); continue
        text = src[i:j + len(b)]
    res.append(dict(clause_id=cid, doc_no=d['doc_no'], title=d['title'], location=loc, text=text.strip(), effective_from=d['eff'], replaced_by=None))
print('BAD', bad)
json.dump(res, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
for r in res: print(f"{r['clause_id']:9s}{len(r['text']):5d}  {r['text'][:70]}")
