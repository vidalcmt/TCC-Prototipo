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

## Dia a dia

| Para | Comando, na janela SSH |
|---|---|
| Atualizar com a versão mais recente da `main` | `sudo bash /opt/devolutiva/deploy/atualizar.sh` |
| Ver se a aplicação está no ar | `sudo systemctl status devolutiva` |
| Ver os erros mais recentes | `sudo journalctl -u devolutiva -n 50` |
| Fazer uma cópia do banco agora | `sudo systemctl start devolutiva-copia` |
| Listar as cópias | `ls -lh /var/backups/devolutiva` |
| Gerar senha provisória para quem esqueceu | `cd /opt/devolutiva && sudo -u devolutiva .venv/bin/python -m scripts.redefinir_senha --email voce@exemplo.com` |
| Baixar o banco para o computador | `sudo cp /opt/devolutiva/tcc.db ~ && sudo chown $USER ~/tcc.db`, depois a engrenagem da janela SSH, **Fazer download de arquivo**, `tcc.db` |

O `atualizar.sh` faz uma cópia do banco antes de qualquer mudança.

## Custos

- A máquina e o IP fixo são cobrados enquanto existirem, mesmo desligados
  (a máquina desligada cobra só o disco e o IP). Os créditos cobrem esses custos.
- As chamadas ao modelo são cobradas pela OpenAI, à parte. O limite diário por
  pessoa (`LIMITE_CHAMADAS_DIA` no `.env`) evita gastos inesperados.
- Para encerrar tudo depois do TCC: apague a instância, o disco, o IP
  estático e as programações de snapshot.
