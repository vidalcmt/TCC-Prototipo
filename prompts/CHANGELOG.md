# Registro de versões dos prompts

Cada versão usada na coleta fica congelada. Uma mudança gera um arquivo novo
(v2, v3...) e uma entrada aqui, com a data e o motivo. A coluna prompt_versao
da tabela metrica_requisicao aponta para estas versões.

## objetiva_v2 (20/10/2026)

Pedido do autor após a revisão da v1: a explicação de cada alternativa errada
deve mostrar a natureza do erro e como o estudante poderia percebê-lo usando
outros conhecimentos (por exemplo, época trocada entre Modernismo e período
contemporâneo, ou contexto histórico errado).

Mudanças em relação à v1:
- contrato novo (CorrecaoObjetivaV2) com três campos por alternativa:
  tipo_de_erro (categoria fechada), elemento_incorreto (o ponto exato que
  está errado) e como_verificar (como perceber o erro sem o gabarito);
- regras específicas para erros de época, contexto, conceito e leitura;
- pede o período em vez de um ano quando não houver segurança sobre a data.

## objetiva_v1 (19/10/2026)

Primeira versão do prompt das questões objetivas. Pede, para cada alternativa
incorreta, o erro de raciocínio que leva a escolhê-la (RF02 e RF03), e para a
correta, os elementos do enunciado que a sustentam. Proíbe contrariar o
gabarito informado pelo professor e inventar dados fora do enunciado.

## teste_v1 (16/10/2026)

Prompt mínimo da etapa 1, usado só para confirmar que a chamada ao modelo e o
registro de métricas funcionam. Não é usado na coleta.
