import json, re, pathlib, importlib.util, sys
root = pathlib.Path(__file__).resolve().parents[2]
src = json.load(open(root / 'shared/i18n/en.json', encoding='utf-8'))
txt = open(root / 'scripts/i18n-draft/mt_draft.py', encoding='utf-8').read()
new_prot = re.compile(re.search(r'^PROT = re\.compile\(r"(.*)"\)$', txt, re.M).group(1))
CLAR = {  # inglês reescrito só para a tradução automática (menos ambíguo)
 "ai.enabled": "AI is turned on", "ai.key": "Gemini API key", "box.auto_font": "Adjust the text size automatically",
 "box.clickthrough": "Clicks pass through the window", "box.ct_off": "Turn off \"clicks pass through\"",
 "bug.copy": "Copy the activity log", "bug.log": "Log file (activity record)", "ocr.before": "Screen capture (before)",
 "ocr.scale": "Enlarge the image", "tab.replace": "Replacements", "ocr.read": "Read text in:",
 "main.region": "Select the region", "main.change": "Change", "common.on": "On", "common.off": "Off",
 "main.tr_short": "Translation", "ocr.detect": "Detect", "ocr.rescan": "Scan again", "rep.keep": "Glossary: names that must NOT be translated",
 "hist.clear": "Clear the history", "main.region_set": "Region selected: {w}×{h}px.", "toast.region_set": "Region selected: {w}×{h}px.",
 "menu.box_hide": "Close the Box Mode window", "menu.box_show": "Open the Box Mode window", "menu.on_top": "Keep window always on top", "gen.topmost": "Keep the main window always on top",
 "main.running": "Active", "status.running": "Active", "ocr.test": "Test the engine", "tr.up": "Move up in the list", "tr.down": "Move down in the list",
 "ocr.sharpen": "Sharpen the image", "comp.update": "Update", "status.cps": "cycles per second", "main.cache": "cache", "main.cache_only_short": "CACHE ONLY",
}
out = {}
for k, v in src.items():
    if k in CLAR: out[k] = CLAR[k]
    elif new_prot.search(v): out[k] = v
json.dump(out, open(root / 'scripts/i18n-draft/clarified_en.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print(len(out))
