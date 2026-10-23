"""意见组装（方案 v4 2.5、第四章）：把模型输出的结构化字段按模板生成正式意见文字。

- 正式意见只写问题和建议，不出现条文编号（专家意见）；依据单独列出，由条文编号补全文号和条款位置。
- 以 runpy.run_path 加载后调用 render(obj) / render_basis(obj, clauses)；也可在命令行渲染样本文件：
  python3 -I render_opinion.py <samples.jsonl> <clauses.json>
"""
import json, re, sys

CN = '一二三四五六七八九十'


def render(obj):
    t = obj.get('task')
    if t == '事实卡抽取':
        out, prev = [], None
        for f in obj['fields']:
            q = '同上' if f['quote'] == prev else f"“{f['quote']}”"
            out.append(f"- {f['name']}：{f['value']}（{f['page']}）{q}"); prev = f['quote']
        return '\n'.join(out)
    if t == '漏项逐项判断':
        return f"{obj['answer']}。\n{obj['explanation']}"
    fs = obj.get('findings', [])
    if not fs:
        return '未发现问题。'
    if all('part' in f for f in fs):
        return render_formal(fs)
    out, k = [], 0
    for f in fs:
        body = f['problem'] + f['suggestion']
        if f['verdict'] == '提示核实':
            out.append(f'请核实：{body}')
        elif f['verdict'] == '无问题':
            out.append(f'未发现问题。\n{body}')
        else:
            out.append(f"{CN[k]}、{f['issue_type']}\n{body}"); k += 1
    return '\n'.join(out)


def render_formal(fs):
    """按评审意见公文格式组装。所属部分不写进意见正文，单列为标签（render_tags，专家第六轮意见）；
    同一部分的多条意见写成“一是……。二是……。”，降本增效情况、“三个标准”按“1.……”编号；提示核实单独列出。"""
    txt = lambda f: f['problem'] + f['suggestion']
    out, main = [], [f for f in fs if f['verdict'] != '提示核实']
    for part, items in group_parts(main):
        if len(items) == 1 or part == '总体':
            out += [txt(f) for f in items]
        elif part.endswith('部分'):
            out.append(''.join(f"{CN[k]}是{txt(f)}" for k, f in enumerate(items)))
        else:
            out.append(''.join(f"{k + 1}.{txt(f)}" for k, f in enumerate(items)))
    out += [f"请核实：{txt(f)}" for f in fs if f['verdict'] == '提示核实']
    return '\n'.join(out)


def group_parts(fs):
    groups = []
    for f in fs:
        if groups and groups[-1][0] == f['part']: groups[-1][1].append(f)
        else: groups.append((f['part'], [f]))
    return groups


def render_tags(obj):
    """意见标签：每段意见所属的部分（总体意见取问题分类），与 render_formal 的段落一一对应；作辅助展示，不进正文。"""
    fs = obj.get('findings', [])
    if not fs or not all('part' in f for f in fs): return []
    main = [f for f in fs if f['verdict'] != '提示核实']
    tags = []
    for part, items in group_parts(main):
        tags += [f['issue_type'] for f in items] if part == '总体' else ([part] if len(items) > 1 else [part])
    return tags + ['提示核实（' + f['part'] + '）' for f in fs if f['verdict'] == '提示核实']


def render_basis(obj, clauses):
    """依据列表：按条文编号补全文号和条款位置；编号不在条文包中的标注“依据待核实”。"""
    out = []
    for f in obj.get('findings', []):
        refs = [f"{clauses[c]['doc_no']} {clauses[c]['location']}" if c in clauses else f'{c}（依据待核实）' for c in f.get('clause_ids', [])]
        if f.get('basis_type', '').endswith('评审经验'): refs.append('评审经验')
        out.append('；'.join(refs) or '评审经验')
    return out


if __name__ == '__main__':
    cl = {c['clause_id']: c for c in json.load(open(sys.argv[2], encoding='utf-8'))}
    for line in open(sys.argv[1], encoding='utf-8'):
        d = json.loads(line); a = d['messages'][-1]['content']
        obj = json.loads(re.sub(r'(?s)^<think>.*?</think>\s*', '', a))
        print(f"## {d['id']}\n{render(obj)}\n依据：{' | '.join(render_basis(obj, cl))}\n")
