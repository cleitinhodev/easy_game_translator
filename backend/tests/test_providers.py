"""Tradutores online com HTTP simulado (nenhum pedido sai da máquina)."""
import hashlib
import json

import pytest

from egt.translate import http as H
from egt.translate.base import RateLimited, TranslationError


class Resp:
    def __init__(self, status=200, body=None, text=None, headers=None):
        self.status_code = status
        self._body = body
        self.text = text if text is not None else (json.dumps(body) if body is not None else "")
        self.headers = headers or {"Content-Type": "application/json"}

    def json(self):
        if self._body is None:
            return json.loads(self.text)
        return self._body


class FakeSession:
    def __init__(self, routes):
        self.routes = routes        # lista de (predicado(method,url,kw) | substring, resposta | função)
        self.calls = []

    def request(self, method, url, **kw):
        self.calls.append((method, url, kw))
        for match, resp in self.routes:
            if (callable(match) and match(method, url, kw)) or (isinstance(match, str) and match in url):
                r = resp(method, url, kw) if callable(resp) else resp
                if isinstance(r, list):
                    return r.pop(0) if len(r) > 1 else r[0]
                return r
        raise AssertionError(f"rota inesperada {method} {url}")


@pytest.fixture
def net(monkeypatch):
    holder = {}

    def install(routes):
        s = FakeSession(routes)
        holder["s"] = s
        monkeypatch.setattr(H, "session", lambda: s)
        return s
    monkeypatch.setattr(H, "throttle", lambda *a, **k: None)
    monkeypatch.setattr("time.sleep", lambda *_: None)
    return install


# ------------------------------------------------------------------ Google
def test_google_clients5(net):
    from egt.translate.google import GoogleTranslate
    s = net([("clients5", Resp(body=["Olá mundo"]))])
    assert GoogleTranslate().translate("Hello world", "en", "pt") == "Olá mundo"
    m, _url, kw = s.calls[0]
    assert m == "POST" and kw["data"] == {"q": "Hello world"} and kw["params"]["tl"] == "pt"


def test_google_auto_detect_shape_and_retry_on_empty(net):
    from egt.translate.google import GoogleTranslate
    seq = [Resp(body=[""]), Resp(body=[["门关着", "en"]])]
    net([("clients5", lambda *a: seq.pop(0))])
    assert GoogleTranslate().translate("The gate is closed", "", "zh-CN") == "门关着"


def test_google_falls_back_to_gtx(net):
    from egt.translate.google import GoogleTranslate
    s = net([("clients5", Resp(429, text="")), ("translate_a/single", Resp(body=[[["Olá ", "Hello ", None], ["mundo", "world"]]]))])
    assert GoogleTranslate().translate("Hello world", "en", "pt") == "Olá mundo"
    assert any("translate_a/single" in c[1] for c in s.calls)


def test_google_all_blocked_is_rate_limited(net):
    from egt.translate.google import GoogleTranslate
    net([("google", Resp(302, text=""))])
    with pytest.raises(RateLimited):
        GoogleTranslate().translate("Hello world", "en", "pt")


# ------------------------------------------------------------------ Bing
PAGE = 'x IG:"ABC123" y data-iid="translator.5023" z var params_AbusePreventionHelper = [1700000000000,"tok_en",3600000];'


def test_bing_session_and_translate(net):
    from egt.translate import bing
    bing.reset_session()
    s = net([("bing.com/translator", Resp(text=PAGE, headers={"Content-Type": "text/html"})),
             ("ttranslatev3", Resp(body=[{"translations": [{"text": "Olá", "to": "pt"}]}]))])
    assert bing.BingTranslate().translate("Hello", "en", "pt") == "Olá"
    post = next(c for c in s.calls if "ttranslatev3" in c[1])
    assert post[2]["data"]["token"] == "tok_en" and post[2]["data"]["key"] == "1700000000000"
    assert post[2]["params"]["IG"] == "ABC123" and post[2]["data"]["fromLang"] == "en"
    # sessão reaproveitada
    bing.BingTranslate().translate("Bye", "", "zh-TW")
    assert sum("bing.com/translator" in c[1] for c in s.calls) == 1
    assert s.calls[-1][2]["data"]["to"] == "zh-Hant" and s.calls[-1][2]["data"]["fromLang"] == "auto-detect"


def test_bing_refreshes_token_on_400(net):
    from egt.translate import bing
    bing.reset_session()
    seq = [Resp(body={"statusCode": 400}), Resp(body=[{"translations": [{"text": "Oi"}]}])]
    s = net([("bing.com/translator", Resp(text=PAGE)), ("ttranslatev3", lambda *a: seq.pop(0))])
    assert bing.BingTranslate().translate("Hi", "en", "pt") == "Oi"
    assert sum("bing.com/translator" in c[1] for c in s.calls) == 2


