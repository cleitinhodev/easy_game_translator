# Publicar uma nova versão no GitHub

Repositório: <https://github.com/cleitinhodev/easy_game_translator> (privado) · branch `main` · tags `vX.Y.Z`.
Pré-requisitos: `gh auth status` (conta `cleitinhodev`, escopo `repo`), Node, `.venv`, backend empacotado.

```bash
V=4.0.6                                    # nova versão
cd egt_v4                                   # pasta do projeto

# 1) versão: package.json / package-lock.json (raiz), textos de fallback e, se o backend mudou, backend/egt/__init__.py
npm version $V --no-git-tag-version
grep -rn "4\.0\.[0-9]" src/components/Titlebar.tsx src/components/HelpModal.tsx src/components/Intro.tsx src/store.ts

# 2) CHANGELOG.md: nova seção "## $V — AAAA-MM-DD" no topo

# 3) testes e build
npm test && npm run build
#   backend: só se mudou →  npm run build:backend  (ou PyInstaller no Wine)  &&  wine backend/dist/EGTBackend/EGTBackend.exe --selftest
npx electron-builder --win nsis portable --x64          # release/EasyGameTranslator-$V-{setup,portable}.exe

# 4) varredura de segredos antes do commit (não deve imprimir nada)
git ls-files -co --exclude-standard | xargs rg -n -e 'AIza[0-9A-Za-z_-]{20}' -e 'gh[oprsu]_[A-Za-z0-9]{20}' -e 'github_pat_' \
  -e '\bsk-[A-Za-z0-9_-]{20}' -e '/home/box' -e 'C:\\\\Users\\\\' -e 'PRIVATE KEY'

# 5) commit + tag + push
git add -A && git status --short
git -c user.name=CleitinhoDEV -c user.email=139408626+cleitinhodev@users.noreply.github.com commit -m "Easy Game Translator $V"
git tag -a v$V -m "Easy Game Translator $V"
git push origin main && git push origin v$V

# 6) release com os executáveis inteiros + SHA256SUMS.txt
cd release && sha256sum EasyGameTranslator-$V-setup.exe EasyGameTranslator-$V-portable.exe > SHA256SUMS.txt && cd ..
#   escreva as notas (pt-BR) em /tmp/notes.md: resumo, instalação, aviso do SmartScreen, SHA-256 de cada arquivo
gh release create v$V --repo cleitinhodev/easy_game_translator --title "Easy Game Translator $V" --notes-file /tmp/notes.md --latest \
  release/EasyGameTranslator-$V-setup.exe release/EasyGameTranslator-$V-portable.exe release/SHA256SUMS.txt
gh release view v$V --repo cleitinhodev/easy_game_translator --json assets --jq '.assets[] | [.name, .size] | @tsv'   # confira os tamanhos
```

Nunca versionar: `node_modules/`, `dist/`, `release/`, `.venv/`, `backend/build|dist/`, executáveis/zips, rascunhos de tradução,
screenshots locais, configuração do usuário (`%APPDATA%\EasyGameTranslator`). O `.gitignore` já cobre isso.
