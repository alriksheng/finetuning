"""把意见复核样本追加到训练目录（不改动原有文件）：写 judge_train_think.json 并在 dataset_info.json 里登记。
Usage: python3 -I add_judge_to_train.py <train_dir> <out_judge/samples.jsonl>   之后在配置里把 judge_train_think 加到 dataset 列表即可（建议 train/sft_v2_judge.yaml）。"""
import sys, json, os
T, S = sys.argv[1:3]
rows = [json.loads(l) for l in open(S, encoding='utf-8')]
data = [dict(conversations=[dict(**{'from': 'human', 'value': r['messages'][0]['content']}), dict(**{'from': 'gpt', 'value': r['messages'][1]['content']})], system=r['system']) for r in rows]
json.dump(data, open(f'{T}/judge_train_think.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
p = f'{T}/dataset_info.json'; info = json.load(open(p, encoding='utf-8'))
info['judge_train_think'] = {'file_name': 'judge_train_think.json', 'formatting': 'sharegpt', 'columns': {'messages': 'conversations', 'system': 'system'}}
json.dump(info, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print(f'写入 {len(data)} 条 → {T}/judge_train_think.json；dataset_info 已登记 judge_train_think')