def test_bing_page_changed(net):
    from egt.translate import bing
    bing.reset_session()
    net([("bing.com/translator", Resp(text="<html>nada</html>"))])
    with pytest.raises(TranslationError) as e:
        bing.BingTranslate().translate("Hi", "en", "pt")
    assert e.value.code == "bad_response"


# ------------------------------------------------------------------ Yandex
def test_yandex_ok_and_unsupported(net):
    from egt.translate.yandex import YandexTranslate
    s = net([("yandex", Resp(body={"code": 200, "lang": "en-pt", "text": ["Olá"]}))])
    assert YandexTranslate().translate("Hello", "en", "pt") == "Olá"
    assert s.calls[0][2]["params"]["lang"] == "en-pt"
    net([("yandex", Resp(400, body={"code": 501, "message": "not supported"}))])
    with pytest.raises(TranslationError) as e:
        YandexTranslate().translate("Hello", "", "pt")
    assert e.value.code == "unsupported_lang"


# ------------------------------------------------------------------ Mozhi
def test_mozhi_rotates_instances(net):
    from egt.translate import mozhi
    mozhi._good.clear()
    first = mozhi.INSTANCES[0]
    s = net([(first, Resp(500, text="request failed with status code: 429", headers={"Content-Type": "text/plain"})),
             ("/api/translate", Resp(body={"translated-text": "O portão", "engine": "duckduckgo"}))])
    eng = mozhi.MozhiTranslate()
    assert eng.translate("The gate", "en", "pt") == "O portão"
    assert eng.last_instance == mozhi.INSTANCES[1]
    assert s.calls[1][2]["params"]["engine"] == "duckduckgo"
    assert mozhi.MozhiTranslate()._instances()[0] == mozhi.INSTANCES[1]


def test_mozhi_custom_url_and_bad_url():
    from egt.translate.mozhi import MozhiTranslate
    assert MozhiTranslate("ftp://x").available()[0] is False
    assert MozhiTranslate("https://mozhi.example.org/")._instances() == ["https://mozhi.example.org"]


def test_mozhi_unsupported_language(net):
    from egt.translate import mozhi
    mozhi._good.clear()
    net([("/api/translate", Resp(200, text="Target language code invalid", headers={"Content-Type": "text/plain"}))])
    with pytest.raises(TranslationError) as e:
        mozhi.MozhiTranslate().translate("The gate", "en", "xx")
    assert e.value.code == "unsupported_lang"


# ------------------------------------------------------------------ Apertium
PAIRS = {"responseData": [{"sourceLanguage": "eng", "targetLanguage": "spa"},
                          {"sourceLanguage": "spa", "targetLanguage": "por_BR"}]}


def test_apertium_direct_and_pivot(net):
    from egt.translate import apertium
    apertium._pairs.clear()

    def tr(method, url, kw):
        pair = kw["data"]["langpair"]
        return Resp(body={"responseData": {"translatedText": f"<{pair}>{kw['data']['q']}"}})
    net([("listPairs", Resp(body=PAIRS)), ("/translate", tr)])
    eng = apertium.ApertiumTranslate()
    assert eng.translate("hi", "en", "es") == "<eng|spa>hi"
    assert eng.translate("hi", "en", "pt") == "<spa|por_BR><eng|spa>hi"
    with pytest.raises(TranslationError) as e:
        eng.translate("hi", "ja", "pt")
    assert e.value.code == "unsupported_lang"
    with pytest.raises(TranslationError):
        eng.translate("hi", "", "pt")         # precisa da origem


# ------------------------------------------------------------------ MyMemory
def test_mymemory_prefers_mt_and_skips_vandalism(net):
    from egt.translate.mymemory import MyMemoryTranslate, pick_match
    data = {"responseStatus": 200, "responseData": {"translatedText": "Hello world translated mierda", "match": 0.99},
            "matches": [{"segment": "Hello world", "translation": "Hello world translated mierda", "created-by": "MateCat", "match": 0.99},
                        {"segment": "Hello, world", "translation": "Hello, world", "created-by": "MateCat", "match": 0.99},
                        {"segment": "Hello World", "translation": "Olá Mundo", "created-by": "MateCat", "match": 0.98}]}
    assert pick_match("Hello world", data) == "Olá Mundo"
    data2 = {"responseStatus": 200, "responseData": {"translatedText": "x"},
             "matches": [{"segment": "The gate", "translation": "O portão", "created-by": "MT!", "match": 0.85}]}
    assert pick_match("The gate", data2) == "O portão"
    s = net([("mymemory", Resp(body=data))])
    assert MyMemoryTranslate(email="eu@exemplo.com").translate("Hello world", "en", "pt") == "Olá Mundo"
    p = s.calls[0][2]["params"]
    assert p["de"] == "eu@exemplo.com" and p["langpair"] == "en-GB|pt-BR" and p["mt"] == "1"
    assert MyMemoryTranslate(email="não é email").email == ""


