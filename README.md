# TCC-Prototipo

Protótipo do TCC II: sistema de apoio ao professor que corrige questões
objetivas e discursivas e gera feedback elaborado por meio de um modelo de
linguagem, mantendo a atribuição final da nota sob decisão humana.

O protótipo é o instrumento que gera os dados da seção de Resultados do artigo.
Por isso, toda chamada ao modelo registra tokens, custo, latência, versão do
modelo e versão do prompt desde a primeira requisição.

## Tecnologias

| Camada | Escolha |
| --- | --- |
| Linguagem | Python 3.11 ou superior |
| API web | FastAPI, com páginas renderizadas no servidor (Jinja2) |
| Banco | SQLite, com SQLAlchemy e migrações pelo Alembic |
| Modelo de linguagem | OpenAI `gpt-6.1-sol`, com saída estruturada validada por Pydantic |
| Testes | pytest |

## Como rodar

1. Crie e ative um ambiente virtual:

   ```bash
   python -m venv .venv
   # Windows
   .venv\Scripts\activate
   # Linux ou macOS
   source .venv/bin/activate
   ```

2. Instale as dependências:

   ```bash
   pip install -r requirements.txt
   ```

3. Copie `.env.example` para `.env`, coloque a sua chave da API da OpenAI e
   gere uma `SECRET_KEY` (o comando está no próprio arquivo).
   O `.env` está no `.gitignore` e nunca deve ir para o GitHub.

4. Crie o banco:

   ```bash
   alembic upgrade head
   ```

5. Crie a primeira conta de administrador. A senha provisória aparece uma
   única vez no terminal e precisa ser trocada no primeiro acesso:

   ```bash
   python -m scripts.criar_admin --nome "Seu Nome" --email voce@exemplo.com
   ```

   As demais contas são criadas pela página Usuários, dentro do sistema.
   Não existe cadastro aberto.

6. Faça uma requisição de teste (critério de pronto da etapa 1):

   ```bash
   python -m scripts.teste_requisicao
   ```

   A saída mostra tokens, custo e latência. A mesma linha aparece na página de
   métricas.

7. Suba o servidor e abra <http://localhost:8000>:

   ```bash
   uvicorn app.main:app --reload
   ```

8. Rode os testes (não gastam crédito, usam um cliente falso):

   ```bash
   pytest
   ```

Esqueceu a senha? Gere uma provisória nova:

```bash
python -m scripts.redefinir_senha --listar
python -m scripts.redefinir_senha --email voce@exemplo.com
```

## Publicação

O passo a passo para colocar o sistema no ar no Google Cloud, com HTTPS e
cópia diária do banco, está em [`deploy/README.md`](deploy/README.md).

## Estrutura

```
app/
  main.py            aplicação FastAPI
  config.py          leitura do .env
  inicio.py          página inicial e fila de revisão
  contas/            login, senhas, papéis e limite diário
  database.py        conexão com o SQLite
  models.py          tabelas da especificação
  correcao/
    llm.py           ponto único de chamada ao modelo, já instrumentado
    prompts.py       carregamento de prompts versionados
  metricas/
    precos.py        cálculo de custo a partir dos tokens
    router.py        página de métricas e exportação em CSV
  questoes/          cadastro de questões (etapas 2 e 3)
  revisao/           tela de aceite do professor (etapa 4)
  atividades/        atividades e impressão em A4
  templates/         páginas HTML
  static/            estilo, fontes e script do tema claro/escuro
config/precos.toml   preços por modelo, com fonte e data de acesso
prompts/             prompts versionados e registro de mudanças
alembic/             migrações do banco
baseline/            similaridade vetorial, fora do produto (etapa 5)
dados/               corpus congelado (etapa 5)
scripts/             utilitários de linha de comando (admin, senha, cópia do banco)
deploy/              instalação no servidor: scripts, serviços e Caddyfile
tests/               testes automatizados
```

## Regras do projeto

- **Toda chamada ao modelo passa por `app/correcao/llm.py`.** É lá que as
  métricas são gravadas, inclusive nas falhas.
- **Prompt usado na coleta não é editado.** Uma mudança gera uma nova versão em
  `prompts/<nome>/v<N>.md` e uma entrada em `prompts/CHANGELOG.md`.
- **Preço atualizado leva nova data de acesso** em `config/precos.toml`.
- **A nota final só existe após a ação do professor** (RF11).
- **Toda página exige login**, exceto `/entrar` e `/saude`. Métricas e
  usuários são só para administradores.

## Acompanhamento

As etapas estão nas
[issues do repositório](https://github.com/vidalcmt/tcc-prototipo/issues),
agrupadas por marcos semanais.
