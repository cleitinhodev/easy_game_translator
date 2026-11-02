// Mensagens do backend vêm em português. As que aparecem para o usuário com mais frequência são traduzidas aqui (por prefixo);
// as demais (detalhes técnicos de motores/OCR) continuam como o backend envia.
const MAP: [RegExp, string][] = [
  [/^Nenhuma região/, 'toast.no_region'],
  [/^Script \[(\w+)\]/, 'sc.err.'],
  [/^IA não configurada/, 'be.ai_unconfigured'],
  [/^falha na captura/, 'be.capture_fail'],
  [/^falha na narração/, 'be.tts_fail'],
  [/^áudio vazio/, 'be.empty_audio'],
  [/^região inválida/, 'be.invalid_region'],
  [/^(motor|alfabeto|idioma|canal|configuração) (desconhecid|inválid)/, 'be.unknown'],
  [/^(perfil|componente) não encontrad|^componente desconhecido/, 'be.not_found'],
  [/^instale: pip install|^argostranslate não instalado/, 'be.install_pkg'],
]
export function mapBackend(text: string, t: (k: string, p?: Record<string, string | number>) => string): string {
  for (const [re, key] of MAP) {
    const m = re.exec(text)
    if (!m) continue
    if (key === 'sc.err.') {        // erros do modo Scripts: "Script [codigo]: detalhe"
      const detail = text.replace(/^Script \[\w+\]:?\s*/, '')
      const k = `sc.err.${m[1]}`
      const msg = t(k, { detail })
      return msg === k ? text : msg + (detail && ['exit', 'script_error', 'count', 'unsupported', 'start'].includes(m[1]) ? ` — ${detail}` : '')
    }
    return t(key, { err: text.replace(/^[^:]*:\s*/, '') })
  }
  return text
}
