"""从专家智能体（xreport-reviewer）的参考文件中逐条抽出审核点，生成待对应清单（2026-10-27）。

用法：python3 -I scripts/extract_expert_rules.py <references 目录> data/rules/expert_points.jsonl
每行一条：{pid, file, section, kind（table / prose）, cells 或 text}。
- 表格行：保留表头对应的各列；去掉“案例锚点”列（含具体项目，避免把评测项目的案例带入输入）。
- 文字规则：取以“⚠️ / 🔴 / **判据** / **见到**”等标记起头、或位于“纪律/口径/判定”小节下的段落。
此清单只是原料，规则对应和改写在 data/rules/expert_mapping/*.py 中逐条完成。
"""
import json, re, sys
from pathlib import Path

SRC, OUT = Path(sys.argv[1]), Path(sys.argv[2])
FILES = ['审核要点规则库.md', '审核要点·典型问题对照表.md']
DROP_COLS = {'案例锚点'}
PROSE_MARK = re.compile(r'^\s*(>\s*)?(⚠️|🔴|\*\*判据|\*\*见到|\*\*原则|\*\*纪律|- \*\*|\d+\. \*\*)')


def cells(line):
    return [c.strip() for c in line.strip().strip('|').split('|')]


def main():
    out, n = [], 0
    for fn in FILES:
        sec, head, lines = [], None, (SRC / fn).read_text(encoding='utf-8').splitlines()
        for i, l in enumerate(lines):
            m = re.match(r'^(#{2,4})\s+(.*)', l)
            if m:
                lvl = len(m.group(1)) - 2
                sec = sec[:lvl] + [m.group(2).strip()]
                head = None
                continue
            b = re.match(r'^\*\*([^*]{2,40})\*\*', l)
            if b and not l.startswith('|'):
                sec = sec[:2] + [b.group(1)] if len(sec) >= 2 else sec + [b.group(1)]
                head = None
            if l.startswith('|'):
                if re.match(r'^\|\s*:?-', l):
                    continue
                c = cells(l)
                if head is None:
                    head = c
                    continue
                row = {h: v for h, v in zip(head, c) if h not in DROP_COLS and v}
                if not row:
                    continue
                n += 1
                out.append(dict(pid=f'E{n:03d}', file=fn, section=' > '.join(sec), kind='table', cells=row))
            else:
                head = None if not l.strip() else head
                if PROSE_MARK.match(l) and len(l.strip()) > 20:
                    n += 1
                    out.append(dict(pid=f'E{n:03d}', file=fn, section=' > '.join(sec), kind='prose', text=l.strip()))
    OUT.write_text('\n'.join(json.dumps(r, ensure_ascii=False) for r in out) + '\n', encoding='utf-8')
    by = {}
    for r in out:
        k = (r['file'][:6], r['kind'])
        by[k] = by.get(k, 0) + 1
    print(f'共 {len(out)} 条；', by)


if __name__ == '__main__':
    main()
