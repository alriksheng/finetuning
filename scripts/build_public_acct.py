"""公开数据·会计审计税务：带推理的选择题样本（训练集 v3，2026-10-27）。

题目：data/public_src/会计审计税务/items.jsonl（CMMLU 会计、工程项目管理；C-Eval 注册会计师、税务师，均为非商业许可）。
推理：data/annotations_public/acct_*.py，每个文件一个 ANNOTATIONS 列表，每项 {id, seq, answer, think, summary}。
     推理在会话中逐题撰写，作答时不看标准答案。
核验：作答与标准答案一致（不一致的拒收，不改答案去凑）；「」引文逐字出自题目；推理不少于 MIN_THINK 字；
     推理中的算式逐个复算（百分数按百分之几计）。
输出：data/public/会计审计税务/acct_samples.json（sharegpt），以及 data/public_src/会计审计税务/ 下的 preview.md、report.txt。
用法：python3 -I scripts/build_public_acct.py data
"""
import glob, json, os, re, runpy, sys

DATA = sys.argv[1]
SRC = os.path.join(DATA, 'public_src', '会计审计税务')
OUT = os.path.join(DATA, 'public', '会计审计税务')
MIN_THINK = 450
SYSTEM = ('你是一名擅长会计、审计、税务与工程造价管理的解题专家。请先充分、逐步地推理——明确考查的知识点、'
          '说明适用的准则或规定、列出计算过程并复算、逐项分析选项并自我检验——再给出答案。')
QUOTE = re.compile(r'「([^」]+)」')
NUM = r'\d[\d,]*(?:\.\d+)?%?'
EXPR = re.compile(rf'({NUM}(?:\s*[+\-−×÷*/]\s*{NUM})+)\s*(=|≈)\s*(\d[\d,]*(?:\.\d+)?)(%?)')
squash = lambda s: re.sub(r'\s+', '', s)


def arith_errors(text):
    errs = []
    for m in EXPR.finditer(text):
        lhs = re.sub(r'(\d[\d,]*(?:\.\d+)?)%', lambda k: f'({k.group(1).replace(",", "")}/100)', m.group(1))
        lhs = re.sub(r'\d[\d,]*(?:\.\d+)?', lambda k: k.group(0).replace(',', ''), lhs)
        try:
            val = eval(lhs.replace('−', '-').replace('×', '*').replace('÷', '/'))
        except Exception:
            errs.append(f'算式无法计算：{m.group(0)}')
            continue
        rhs = m.group(3).replace(',', '')
        if m.group(4):
            val *= 100
        d = len(rhs.split('.')[1]) if '.' in rhs else 0
        tol = 0.5 * 10 ** -d + 1e-9 if m.group(2) == '=' else max(0.5 * 10 ** -d, abs(float(rhs)) * 0.005)
        if abs(val - float(rhs)) > tol:
            errs.append(f'算式不对：{m.group(0)}（实际 {val:.4f}）')
    return errs


def user_text(it):
    return f"【题目】\n{it['question']}\n" + '\n'.join(f'{k}. {it["options"][k]}' for k in 'ABCD') + '\n\n请作答。'


def main():
    items = {json.loads(l)['seq']: json.loads(l) for l in open(os.path.join(SRC, 'items.jsonl'), encoding='utf-8')}
    ok, bad, seen = [], [], set()
    for f in sorted(glob.glob(os.path.join(DATA, 'annotations_public', 'acct_*.py'))):
        for a in runpy.run_path(f)['ANNOTATIONS']:
            it, errs = items.get(a['seq']), []
            if it is None:
                bad.append((a['id'], ['题号不存在']))
                continue
            if a['seq'] in seen:
                errs.append('题号重复')
            seen.add(a['seq'])
            if a['answer'] != it['answer']:
                errs.append(f'作答 {a["answer"]}，标准答案 {it["answer"]}（拒收）')
            user = user_text(it)
            hay = squash(user)
            for q in QUOTE.findall(a['think'] + a['summary']):
                if not all(squash(p) in hay for p in re.split(r'…+', q) if p.strip()):
                    errs.append(f'引文不在题目中：「{q[:30]}」')
            if len(a['think']) < MIN_THINK:
                errs.append(f'推理过短：{len(a["think"])} 字')
            errs += arith_errors(a['think'] + a['summary'])
            tr = lambda t: QUOTE.sub(lambda m: '“' + m.group(1) + '”', t).strip()
            rec = dict(id=a['id'], seq=a['seq'], item_id=it['item_id'], subject=it['subject'], think_chars=len(a['think']),
                       system=SYSTEM, user=user,
                       assistant=f"<think>\n{tr(a['think'])}\n</think>\n答案：{a['answer']}。{tr(a['summary'])}")
            (bad.append((a['id'], errs)) if errs else ok.append(rec))
    os.makedirs(OUT, exist_ok=True)
    json.dump([dict(system=r['system'], conversations=[{'from': 'human', 'value': r['user']}, {'from': 'gpt', 'value': r['assistant']}]) for r in ok],
              open(os.path.join(OUT, 'acct_samples.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    with open(os.path.join(SRC, 'preview.md'), 'w', encoding='utf-8') as fo:
        fo.write('# 会计审计税务 公开样本预览\n\n')
        for r in ok:
            fo.write(f"## {r['id']} · {r['subject']} · {r['item_id']} · 推理 {r['think_chars']} 字\n\n```\n{r['user']}\n```\n\n```\n{r['assistant']}\n```\n\n---\n\n")
    by = {}
    for r in ok:
        by[r['subject']] = by.get(r['subject'], 0) + 1
    rep = (f'通过 {len(ok)}，拒收 {len(bad)}；题库共 {len(items)} 题；按科目 {by}\n'
           + '\n'.join(f'拒收 {i}：{e}' for i, e in bad))
    open(os.path.join(SRC, 'report.txt'), 'w', encoding='utf-8').write(rep + '\n')
    print(rep)


if __name__ == '__main__':
    main()