def test_mymemory_quota(net):
    from egt.translate.mymemory import MyMemoryTranslate
    net([("mymemory", Resp(body={"responseStatus": 429, "quotaFinished": True, "responseData": {"translatedText": "MYMEMORY WARNING"}}))])
    with pytest.raises(RateLimited) as e:
        MyMemoryTranslate().translate("Hello", "en", "pt")
    assert e.value.code == "quota"


# ------------------------------------------------------------------ LibreTranslate
def test_libre_config_and_errors(net):
    from egt.translate.libre import LibreTranslate
    assert LibreTranslate("").available()[0] is False
    assert LibreTranslate("https://libretranslate.com").available()[0] is False     # exige chave
    assert LibreTranslate("javascript:alert(1)").available()[0] is False
    for url, code in (("", "config"), ("ftp://x", "config"), ("https://libretranslate.com", "no_key")):
        with pytest.raises(TranslationError) as e:
            LibreTranslate(url).translate("hi", "en", "pt")
        assert e.value.code == code, url
        assert LibreTranslate(url).unavailable_code() == code
    net([("/translate", Resp(403, body={"error": "Invalid API key"}))])
    with pytest.raises(TranslationError) as e:
        LibreTranslate("https://libretranslate.com", "k").translate("hi", "en", "pt")
    assert e.value.code == "bad_key"
    s = net([("/languages", Resp(body=[{"code": "en"}])), ("/translate", Resp(body={"translatedText": "oi"}))])
    eng = LibreTranslate("http://localhost:5000")
    assert eng.languages() == [{"code": "en"}]
    assert eng.translate("hi", "", "zh-TW") == "oi"
    assert s.calls[-1][2]["json"]["target"] == "zh-Hant" and "api_key" not in s.calls[-1][2]["json"]


# ------------------------------------------------------------------ DeepL / Azure / Google Cloud
def test_deepl_free_endpoint_and_header(net):
    from egt.translate.official import DeepLTranslate
    s = net([("deepl.com", Resp(body={"translations": [{"text": "Olá"}]}))])
    assert DeepLTranslate("abc:fx").translate("Hello", "en", "pt") == "Olá"
    _m, url, kw = s.calls[0]
    assert url.startswith("https://api-free.deepl.com/v2/translate")
    assert kw["headers"]["Authorization"] == "DeepL-Auth-Key abc:fx"
    assert kw["json"]["target_lang"] == "PT-BR" and kw["json"]["source_lang"] == "EN"
    assert "abc" not in url
    net([("deepl.com", Resp(403, text="Forbidden"))])
    with pytest.raises(TranslationError) as e:
        DeepLTranslate("abc").translate("Hello", "en", "pt")
    assert e.value.code == "bad_key"
    net([("deepl.com", Resp(456, text=""))])
    with pytest.raises(RateLimited) as e:
        DeepLTranslate("abc").translate("Hello", "en", "pt")
    assert e.value.code == "quota"
    assert DeepLTranslate("").available()[0] is False


def test_azure_rest(net):
    from egt.translate.official import MicrosoftTranslate
    s = net([("microsofttranslator", Resp(body=[{"translations": [{"text": "Olá", "to": "pt"}]}]))])
    assert MicrosoftTranslate("k", "brazilsouth").translate("Hello", "", "zh-CN") == "Olá"
    _m, _url, kw = s.calls[0]
    assert kw["params"]["to"] == "zh-Hans" and "from" not in kw["params"]
    assert kw["headers"]["Ocp-Apim-Subscription-Region"] == "brazilsouth" and kw["json"] == [{"Text": "Hello"}]
    net([("microsofttranslator", Resp(401, body={"error": {"code": 401001}}))])
    with pytest.raises(TranslationError) as e:
        MicrosoftTranslate("k").translate("Hello", "en", "pt")
    assert e.value.code == "bad_key"


def test_gcloud_key_in_header_not_url(net):
    from egt.translate.official import GoogleCloudTranslate
    s = net([("translation.googleapis.com", Resp(body={"data": {"translations": [{"translatedText": "Olá"}]}}))])
    assert GoogleCloudTranslate("AIzaSECRET").translate("Hello", "en", "pt") == "Olá"
    _m, url, kw = s.calls[0]
    assert "SECRET" not in url and kw["headers"]["X-Goog-Api-Key"] == "AIzaSECRET"
    net([("translation.googleapis.com", Resp(400, body={"error": {"message": "API key not valid. Please pass a valid API key."}}))])
    with pytest.raises(TranslationError) as e:
        GoogleCloudTranslate("x").translate("Hello", "en", "pt")
    assert e.value.code == "bad_key"


