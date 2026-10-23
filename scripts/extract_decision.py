"""Extract decision body text from downloaded gov pages. Usage: extract_decision.py raw_dir txt_dir"""
import sys, os, re, html, glob
raw, out = sys.argv[1], sys.argv[2]
def clean(t):
    t = re.sub(r'(?is)<(script|style)[^>]*>.*?</\1>', ' ', t)
    t = re.sub(r'(?i)</(p|div|br|li|tr|h\d)>|<br\s*/?>', '\n', t)
    t = re.sub(r'<[^>]+>', ' ', t)
    t = html.unescape(t)
    t = re.sub(r'[ \t　\xa0]+', ' ', t)
    t = re.sub(r'\n\s*\n+', '\n', t)
    return t.strip()
for f in sorted(glob.glob(os.path.join(raw, '*.html'))):
    sid = os.path.basename(f)[:-5]
    t = clean(open(f, encoding='utf-8', errors='ignore').read())
    i = t.find('投诉人')
    j = t.rfind('投诉人：') if False else -1
    body = t[i:] if i >= 0 else t
    # cut footer noise after the decision's tail
    for endk in ('网站地图', '版权所有', '主办单位', '相关链接', '上一篇', '下一篇', '分享到', '打印本页', '信息来源'):
        k = body.find(endk, 400)
        if k > 0: body = body[:k]
    open(os.path.join(out, sid + '.txt'), 'w', encoding='utf-8').write(body)
    m = re.search(r'(决定如下|处理结果|处理依据及结果|本机关认为)', body)
    print(f'{sid:12s} chars={len(body):6d}  has_result_marker={bool(m)}')
