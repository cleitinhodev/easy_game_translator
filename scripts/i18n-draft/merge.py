"""Junta rascunho automático + correções manuais (overrides/<lang>.json) e grava shared/i18n/<lang>.json (chaves ordenadas)."""
import json, re, sys, pathlib
root = pathlib.Path(__file__).resolve().parents[2]
here = root / 'scripts/i18n-draft'
en = json.load(open(root / 'shared/i18n/en.json', encoding='utf-8'))
phs = lambda v: sorted(re.findall(r"\{[a-z_]+\}", v))
PRODUCT = ['OCR', 'Tesseract', 'CleitinhoDEV', 'Nina', 'RapidOCR', 'EasyOCR', 'PaddleOCR', 'Ollama', 'Gemini', 'Google', 'YouTube', 'Patreon', 'GPU']
prods = lambda v: [p for p in PRODUCT if re.search(rf"(^|[^A-Za-z]){p}([^A-Za-z]|$)", v)]
# normaliza termos do rascunho automático para o vocabulário revisado (só onde não há problema de concordância)
GLOSS = {'fr': [('région', 'zone'), ('Région', 'Zone')], 'it': [('regione', 'area'), ('Regione', 'Area')], 'id': [('wilayah', 'area'), ('Wilayah', 'Area')],
         'vi': [('khu vực', 'vùng')], 'th': [('ภูมิภาค', 'พื้นที่')], 'ko': [('지역', '영역')], 'ja': [('地域', '領域'), ('プロフィール', 'プロファイル'), ('歴史', '履歴')],
         'zh-CN': [('个人资料', '配置文件')], 'zh-TW': [('地區', '區域'), ('個人資料', '設定檔')]}
for lang in sys.argv[1:]:
    d = json.load(open(here / f'{lang}.draft.json', encoding='utf-8'))
    for a, b in GLOSS.get(lang, []): d = {k: v.replace(a, b) for k, v in d.items()}
    ov_p = here / 'overrides' / f'{lang}.json'
    ov = json.load(open(ov_p, encoding='utf-8')) if ov_p.exists() else {}
    unknown = [k for k in ov if k not in en]
    d.update({k: v for k, v in ov.items() if k in en})
    out, bad = {}, []
    for k in sorted(en):
        v = d.get(k, en[k])
        if phs(v) != phs(en[k]) or any(p not in v for p in prods(en[k])) or not v.strip():
            bad.append(k); v = ov.get(k) if False else en[k]
        out[k] = v
    json.dump(out, open(root / f'shared/i18n/{lang}.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    open(root / f'shared/i18n/{lang}.json', 'a').write('\n')
    print(lang, 'overrides', len(ov), 'unknown-override-keys', unknown, 'english-fallback', bad)
