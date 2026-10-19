'use strict'
const fs = require('node:fs')
const path = require('node:path')
const { app } = require('electron')

const i18nDir = path.join(__dirname, '..', 'shared', 'i18n')
const dicts = {}
function loadDict(lang) {
  if (!dicts[lang]) {
    try { dicts[lang] = JSON.parse(fs.readFileSync(path.join(i18nDir, `${lang}.json`), 'utf8')) } catch { dicts[lang] = {} }
  }
  return dicts[lang]
}
const LOCALES = (() => { try { return JSON.parse(fs.readFileSync(path.join(i18nDir, '_locales.json'), 'utf8')) } catch { return [{ code: 'pt-BR' }, { code: 'en' }] } })()
const isRtl = (l) => !!LOCALES.find((x) => x.code === l)?.rtl
/** Um idioma do sistema → idioma suportado (mesma regra do renderer, src/lib/i18n.ts). */
function matchLocale(tag) {
  const t = String(tag).replace('_', '-').toLowerCase()
  const exact = LOCALES.find((x) => x.code.toLowerCase() === t)
  if (exact) return exact.code
  const [base, ...rest] = t.split('-')
  if (base === 'zh') return rest.some((r) => ['tw', 'hk', 'mo', 'hant'].includes(r)) ? 'zh-TW' : 'zh-CN'
  if (base === 'pt') return 'pt-BR'
  if (base === 'nb' || base === 'nn') return null
  return LOCALES.find((x) => x.code.toLowerCase() === base)?.code ?? null
}
function systemLanguages() {
  const out = []
  try { out.push(...app.getPreferredSystemLanguages()) } catch { /* ignora */ }
  try { out.push(app.getSystemLocale()) } catch { /* ignora */ }
  try { out.push(app.getLocale()) } catch { /* ignora */ }
  return out.filter(Boolean)
}
/** 'auto' (ou vazio) → idioma do sistema; sem correspondência → inglês. */
function resolveLang(pref) {
  if (pref && pref !== 'auto') return LOCALES.some((x) => x.code === pref) ? pref : (matchLocale(pref) || 'en')
  for (const s of systemLanguages()) { const m = matchLocale(s); if (m) return m }
  return 'en'
}
/** Traduz uma chave (idioma → inglês → pt-BR). */
function makeT(lang) {
  const d = loadDict(lang), en = loadDict('en'), fb = loadDict('pt-BR')
  return (key, params) => {
    let s = d[key] ?? en[key] ?? fb[key] ?? key
    if (params) for (const [k, v] of Object.entries(params)) s = s.replaceAll(`{${k}}`, String(v))
    return s
  }
}

function userFile(name) { return path.join(app.getPath('userData'), name) }
function readJson(name, fallback) {
  try { return JSON.parse(fs.readFileSync(userFile(name), 'utf8')) } catch { return fallback }
}
function writeJson(name, data) {
  try { fs.mkdirSync(app.getPath('userData'), { recursive: true }); fs.writeFileSync(userFile(name), JSON.stringify(data, null, 2)) } catch { /* ignora */ }
}

/** Windows 11 (build >= 22000) aceita backgroundMaterial; 22621+ tem Mica "oficial" para apps. */
function winBuild() {
  if (process.platform !== 'win32') return 0
  const m = /^(\d+)\.(\d+)\.(\d+)/.exec(require('node:os').release())
  return m ? Number(m[3]) : 0
}

module.exports = { LOCALES, isRtl, matchLocale, resolveLang, systemLanguages, makeT, readJson, writeJson, winBuild }
