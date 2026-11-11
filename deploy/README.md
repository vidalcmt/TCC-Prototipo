# Publicação no Google Cloud

Guia para colocar a Devolutiva no ar numa máquina virtual do Compute Engine,
com HTTPS e cópia de segurança diária do banco. Tudo é feito pelo navegador:
não é preciso instalar nada no computador.

## Como fica

```
navegador ──HTTPS──> Caddy (porta 443) ──> uvicorn (127.0.0.1:8000) ──> tcc.db
                     certificado automático       aplicação FastAPI       SQLite
```

- **Caddy:** recebe as conexões, obtém e renova sozinho o certificado HTTPS
  (Let's Encrypt) e repassa as requisições para a aplicação.
- **Aplicação:** roda como serviço do sistema (`devolutiva.service`), num
  usuário próprio sem permissão de administrador, e volta sozinha se cair ou
  se a máquina reiniciar.
- **Cópia do banco:** todo dia às 3h30 de Brasília
  (`devolutiva-copia.timer`), guardada por 30 dias em `/var/backups/devolutiva`.
- **Endereço:** sem domínio próprio, o site usa o IP da máquina no formato
  `34-95-10-20.sslip.io`. O serviço sslip.io só traduz esse nome para o IP, e
  isso basta para o Let's Encrypt emitir o certificado.

## 1. Criar a máquina

No [console do Google Cloud](https://console.cloud.google.com), com o projeto
dos créditos selecionado:

1. Abra **Compute Engine > Instâncias de VM** e ative a API, se o console pedir.
2. Clique em **Criar instância** e preencha:
   - **Nome:** `devolutiva`
   - **Região:** `southamerica-east1 (São Paulo)`
   - **Tipo de máquina:** `e2-small` (2 GB de memória). A estimativa de custo
     mensal aparece à direita.
   - **Disco de inicialização:** Debian 12, 20 GB.
   - **Firewall:** marque **Permitir tráfego HTTP** e **Permitir tráfego HTTPS**.
3. Clique em **Criar** e espere a máquina ficar com o círculo verde.

## 2. Fixar o IP

O IP externo muda se a máquina for desligada, e o endereço do site depende
dele. Para fixá-lo:

1. Abra **Rede VPC > Endereços IP**.
2. Na linha do IP externo da máquina `devolutiva`, clique nos três pontos e em
   **Promover a endereço IP estático**. Dê o nome `devolutiva`.

## 3. Instalar

Na lista de instâncias, clique em **SSH** na linha da máquina. Abre um
terminal no navegador. Cole os comandos abaixo, um bloco por vez:

```bash
sudo apt-get update && sudo apt-get install -y git
sudo git clone https://github.com/vidalcmt/TCC-Prototipo.git /opt/devolutiva
sudo bash /opt/devolutiva/deploy/instalar.sh
```

O instalador pede a chave da API da OpenAI. Cole e tecle Enter; ela não
aparece na tela e fica só no arquivo `/opt/devolutiva/.env` da máquina, com
leitura restrita ao usuário da aplicação. A `SECRET_KEY` é gerada sozinha.

No fim, ele mostra o endereço do site e o comando para criar a sua conta:

```bash
cd /opt/devolutiva && sudo -u devolutiva .venv/bin/python -m scripts.criar_admin --nome "Seu Nome" --email voce@exemplo.com
```

Abra o endereço no navegador. O primeiro acesso pode levar até um minuto,
enquanto o certificado é emitido.

## 4. Levar os dados do seu computador (opcional)

Se as questões e correções que você já fez no computador devem ir para o
servidor, envie o arquivo `tcc.db` da pasta do projeto:

1. Na janela SSH, clique na engrenagem (ou em **Fazer upload de arquivo**) e
   escolha o `tcc.db`. Ele vai para a sua pasta pessoal na máquina.
2. Rode:

```bash
sudo bash /opt/devolutiva/deploy/usar_banco.sh ~/tcc.db
```

O banco que estava no servidor é guardado em `/var/backups/devolutiva` antes
da troca. As contas de usuário vêm junto com o arquivo: entre com a mesma
conta que você usa no computador.

Depois disso, use só o servidor, para que os dados da coleta fiquem num lugar só.

## 5. Cópia fora da máquina

A cópia diária fica no mesmo disco da máquina. Para ter uma cópia que
sobreviva à perda do disco, programe snapshots diários:

1. Abra **Compute Engine > Snapshots > Programações de snapshot** e crie uma
   programação diária, com retenção de 14 dias, na região `southamerica-east1`.
2. Em **Compute Engine > Discos**, abra o disco `devolutiva`, clique em
   **Editar** e escolha essa programação.

## 6. Leitura da escrita (Google Cloud Vision)

A leitura das bolinhas das objetivas funciona sem configuração. Para
transcrever a escrita das discursivas, o sistema usa o Google Cloud Vision, no
mesmo projeto do Google Cloud em que está a máquina. São quatro passos, todos
no navegador, mais um teste na janela SSH.

### 6.1 Ativar a API

1. Abra https://console.cloud.google.com/apis/library/vision.googleapis.com
   e confira, no seletor do alto da página, se o projeto é o da máquina
   `devolutiva`.
2. Clique em **Ativar**. Se aparecer um pedido de faturamento, vincule a mesma
   conta de faturamento da máquina: as primeiras 1.000 páginas por mês são
   gratuitas.

### 6.2 Criar a chave

1. Abra https://console.cloud.google.com/apis/credentials (mesmo projeto).
2. Clique em **Criar credenciais > Chave de API**. A chave aparece numa
   janela; ainda não copie, clique em **Editar chave de API** (ou feche e
   clique no nome da chave na lista).
3. Em **Nome**, escreva `devolutiva-vision`.
4. Em **Restrições do aplicativo**, escolha **Endereços IP** e adicione o IP
   fixo da máquina, o mesmo do endereço do site (por exemplo, `34.39.228.173`).
5. Em **Restrições de API**, escolha **Restringir chave**, abra a lista, marque
   só **Cloud Vision API** e clique em **OK**.
6. Clique em **Salvar**. As restrições levam alguns minutos para valer.

Com as duas restrições, mesmo que a chave vaze, ela só funciona a partir do
servidor e só para o Vision. Nunca cole a chave em conversas, prints, e-mails
ou no GitHub.

### 6.3 Colocar a chave no servidor

1. Na lista de credenciais, clique em **Mostrar chave** e copie.
2. Na janela SSH da máquina:

   ```
   sudo nano /opt/devolutiva/.env
   ```

3. Vá até o fim do arquivo e acrescente uma linha, sem espaços e sem aspas:

   ```
   GOOGLE_VISION_API_KEY=cole-a-chave-aqui
   ```

   Aproveite para conferir `LIMITE_CHAMADAS_DIA`: uma turma de 40 alunos com
   duas discursivas são 80 correções. Para corrigir a turma num dia, use por
   exemplo `LIMITE_CHAMADAS_DIA=150`.
4. Salve com `Ctrl+O`, `Enter`, e saia com `Ctrl+X`.
5. Reinicie a aplicação:

   ```
   sudo systemctl restart devolutiva
   ```

### 6.4 Testar

```
cd /opt/devolutiva && sudo -u devolutiva .venv/bin/python -m scripts.teste_vision
```

O teste envia uma imagem com uma frase e mostra o que foi lido. Se der certo,
aparece `Funcionou` e a frase lida. Se der errado, a mensagem diz o que
conferir:

| Mensagem | O que fazer |
|---|---|
| `GOOGLE_VISION_API_KEY não está no .env` | Repita o 6.3 e confira se a linha não tem espaço antes do `=` |
| `a chave está errada ou foi apagada` | Copie a chave de novo, sem espaços no começo ou no fim |
| `a Cloud Vision API não está ativada` | Repita o 6.1 e espere alguns minutos |
| `a chave não tem permissão para a Cloud Vision API` | No 6.2, marque Cloud Vision API em Restrições de API |
| `a chave está restrita a outro endereço IP` | No 6.2, confira o IP fixo da máquina |
| `o faturamento do projeto não está ativo` | Vincule a conta de faturamento ao projeto |

Depois do teste, a página **Folhas digitalizadas** de qualquer atividade deixa
de mostrar o aviso vermelho de que a leitura da escrita está desligada.

### Para testar no seu computador

A chave do servidor não funciona fora dele, por causa da restrição de IP.
Para testar no computador, crie uma segunda chave, com a restrição de API mas
sem a de IP, coloque no `.env` local e apague essa chave quando terminar.

### 6.5 Usar o Google Document AI em vez do Vision (opcional)

O Document AI é o outro serviço de OCR do Google, com um modelo mais recente,
leitura de letra à mão ligada por padrão e melhorias na ordem de leitura. O
preço é o mesmo do Vision (as primeiras 1.000 páginas por mês são gratuitas).
A diferença está na configuração: ele não aceita chave de API, e sim a conta
de serviço da máquina. Os processadores ficam nos Estados Unidos ou na Europa,
então as páginas são lidas lá.

1. **Ativar a API:** abra
   https://console.cloud.google.com/apis/library/documentai.googleapis.com
   (projeto da máquina) e clique em **Ativar**.
2. **Criar o processador:** em https://console.cloud.google.com/ai/document-ai
   abra a **Galeria de processadores** e, em **Geral**, escolha **Document
   OCR** (é o nome que o console dá ao Enterprise Document OCR). Dê o nome
   `devolutiva-ocr`, região **US** e clique em **Criar**. Em **Gerenciar
   versões**, deixe como padrão a versão estável mais recente
   (`pretrained-ocr-v2.1-2024-08-07` ou posterior), que melhorou a ordem de
   leitura. Na página do processador, copie o **Endpoint de previsão**: é um
   endereço como
   `https://us-documentai.googleapis.com/v1/projects/123/locations/us/processors/abc:process`.
   O que interessa é o trecho entre `v1/` e `:process`.
3. **Dar permissão à máquina:** em https://console.cloud.google.com/iam-admin/iam,
   ache a conta **Compute Engine default service account**, clique no lápis,
   **Adicionar outro papel** e escolha **Usuário da API Document AI**. Salve.
4. **Liberar o acesso da máquina às APIs:** em **Compute Engine > Instâncias de
   VM > devolutiva**, veja **Escopos de acesso da API**. Se estiver como
   acesso padrão, clique em **Parar** (o site fica fora do ar por um ou dois
   minutos; o IP fixo continua o mesmo), depois **Editar**, em escopos escolha
   **Permitir acesso total a todas as APIs do Cloud**, salve e clique em
   **Iniciar**. O que a máquina pode fazer continua limitado pelos papéis da
   conta de serviço.
5. **Configurar:** `sudo nano /opt/devolutiva/.env` e acrescente, com o trecho
   copiado no passo 2:

   ```
   LEITURA_SERVICO=documentai
   DOCUMENTAI_PROCESSADOR=projects/123/locations/us/processors/abc
   ```

   Mantenha a `GOOGLE_VISION_API_KEY`: ela é usada na comparação abaixo. Depois,
   `sudo systemctl restart devolutiva`.
6. **Testar:**
   `cd /opt/devolutiva && sudo -u devolutiva .venv/bin/python -m scripts.teste_vision --documentai`

Para voltar ao Vision, troque para `LEITURA_SERVICO=vision` e reinicie.

**Comparar os dois nas mesmas folhas:** depois de conferir e salvar algumas
folhas lidas, rode
`cd /opt/devolutiva && sudo -u devolutiva .venv/bin/python -m scripts.comparar_ocr --csv /tmp/comparacao.csv`.
O script lê de novo as mesmas páginas com os dois serviços, sem mudar nada no
sistema, e mostra a taxa de erro de cada um contra o texto que você salvou.

No computador, em vez dos passos 3 e 4, rode `gcloud auth application-default login`
com a sua conta do Google.

### 6.6 Revisão da transcrição pela IA (opcional)

Um modelo de linguagem olha a imagem de cada caixa e corrige o que o OCR leu
errado ("perede" vira "parede"), mantendo os erros do próprio aluno
("assasino" continua assim). As trocas aparecem embaixo de cada resposta na
página da folha, para você conferir antes de salvar.

1. No `.env` do servidor (`sudo nano /opt/devolutiva/.env`), acrescente
   `LEITURA_REVISAO_IA=true`.
2. Cada caixa com texto é uma chamada ao modelo. Se for ler uma turma inteira
   no mesmo dia, aumente o limite, por exemplo `LIMITE_CHAMADAS_DIA=300`.
3. `sudo systemctl restart devolutiva`.

A revisão vale para as leituras feitas depois de ligada. Para revisar uma
folha já lida, use "Ler de novo a folha digitalizada" na página da folha (só preenche as questões
que ainda não têm resposta salva).

**Medir se ajudou:** depois de conferir e salvar as folhas, rode
`cd /opt/devolutiva && sudo -u devolutiva .venv/bin/python -m scripts.medir_leitura`.
A linha "Revisão da IA" mostra a taxa de erro do OCR sozinho e com a revisão,
e em quantas respostas a revisão piorou o texto (trocas que você desfez).

## 7. Monitoramento

Há dois lugares para acompanhar o sistema, e eles se completam:

- **A página Monitoramento** (no menu, só para administradores) mostra o que
  acontece dentro do sistema: o tempo de resposta de cada rota, as requisições
  mais lentas, os erros, o tempo das chamadas à OpenAI e ao Google Cloud
  Vision, e a memória e o disco no momento. Não precisa configurar nada.
- **O Cloud Monitoring**, no Google Cloud, vê a máquina de fora: memória e
  disco ao longo do tempo, se o site está no ar e alertas por e-mail. É o que
  mostra um erro 502, que acontece justamente quando o sistema não responde.

O Cloud Monitoring não tem custo neste uso: as verificações de disponibilidade
têm 1 milhão de execuções grátis por mês, os alertas não são cobrados, as
métricas do agente cabem nos 150 MiB grátis por mês e os logs, nos 50 GiB.

### 7.1 Instalar o agente na máquina

Sem o agente, o Google Cloud só enxerga a CPU e a rede; a memória, que foi a
causa do erro 502, fica de fora. Na janela SSH:

```
cd ~
curl -sSO https://dl.google.com/cloudagents/add-google-cloud-ops-agent-repo.sh
sudo bash add-google-cloud-ops-agent-repo.sh --also-install
rm add-google-cloud-ops-agent-repo.sh
sudo cp /opt/devolutiva/deploy/ops-agent.yaml /etc/google-cloud-ops-agent/config.yaml
sudo systemctl restart google-cloud-ops-agent
sudo systemctl status google-cloud-ops-agent"*" --no-pager | grep -E "Active|ops-agent-"
```

As linhas devem mostrar `active (running)`. O arquivo `ops-agent.yaml` faz o
agente enviar também os logs da aplicação e do Caddy.

### 7.2 Ver a máquina

Em **Compute Engine > Instâncias de VM**, clique em `devolutiva` e abra a aba
**Observabilidade**. Depois de alguns minutos, aparecem os gráficos de CPU,
**memória**, disco e rede. Se a memória vive perto de 100%, ative a swap (a
reserva em disco) ou aumente a máquina.

### 7.3 Saber se o site caiu

1. Abra https://console.cloud.google.com/monitoring/uptime e clique em
   **Criar verificação de tempo de atividade**.
2. Protocolo **HTTPS**, tipo de recurso **URL**, nome do host
   `34-39-228-173.sslip.io` (ou o seu domínio) e caminho `/saude`. Frequência
   de **5 minutos**.
3. Em validação da resposta, marque **O conteúdo corresponde** e escreva `ok`.
4. Em alerta e notificação, deixe a criação do alerta ligada e escolha (ou crie)
   um canal de **e-mail** com o seu endereço.
5. Dê o nome `Devolutiva no ar` e clique em **Criar**.

A partir daí, se o site parar de responder, chega um e-mail. A própria
verificação mostra o tempo de resposta visto de várias regiões do mundo.

### 7.4 Alertas de memória e disco

Em https://console.cloud.google.com/monitoring/alerting, clique em **Criar
política**:

1. Métrica: **VM Instance > Memory > Memory utilization**. Filtro
   `state = used`. Condição: acima de **90** por **5 minutos**. Canal: o mesmo
   e-mail. Nome: `Devolutiva memória alta`.
2. Repita com **VM Instance > Disk > Disk utilization**, acima de **85**. Nome:
   `Devolutiva disco quase cheio`.

### 7.5 Procurar nos logs

Em https://console.cloud.google.com/logs, escolha a máquina e procure:

| Procurar | Para ver |
|---|---|
| `requisicao lenta` | Requisições que levaram mais de 3 segundos, com a rota |
| `requisicao com_erro` | Erros do servidor, com a rota |
| `Traceback` | O detalhe de um erro do Python |
| `connection refused` ou `502` | Momentos em que o Caddy não conseguiu falar com o sistema |
| `Out of memory` ou `Killed process` | O sistema encerrado por falta de memória |

O endereço completo das páginas não aparece nesses logs: o log de acesso do
uvicorn foi desligado (ele gravaria o código das folhas dos alunos), e o
sistema registra a rota no lugar.

## Dia a dia

| Para | Comando, na janela SSH |
|---|---|
| Atualizar com a versão mais recente da `main` | `sudo bash /opt/devolutiva/deploy/atualizar.sh` |
| Ver se a aplicação está no ar | `sudo systemctl status devolutiva` |
| Ver os erros mais recentes | `sudo journalctl -u devolutiva -n 50` |
| Fazer uma cópia do banco agora | `sudo systemctl start devolutiva-copia` |
| Listar as cópias | `ls -lh /var/backups/devolutiva` |
| Ver se o sistema está lento ou com erro | Menu **Monitoramento**, ou a seção 7 para o Cloud Monitoring |
| Testar a chave do Google Cloud Vision | `cd /opt/devolutiva && sudo -u devolutiva .venv/bin/python -m scripts.teste_vision` |
| Gerar senha provisória para quem esqueceu | `cd /opt/devolutiva && sudo -u devolutiva .venv/bin/python -m scripts.redefinir_senha --email voce@exemplo.com` |
| Baixar o banco para o computador | `sudo cp /opt/devolutiva/tcc.db ~ && sudo chown $USER ~/tcc.db`, depois a engrenagem da janela SSH, **Fazer download de arquivo**, `tcc.db` |

O `atualizar.sh` faz uma cópia do banco antes de qualquer mudança.

## Custos

- A máquina e o IP fixo são cobrados enquanto existirem, mesmo desligados
  (a máquina desligada cobra só o disco e o IP). Os créditos cobrem esses custos.
- O Google Cloud Vision cobra por página lida (uma chamada por página com
  discursivas); as primeiras 1.000 por mês são gratuitas. Confira os valores
  atuais em cloud.google.com/vision/pricing.
- As folhas digitalizadas ficam em `/opt/devolutiva/arquivos` e não entram na
  cópia diária do banco; o snapshot do disco as inclui.
- As chamadas ao modelo são cobradas pela OpenAI, à parte. O limite diário por
  pessoa (`LIMITE_CHAMADAS_DIA` no `.env`) evita gastos inesperados.
- Para encerrar tudo depois do TCC: apague a instância, o disco, o IP
  estático e as programações de snapshot.
