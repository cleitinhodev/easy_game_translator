#!/usr/bin/env node
// Exemplo REAL para o modo Scripts do Easy Game Translator (contrato v1), em Node.js.
// Glossário OFFLINE (nada sai do seu PC): troca termos de jogos em inglês pelos equivalentes em português.
// Mostra a SAÍDA EM TEXTO PURO: canal único = o texto impresso; canal duplo = as duas partes separadas
// por uma linha contendo só ---  (o EGT também aceita JSON {"outputs": [...]}).
//
// ENTRADA (stdin, JSON UTF-8): {"version": 1, "mode": "single"|"dual", "inputs": ["..."] ou ["A", "B"],
//                               "source_lang": "en", "target_lang": "pt", "channels": [...]}
// Precisa do Node.js instalado (https://nodejs.org). Edite o GLOSSARIO à vontade.
'use strict'

// Frases inteiras (conferidas primeiro, sem diferenciar maiúsculas)
const FRASES = {
  'game over': 'Fim de jogo',
  'press start': 'Aperte Start',
  'new game': 'Novo jogo',
  'continue?': 'Continuar?',
  'level up!': 'Subiu de nível!',
  'quest completed': 'Missão concluída',
  'you died': 'Você morreu',
  'save game': 'Salvar jogo',
  'load game': 'Carregar jogo',
}

// Palavras e expressões curtas (a mais longa ganha)
const GLOSSARIO = {
  'the king': 'o rei', 'the queen': 'a rainha', 'throne room': 'sala do trono', 'awaits you': 'espera por você',
  'in the': 'na', 'take this': 'pegue esta', 'key': 'chave', 'it opens': 'ela abre', 'the old': 'a velha',
  'cellar door': 'porta da adega', 'we must leave': 'precisamos partir', 'before the storm arrives': 'antes que a tempestade chegue', 'before': 'antes de', 'the storm': 'a tempestade',
  'arrives': 'chegar', 'careful': 'cuidado', 'the bridge': 'a ponte', 'will not hold': 'não vai aguentar',
  'much longer': 'muito mais tempo', 'you have found the legendary': 'você encontrou a lendária', 'legendary': 'lendária', 'sword': 'espada',
  'of dawn': 'da aurora', 'the': 'o', 'sword of dawn': 'espada da aurora', 'health': 'vida', 'mana': 'mana',
  'potion': 'poção', 'potions': 'poções', 'healing': 'cura', 'gold': 'ouro', 'quest': 'missão', 'inventory': 'inventário',
  'anyone want to join the raid': 'alguém quer entrar na raid', 'the healing potions': 'as poções de cura', 'healing potions': 'poções de cura', 'tonight': 'hoje à noite', 'i will bring': 'eu levo',
  'meet at the north gate': 'encontro no portão norte', 'in ten minutes': 'em dez minutos', 'raid': 'raid',
  'hello': 'olá', 'adventurer': 'aventureiro', 'the gate is closed': 'o portão está fechado', 'gate': 'portão',
}

const esc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const termos = Object.keys(GLOSSARIO).sort((a, b) => b.length - a.length)
const RE = new RegExp(`\\b(${termos.map(esc).join('|')})\\b`, 'gi')

function capitalizar(orig, troca) {
  return orig[0] && orig[0] === orig[0].toUpperCase() && orig[0] !== orig[0].toLowerCase()
    ? troca.charAt(0).toUpperCase() + troca.slice(1) : troca
}

function traduzir(texto) {
  const t = String(texto || '').trim()
  if (!t) return ''
  const frase = FRASES[t.toLowerCase()]
  if (frase) return frase
  return t.replace(RE, (m) => capitalizar(m, GLOSSARIO[m.toLowerCase()]))
}

let entrada = ''
process.stdin.setEncoding('utf8')
process.stdin.on('data', (c) => { entrada += c })
process.stdin.on('end', () => {
  let pedido
  try { pedido = JSON.parse(entrada) } catch (e) {
    process.stderr.write('entrada inválida: ' + e.message + '\n'); process.exit(2)
  }
  const saidas = (pedido.inputs || []).map(traduzir)
  // texto puro: no canal duplo, uma linha com só --- separa a saída A da saída B
  process.stdout.write(saidas.join('\n---\n') + '\n')
})
