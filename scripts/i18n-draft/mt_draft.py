"""Rascunho de tradução automática a partir de en.json -> scripts/i18n-draft/<lang>.draft.json (biblioteca 'translators', Bing e reserva).
Uso: python mt_draft.py ar de es ...
Placeholders ({n}), nomes de produto e atalhos são protegidos por marcadores {0},{1}… e validados; em caso de falha mantém o inglês.
Depois, merge.py aplica as correções manuais (overrides/<lang>.json) e grava shared/i18n/<lang>.json."""
import json, re, sys, pathlib, time, warnings
from concurrent.futures import ThreadPoolExecutor
warnings.filterwarnings('ignore')
import translators as ts
root = pathlib.Path(__file__).resolve().parents[2]
src = json.load(open(root / 'shared/i18n/en.json', encoding='utf-8'))
PROT = re.compile(r"\{[a-z_]+\}|\bOCR\b|Tesseract|CleitinhoDEV|Nina|RapidOCR|EasyOCR|PaddleOCR|Ollama|Gemini|Google|YouTube|Patreon|Windows|Python|\bGPU\b|\bCPU\b|\bAPI\b|Ctrl\+\w+|<[a-z]+>|\bPNG\b|\bJSON\b|\bCSV\b|\bTXT\b|\bDeepL\b|\bOpenAI\b|\bDiscord\b|\bGitHub\b|\bPDF\b|\bZIP\b|pip install [A-Za-z]+(?: [A-Za-z]+)?|GEMINI_API_KEY|\.(?:argosmodel|pth|traineddata)\b|\b[\w.]+\.(?:exe|onnx|dll)\b|\bF[56]\b|UB Mannheim|OpenCV|CLAHE|Otsu|\bPSM\b|Regex|Azure|PyAudio|gTTS|pygame|SpeechRecognition|Argos Translate|Argos|EasyOCR|\bDLLs?\b")
BING = {'zh-CN': 'zh-Hans', 'zh-TW': 'zh-Hant', 'uk': 'uk', 'id': 'id', 'vi': 'vi', 'th': 'th'}
ALT = {'zh-CN': 'zh', 'zh-TW': 'zh-TW'}
def call(text, lang):
    errs = []
    for eng, code in (('bing', BING.get(lang, lang)), ('bing', BING.get(lang, lang)), ('alibaba', ALT.get(lang, lang)), ('sogou', ALT.get(lang, lang)), ('youdao', ALT.get(lang, lang))):
        try:
            return ts.translate_text(text, translator=eng, from_language='en', to_language=code, timeout=25), eng
        except Exception as e:
            errs.append(str(e)[:40]); time.sleep(0.5)
    return None, errs
def one(text, lang):
    toks = []
    def rep(m):
        toks.append(m.group(0)); return "{%d}" % (len(toks) - 1)
    s = PROT.sub(rep, text)
    for attempt in range(3):
        out, eng = call(s, lang)
        if out is None: continue
        if all(len(re.findall(r"\{%d\}" % i, out)) == 1 for i in range(len(toks))) and not re.search(r"\{(\d+)\}", re.sub(r"\{(%s)\}" % "|".join(map(str, range(len(toks)))) if toks else r"$^", "", out)):
            return re.sub(r"\{(\d+)\}", lambda m: toks[int(m.group(1))], out)
    return None
def line(ln, lang):
    lead = re.match(r"^\s*", ln).group(0); trail = re.search(r"\s*$", ln).group(0); core = ln.strip()
    if not core or not re.search(r"[A-Za-z]", PROT.sub('', core)): return ln
    o = one(core, lang)
    return None if o is None else lead + o.strip() + trail
def tr(v, lang):
    outl = []
    for ln in v.split('\n'):
        o = line(ln, lang)
        if o is None: return None
        outl.append(o)
    return '\n'.join(outl)
def run(lang):
    uniq = sorted(set(src.values()))
    with ThreadPoolExecutor(6) as ex: res = dict(zip(uniq, ex.map(lambda v: tr(v, lang), uniq)))
    bad = [k for k, v in src.items() if res[v] is None]
    out = {k: (res[v] if res[v] is not None else v) for k, v in src.items()}
    json.dump(out, open(root / f'scripts/i18n-draft/{lang}.draft.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    json.dump(bad, open(root / f'scripts/i18n-draft/{lang}.failed.json', 'w'))
    print(lang, 'done', len(out), 'failed:', len(bad), flush=True)
def fix(lang, clar):
    """Retraduz só as chaves de `clar` (inglês reescrito para ficar sem ambiguidade) sobre o rascunho existente."""
    p = root / f'scripts/i18n-draft/{lang}.draft.json'; d = json.load(open(p, encoding='utf-8'))
    keys = list(clar)
    with ThreadPoolExecutor(6) as ex: res = list(ex.map(lambda k: tr(clar[k], lang), keys))
    bad = [k for k, v in zip(keys, res) if v is None]
    for k, v in zip(keys, res):
        if v is not None: d[k] = v
    json.dump(d, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=1); print(lang, 'fix', len(keys), 'failed', bad, flush=True)
if __name__ == '__main__':
    if sys.argv[1] == '--fix':
        clar = json.load(open(root / 'scripts/i18n-draft/clarified_en.json', encoding='utf-8'))
        for l in sys.argv[2:]: fix(l, clar)
    else:
        for l in sys.argv[1:]: run(l)
