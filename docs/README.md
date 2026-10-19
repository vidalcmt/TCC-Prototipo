# Documentação

- `Documentacao_Tecnica.docx`: documentação técnica do sistema, atualizada no
  mesmo pull request de cada mudança.
- `fonte/gerar_documentacao.js`: texto da documentação e gerador do .docx.
  Mantendo o texto aqui, cada mudança na documentação aparece no pull request
  e pode ser revisada junto com o código.

Para gerar de novo (precisa do Node.js):

```bash
npm install docx
node docs/fonte/gerar_documentacao.js
```
