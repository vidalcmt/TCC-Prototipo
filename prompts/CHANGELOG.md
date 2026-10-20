# Registro de versões dos prompts

Cada versão usada na coleta fica congelada. Uma mudança gera um arquivo novo
(v2, v3...) e uma entrada aqui, com a data e o motivo. A coluna prompt_versao
da tabela metrica_requisicao aponta para estas versões.

## objetiva_v1 (19/10/2026)

Primeira versão do prompt das questões objetivas. Pede, para cada alternativa
incorreta, o erro de raciocínio que leva a escolhê-la (RF02 e RF03), e para a
correta, os elementos do enunciado que a sustentam. Proíbe contrariar o
gabarito informado pelo professor e inventar dados fora do enunciado.

## teste_v1 (16/10/2026)

Prompt mínimo da etapa 1, usado só para confirmar que a chamada ao modelo e o
registro de métricas funcionam. Não é usado na coleta.
