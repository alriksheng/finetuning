"""给每条意见的推理末尾加“归类”步骤：先说意见属于哪条规则，再对易混规则说明判别标准。
Usage: python3 -I add_classification_step.py <data_dir> [in=out/samples.jsonl] [out=out_cls/samples.jsonl]
依据：开发集诊断显示，预测与标准意见的引文对上时，规则编号一致的只有约 50%；错误集中在几组定义相近的规则（见 CONFUSABLE）。
做法：纯后处理，不改动 JSON 输出，也不改动已有推理，只在 </think> 前追加一段“归类：…”；规则标签和问题取自 rules/rules.yaml。
事实卡抽取、漏项清单、没有意见的样本不处理。判别句（DIS）由人工对照规则定义撰写，待专家过目。"""
import sys, os, json, yaml, re
D = sys.argv[1]
src = os.path.join(D, sys.argv[2] if len(sys.argv) > 2 else 'out/samples.jsonl'); dst = os.path.join(D, sys.argv[3] if len(sys.argv) > 3 else 'out_cls/samples.jsonl')
os.makedirs(os.path.dirname(dst), exist_ok=True)
R = {r['rule_id']: r for r in yaml.safe_load(open(os.path.join(D, 'rules/rules.yaml'), encoding='utf-8'))}
tg = lambda r: f"“{R[r]['tag']}”（{r}）" if r in R else r
# 易混规则：规则 → 判别句（说明“什么情形属于本规则、什么情形属于相近规则”）
DIS = {
 'R-BASE-INDICATOR': '本条判断的是指标该不该设、是否聚焦与成本关联的关键指标、是否缺核心效益指标；如果判断的是基线值有没有来源和测算，则属于“基线值来源与测算”（R-BASE-BASIS）。',
 'R-BASE-BASIS': '本条判断的是基线值或标杆值有没有来源、测算过程、是否量化；如果判断的是指标本身该不该设、是否聚焦，则属于“绩效指标聚焦”（R-BASE-INDICATOR）。',
 'R-REDUCE-CALC': '本条判断的是降本是否同口径、新增或结构调整是否计入；如果判断的是降本幅度是否足够、降本路径是否逐项说明，则属于“降本显著性”（R-REDUCE-VIS）。',
 'R-REDUCE-VIS': '本条判断的是降本幅度是否足够、降本路径是否说明；如果判断的是降本口径是否一致，则属于“降本口径”（R-REDUCE-CALC）；如果判断的是支出标准是否形成并落到下一年度预算，则属于“三个标准衔接”（R-STD-LINK）。',
 'R-STD-LINK': '本条判断的是绩效基线、成本定额和支出标准是否衔接、是否分场景形成并落到下一年度预算建议；如果判断的是降本幅度，则属于“降本显著性”（R-REDUCE-VIS）。',
 'R-COST-PRICE': '本条判断的是单价有没有来源、比价依据和下浮比例依据；如果判断的是文字、表格、不同表之间的数据是否一致、能否复算，则属于“成本数据一致性”（R-COST-CHECK）。',
 'R-COST-CHECK': '本条判断的是文字与表格、摘要与正文、不同表之间的金额、比例、人数是否一致、可复算的是否复算；如果判断的是单价来源和比价依据，则属于“单价核定依据”（R-COST-PRICE）。',
 'R-BASIC-BUDGET': '本条判断的是预算金额、近三年预决算、变化原因和经费去向是否交代；如果判断的是体量、人员、场地等实施内容，则属于“实施内容梳理”（R-BASIC-CONTENT）。',
 'R-BASIC-CONTENT': '本条判断的是体量、服务边界、人员和场地等实施内容是否梳理到位；如果判断的是预算金额和预决算，则属于“预算信息完整性”（R-BASIC-BUDGET）；如果判断的是分析对象是否覆盖全部组成部分，则属于“分析范围完整性”（R-SCOPE）。',
 'R-SCOPE': '本条判断的是分析对象和范围是否覆盖全部组成部分、与基本情况是否一致；如果判断的是实施内容本身有没有写清楚，则属于“实施内容梳理”（R-BASIC-CONTENT）。',
 'R-PROC-PURCHASE': '本条针对涉及政府采购或购买服务的项目，判断采购管理、合同管理、服务考核是否分析；如果判断的是业务环节如何分类、哪些环节影响成本，则属于“业务流程分类梳理”（R-PROC-FLOW）。',
 'R-PROC-FLOW': '本条判断的是业务流程是否分类梳理、是否识别影响成本的环节和优化空间；如果针对的是政府采购或购买服务的采购、合同、考核，则属于“采购、合同与服务考核”（R-PROC-PURCHASE）。',
 'L3-07': '本条判断的是关键指标是否驱动成本项、成本项是否有指标覆盖（指标变化成本是否随之变化）；如果判断的是指标是否聚焦、是否缺核心效益指标，则属于“绩效指标聚焦”（R-BASE-INDICATOR）。',
}
n = k = 0
with open(dst, 'w', encoding='utf-8') as fo:
    for line in open(src, encoding='utf-8'):
        r = json.loads(line); n += 1
        asst = r['messages'][1]['content']; th, js = asst.split('</think>', 1)
        try: obj = json.loads(js.strip())
        except Exception: obj = None
        F = [f for f in (obj or {}).get('findings', []) if isinstance(f, dict)] if isinstance(obj, dict) and r['meta'].get('task_type') in ('小节审核', '比对包') else []
        if F and not r['meta'].get('synthetic'):
            lines, seen = [], set()
            for i, f in enumerate(F, 1):
                rid = f.get('rule_id'); head = f"第{i}条意见（{f.get('issue_type') or '—'}）属于{tg(rid)}"
                if rid in seen: lines.append(head + '，判别同上。'); continue              # 同一规则在同一样本里第二次出现时不再重复判别句
                seen.add(rid)
                lines.append(head + ('：' + DIS[rid] if rid in DIS else (f"，关注的问题是：{R[rid]['question']}。" if rid in R else '。')))
            th = th.rstrip() + '\n归类：' + ('\n'.join(lines) if len(lines) > 1 else lines[0]) + '\n'
            r['messages'][1]['content'] = th + '</think>' + js; r['meta']['cls_step'] = True; k += 1
        fo.write(json.dumps(r, ensure_ascii=False) + '\n')
print(f'处理 {n} 条样本，其中 {k} 条加入归类步骤 → {dst}')
