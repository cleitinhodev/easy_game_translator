"""Catálogo dos tradutores: metadados para a interface (tipo, limites, privacidade, campos, links) e
fábricas a partir das configurações. Fonte única: a aba Tradução é montada a partir daqui.

Tipos: free = grátis sem chave · key = conta/chave do usuário · self = servidor próprio · offline = no PC.
`official=False` → endpoint da web, não documentado: "não oficial, pode parar de funcionar".
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class FieldSpec:
    key: str                 # caminho em settings: translation.<key>
    kind: str                # secret | text | url | select | email
    label: str               # chave i18n
    placeholder: str = ""
    options: tuple = ()


@dataclass(frozen=True)
class Provider:
    id: str
    name: str
    kind: str
    official: bool
    receiver: str            # quem recebe o texto ("" = ninguém / o seu servidor)
    country: str             # ISO 3166 (a interface mostra o nome no idioma do usuário); "" = varia
    limit: tuple             # (período, quantidade): month/day/once/fair/credit/local/self
    fields: tuple = ()
    site: str = ""
    key_url: str = ""        # onde criar a chave (só para kind=key/self)
    docs: str = ""
    howto: str = ""          # chave i18n com o passo a passo curto
    note: str = ""           # chave i18n com observação
    default_on: bool = False
    meta: dict = field(default_factory=dict)

    def public(self) -> dict:
        d = asdict(self)
        d["fields"] = [asdict(f) for f in self.fields]
        d["limit"] = {"period": self.limit[0], "amount": self.limit[1]}
        return d


def _f(key, kind, label, placeholder="", options=()):
    return FieldSpec(key, kind, label, placeholder, tuple(options))


PROVIDERS: tuple[Provider, ...] = (
    Provider("google", "Google Translate", "free", False, "Google", "US", ("fair", 0),
             site="https://translate.google.com", default_on=True),
    Provider("bing", "Bing Translator", "free", False, "Microsoft (Bing)", "US", ("fair", 0),
             site="https://www.bing.com/translator", default_on=True),
    Provider("mymemory", "MyMemory", "free", True, "Translated (MyMemory)", "IT", ("day", 5000),
             fields=(_f("mymemory_email", "email", "tr.f.email", "email@example.com"),),
             site="https://mymemory.translated.net", docs="https://mymemory.translated.net/doc/spec.php",
             note="tr.note.mymemory", default_on=True),
    Provider("mozhi", "Mozhi", "free", True, "Mozhi", "", ("fair", 0),
             fields=(_f("mozhi_engine", "select", "tr.f.engine", "", ("duckduckgo", "yandex", "google")),
                     _f("mozhi_url", "url", "tr.f.instance", "tr.f.auto_instance")),
             site="https://codeberg.org/aryak/mozhi", docs="https://codeberg.org/aryak/mozhi#instances",
             note="tr.note.mozhi"),
    Provider("yandex", "Yandex Translate", "free", False, "Yandex", "RU", ("fair", 0),
             site="https://translate.yandex.com", note="tr.note.yandex"),
    Provider("apertium", "Apertium", "free", True, "Apertium (apertium.org)", "", ("fair", 0),
             fields=(_f("apertium_url", "url", "tr.f.url", "https://apertium.org/apy"),),
             site="https://www.apertium.org", docs="https://wiki.apertium.org/wiki/Apertium-apy",
             note="tr.note.apertium"),
    Provider("libre", "LibreTranslate", "self", True, "", "", ("self", 0),
             fields=(_f("libre_url", "url", "tr.f.url", "http://localhost:5000"),
                     _f("libre_key", "secret", "tr.f.key_optional")),
             site="https://libretranslate.com", key_url="https://portal.libretranslate.com",
             docs="https://docs.libretranslate.com", howto="tr.howto.libre"),
    Provider("deepl", "DeepL", "key", True, "DeepL SE", "DE", ("once", 1_000_000),
             fields=(_f("deepl_key", "secret", "tr.f.key"),),
             site="https://www.deepl.com", key_url="https://www.deepl.com/pro-api",
             docs="https://developers.deepl.com/docs", howto="tr.howto.deepl", note="tr.note.deepl"),
    Provider("microsoft", "Azure AI Translator", "key", True, "Microsoft Azure", "US", ("month", 2_000_000),
             fields=(_f("microsoft_key", "secret", "tr.f.key"), _f("microsoft_region", "text", "tr.f.region", "brazilsouth")),
             site="https://azure.microsoft.com/products/ai-services/ai-translator",
             key_url="https://portal.azure.com/#create/Microsoft.CognitiveServicesTextTranslation",
             docs="https://learn.microsoft.com/azure/ai-services/translator/text-translation/reference/v3/translate",
             howto="tr.howto.microsoft"),
    Provider("gcloud", "Google Cloud Translation", "key", True, "Google Cloud", "US", ("month", 500_000),
             fields=(_f("gcloud_key", "secret", "tr.f.key"),),
             site="https://cloud.google.com/translate", key_url="https://console.cloud.google.com/apis/library/translate.googleapis.com",
             docs="https://cloud.google.com/translate/docs/basic/translating-text", howto="tr.howto.gcloud",
             note="tr.note.gcloud"),
    Provider("baidu", "Baidu Fanyi (百度翻译)", "key", True, "Baidu", "CN", ("month", 50_000),
             fields=(_f("baidu_appid", "text", "tr.f.appid"), _f("baidu_key", "secret", "tr.f.secret")),
             site="https://fanyi-api.baidu.com", key_url="https://fanyi-api.baidu.com/manage/developer",
             docs="https://fanyi-api.baidu.com/doc/21", howto="tr.howto.baidu"),
    Provider("youdao", "Youdao (有道智云)", "key", True, "NetEase Youdao", "CN", ("credit", 0),
             fields=(_f("youdao_appkey", "text", "tr.f.appid"), _f("youdao_secret", "secret", "tr.f.secret")),
             site="https://ai.youdao.com", key_url="https://ai.youdao.com/console/",
             docs="https://ai.youdao.com/DOCSIRMA/html/trans/api/wbfy/index.html", howto="tr.howto.youdao"),
    Provider("niutrans", "NiuTrans (小牛翻译)", "key", True, "NiuTrans", "CN", ("day", 200_000),
             fields=(_f("niutrans_key", "secret", "tr.f.key"),),
             site="https://niutrans.com", key_url="https://niutrans.com/cloud/account_info/info",
             docs="https://niutrans.com/documents/contents/trans_text", howto="tr.howto.niutrans"),
    Provider("argos", "Argos Translate", "offline", True, "", "", ("local", 0),
             site="https://github.com/argosopentech/argos-translate", note="tr.note.argos"),
)
BY_ID = {p.id: p for p in PROVIDERS}
DEFAULT_ORDER = [p.id for p in PROVIDERS]
DEFAULT_ENABLED = [p.id for p in PROVIDERS if p.default_on]
REMOVED = {"lingva": "mozhi"}       # motores removidos → substituto (migração das configurações)


def factories(settings) -> dict[str, Callable]:
    """{id: fábrica} — nada de rede aqui; as chaves são lidas (decifradas) só quando o motor é criado."""
    from .apertium import ApertiumTranslate
    from .argos import ArgosTranslate
    from .bing import BingTranslate
    from .google import GoogleTranslate
    from .libre import LibreTranslate
    from .mozhi import MozhiTranslate
    from .mymemory import MyMemoryTranslate
    from .official import (
        BaiduTranslate,
        DeepLTranslate,
        GoogleCloudTranslate,
        MicrosoftTranslate,
        NiuTransTranslate,
        YoudaoTranslate,
    )
    from .yandex import YandexTranslate

    tr = settings.section("translation")
    to = float(tr.get("timeout", 8.0))
    sec = settings.secret
    return {
        "google": lambda: GoogleTranslate(to),
        "bing": lambda: BingTranslate(to),
        "mymemory": lambda: MyMemoryTranslate(to, sec("translation.mymemory_email")),
        "mozhi": lambda: MozhiTranslate(tr.get("mozhi_url", ""), tr.get("mozhi_engine", "duckduckgo"), to),
        "yandex": lambda: YandexTranslate(to),
        "apertium": lambda: ApertiumTranslate(tr.get("apertium_url", ""), to),
        "libre": lambda: LibreTranslate(tr.get("libre_url", ""), sec("translation.libre_key"), to),
        "deepl": lambda: DeepLTranslate(sec("translation.deepl_key"), to),
        "microsoft": lambda: MicrosoftTranslate(sec("translation.microsoft_key"), tr.get("microsoft_region", ""), to),
        "gcloud": lambda: GoogleCloudTranslate(sec("translation.gcloud_key"), to),
        "baidu": lambda: BaiduTranslate(tr.get("baidu_appid", ""), sec("translation.baidu_key"), to),
        "youdao": lambda: YoudaoTranslate(tr.get("youdao_appkey", ""), sec("translation.youdao_secret"), to),
        "niutrans": lambda: NiuTransTranslate(sec("translation.niutrans_key"), to),
        "argos": lambda: ArgosTranslate(),
    }


def secret_paths() -> tuple[str, ...]:
    return tuple(f"translation.{f.key}" for p in PROVIDERS for f in p.fields if f.kind in ("secret", "email"))
