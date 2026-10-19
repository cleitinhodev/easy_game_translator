"""Correções pontuais (palavras comuns que a tradução automática errou) -> overrides/<lang>.json (somem em cima do rascunho)."""
import json, pathlib
here = pathlib.Path(__file__).resolve().parent
X = {
 'apply': {'th': 'ใช้', 'zh-CN': '应用', 'zh-TW': '套用', 'ja': '適用'},
 'menu.quit': {'ar': 'إنهاء', 'ja': '終了', 'ko': '종료', 'nl': 'Afsluiten', 'th': 'ปิดโปรแกรม'},
 'common.on': {'fr': 'Activé', 'it': 'Attivo', 'es': 'Activado', 'pl': 'Wł.'},
 'common.off': {'es': 'Desactivado', 'fr': 'Désactivé', 'it': 'Disattivo', 'pl': 'Wył.'},
 'tr.ready': {'ja': '準備完了', 'ko': '준비됨', 'zh-CN': '就绪', 'zh-TW': '就緒'},
 'rep.find': {'es': 'Buscar', 'fr': 'Rechercher', 'de': 'Suchen', 'it': 'Cerca', 'ja': '検索', 'ko': '찾기', 'zh-CN': '查找', 'zh-TW': '尋找', 'th': 'ค้นหา', 'nl': 'Zoeken', 'id': 'Cari'},
 'manual.mic': {'ko': '말하기', 'zh-CN': '说话', 'hi': 'बोलें'},
}
for k in ('main.cache', 'manual.cached'):
    X[k] = {'pl': 'cache', 'ar': 'الذاكرة المؤقتة'}
for k in ('status.cache', 'tr.cache'):
    X[k] = {'pl': 'Cache', 'ar': 'الذاكرة المؤقتة'}
for k, per in X.items():
    for lang, v in per.items():
        p = here / 'overrides' / f'{lang}.json'; d = json.load(open(p, encoding='utf-8')); d[k] = v
        json.dump(d, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('ok')
