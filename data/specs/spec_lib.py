"""项目规格的公共部分：从切分结果（data/specs/sections/<P>.json）生成 SECTIONS，从全局对应表（data/specs/clause_map.yaml）生成 CLAUSE_MAP。"""
import os, json, yaml
_D = os.path.dirname(os.path.abspath(__file__))

def load(pid, ptype):
    sec = json.load(open(os.path.join(_D, 'sections', pid + '.json'), encoding='utf-8'))
    secs = {u['id']: dict(lines=[tuple(u['lines'])], loc=('摘要 ' if u['abstract'] else '') + u['path'], kind=u['kind'])
            for u in sec['units'] if u['kind'] != 'annex'}
    cm = yaml.safe_load(open(os.path.join(_D, 'clause_map.yaml'), encoding='utf-8'))[ptype]
    full = dict(cm)
    for k in list(cm):
        if not k.startswith('pack:'): full['abs_' + k] = cm[k]
    full.setdefault('other', cm.get('work', []))
    full.setdefault('abs_other', full['other'])
    return secs, full