# ------------------------------------------------------------------ Baidu / Youdao / NiuTrans
def test_baidu_sign_and_errors(net):
    from egt.translate.official import BaiduTranslate
    assert BaiduTranslate.sign("2015063000000001", "apple", "1435660288", "12345678") == \
        hashlib.md5(b"2015063000000001apple143566028812345678").hexdigest()
    s = net([("baidu", Resp(body={"from": "en", "to": "pt", "trans_result": [{"src": "a", "dst": "Olá"}, {"src": "b", "dst": "mundo"}]}))])
    assert BaiduTranslate("id", "sec").translate("Hello\nworld", "ja", "ko") == "Olá\nmundo"
    d = s.calls[0][2]["data"]
    assert d["from"] == "jp" and d["to"] == "kor" and d["sign"] == BaiduTranslate.sign("id", "Hello\nworld", d["salt"], "sec")
    assert "sec" not in json.dumps(d)
    net([("baidu", Resp(body={"error_code": "54001", "error_msg": "Invalid Sign"}))])
    with pytest.raises(TranslationError) as e:
        BaiduTranslate("id", "sec").translate("x", "en", "pt")
    assert e.value.code == "bad_key"
    net([("baidu", Resp(body={"error_code": "54003"}))])
    with pytest.raises(RateLimited):
        BaiduTranslate("id", "sec").translate("x", "en", "pt")
    assert BaiduTranslate("id", "").available()[0] is False


def test_youdao_sign_v3(net):
    from egt.translate.official import YoudaoTranslate
    q = "abcdefghijklmnopqrstuvwxyz"
    expect = hashlib.sha256(("K" + "abcdefghij" + "26" + "qrstuvwxyz" + "S1" + "T1" + "SEC").encode()).hexdigest()
    assert YoudaoTranslate.sign("K", q, "S1", "T1", "SEC") == expect
    s = net([("youdao", Resp(body={"errorCode": "0", "translation": ["Olá"]}))])
    assert YoudaoTranslate("K", "SEC").translate("Hello", "", "zh-CN") == "Olá"
    d = s.calls[0][2]["data"]
    assert d["to"] == "zh-CHS" and d["signType"] == "v3" and "SEC" not in json.dumps(d)
    net([("youdao", Resp(body={"errorCode": "108"}))])
    with pytest.raises(TranslationError) as e:
        YoudaoTranslate("K", "SEC").translate("x", "en", "pt")
    assert e.value.code == "bad_key"


def test_niutrans(net):
    from egt.translate.official import NiuTransTranslate
    s = net([("niutrans", Resp(body={"from": "en", "to": "pt", "tgt_text": "Olá"}))])
    assert NiuTransTranslate("k").translate("Hello", "en", "zh-TW") == "Olá"
    assert s.calls[0][2]["data"]["to"] == "cht"
    net([("niutrans", Resp(body={"error_code": "13001", "error_msg": "Balance is insufficient."}))])
    with pytest.raises(TranslationError) as e:
        NiuTransTranslate("k").translate("x", "en", "pt")
    assert e.value.code == "bad_key"


# ------------------------------------------------------------------ comum
def test_network_errors_are_coded(monkeypatch):
    import requests

    from egt.translate.google import GoogleTranslate

    class S:
        def request(self, *a, **k):
            raise requests.ConnectionError("x https://secret-url?key=abc")
    monkeypatch.setattr(H, "session", lambda: S())
    monkeypatch.setattr(H, "throttle", lambda *a, **k: None)
    with pytest.raises(TranslationError) as e:
        GoogleTranslate().translate("hi", "en", "pt")
    assert e.value.code == "network" and "abc" not in str(e.value)


def test_throttle_spaces_requests(monkeypatch):
    slept = []
    monkeypatch.setattr("time.sleep", lambda s: slept.append(s))
    H.reset_throttle()
    H.throttle("x", 0.5)
    H.throttle("x", 0.5)
    assert slept and 0.3 < slept[0] <= 0.5


def test_catalog_matches_settings():
    from egt.config import DEFAULTS, SECRET_PATHS
    from egt.translate.providers import (
        DEFAULT_ENABLED,
        DEFAULT_ORDER,
        PROVIDERS,
        secret_paths,
    )
    assert set(secret_paths()) <= set(SECRET_PATHS)
    assert DEFAULTS["translation"]["order"] == DEFAULT_ORDER
    assert DEFAULTS["translation"]["enabled"] == DEFAULT_ENABLED
    for p in PROVIDERS:
        for f in p.fields:
            assert f.key in DEFAULTS["translation"], f.key
        if p.kind == "key":
            assert p.key_url.startswith("https://") and p.howto
        if not p.official:
            assert p.kind == "free"
