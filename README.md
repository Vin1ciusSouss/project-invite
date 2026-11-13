# Site de casamento — Vinícius & Emanuelle

Site em Python/Flask para informações do casamento, confirmação de presença
por convite privado, presentes e administração pelos noivos.

**Site:** https://viniciussouss.pythonanywhere.com

O repositório local chama-se `project-invite`. O ZIP e a pasta da hospedagem
continuam usando `project-casamento` para preservar a instalação existente.

## Funcionalidades atuais

- RSVP sem e-mail: cada grupo recebe um link privado e marca quem irá comparecer. O total de pessoas é calculado automaticamente.
- Prazo informativo para confirmação: **13/02/2027**. O aviso não bloqueia respostas posteriores.
- Painel `/admin/` protegido por senha, com limite de cinco tentativas por quinze minutos por origem.
- Cadastro de convites, renovação de links e status por convidado.
- Ações **Corrigir resposta** e **Remover**. Remover uma resposta preserva o convite e libera nova confirmação.
- Presentes físicos com link para marketplace, reserva por nome e cancelamento pelo admin.
- Upload de imagens PNG, JPG/JPEG e WebP, limitado a 5 MB e 20 megapixels.
- Cotas de lua de mel de **R$ 150 e R$ 200**: Pix pelo Nubank e cartão pelo Mercado Pago. Várias pessoas podem presentear nos mesmos valores.
- Notificações em verde oliva escuro, com posição da página preservada após os formulários.
- Migrações versionadas e backup do SQLite antes de atualizações de esquema.

Uma reserva de presente não comprova compra. Os pagamentos são concluídos nos
serviços externos, sem webhook ou confirmação automática no site. A opção
de outro valor no cartão foi retirada. A rota autenticada de Excel permanece
no código, mas o botão foi removido do painel.

## O que enviar ao GitHub

| Pode ser versionado | Deve ficar fora do Git |
| --- | --- |
| `app/`: Python, templates, CSS e JavaScript | `.env`, `.env.production`, senhas, hashes reais, tokens e chaves de API |
| `migrations/`: todas as revisões do esquema | `instance/`, `casamento-dados/`, arquivos SQLite e WAL/journal |
| `tests/`: exemplos e dados fictícios | Listas reais de convidados, links privados de convite e exportações com dados pessoais |
| `deploy/`, `requirements.txt`, `run.py`, iniciador | Backups, logs, ZIPs e demais arquivos gerados em `dist/` |
| `README.md`, `AGENTS.md`, `.gitignore`, `.env.example` vazia | `.venv/`, caches e configurações pessoais do editor |
| Logo, foto pública da lua de mel e imagens iniciais revisadas | Novos uploads do admin e fotos/documentos privados sem revisão |

As fotos do casal, os endereços do evento e os links de cobrança presentes no
código são conteúdo público do site. Recomenda-se manter o repositório privado
para limitar a exposição do projeto. Um repositório privado também deve manter
credenciais e dados de convidados fora do histórico.

O `.gitignore` mantém fora do Git os arquivos privados e gerados. Na pasta
`app/static/img/presentes/`, permite apenas as três imagens iniciais usadas
pelo site. Para acrescentar outra imagem inicial, revise o conteúdo e adicione
uma exceção explícita ao ignore.

Antes de criar um commit, confira:

```bash
git status --short
git diff --cached --name-only
git diff --cached
```

Não use `git add -f` para incluir banco, `.env` ou pastas de dados. O ignore
não protege arquivos que já foram rastreados. Se um segredo tiver sido enviado,
removê-lo do último arquivo não o apaga do histórico: será necessário revogar
ou trocar a credencial e avaliar a limpeza do histórico.

## Executar localmente

Requisitos: Python 3.10 ou superior e pip. A hospedagem atual usa Python 3.13.

No PowerShell, na raiz do repositório:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Faça a cópia do `.env` apenas na primeira configuração. Edite-o localmente
e preencha `SECRET_KEY` e `ADMIN_PASSWORD_HASH`. Gere uma chave aleatória com:

```powershell
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))"
```

Gere o hash da senha administrativa sem exibir a senha digitada:

```powershell
.\.venv\Scripts\python.exe -c "from getpass import getpass; from werkzeug.security import generate_password_hash; print(generate_password_hash(getpass('Senha administrativa: ')))"
```

Guarde os resultados somente no `.env`. Não envie capturas, conteúdo do arquivo
ou saídas contendo esses valores para o GitHub.

Para iniciar no Windows:

```powershell
.\run.cmd
```

O script prepara o banco e inicia o site em http://127.0.0.1:5000.
Se a execução de `.ps1` estiver bloqueada, o iniciador `.cmd` continua sendo
o comando indicado.

Para iniciar manualmente, usando o mesmo Python das dependências:

```powershell
.\.venv\Scripts\python.exe -m flask --app run.py preparar-banco
.\.venv\Scripts\python.exe -m flask --app run.py run --debug
```

Em Linux/macOS, ative o ambiente com `source .venv/bin/activate` e use
`python` nos mesmos comandos. O debug é exclusivo do desenvolvimento local.

## Configuração por ambiente

| Variável | Uso |
| --- | --- |
| `APP_ENV` | `development` localmente; `production` na hospedagem |
| `SECRET_KEY` | Chave aleatória; em produção, pelo menos 32 caracteres |
| `ADMIN_PASSWORD_HASH` | Hash Werkzeug da senha compartilhada do painel |
| `DATABASE_URL` | Vazia usa `instance/casamento.db`; na hospedagem aponta para o SQLite persistente |
| `GIFT_UPLOAD_FOLDER` | Diretório persistente para fotos enviadas; localmente usa `app/static/img/presentes` se vazio |
| `PYTHONANYWHERE_HOST` | Domínio autorizado na entrada WSGI do PythonAnywhere |

Produção exige chave e hash configurados, usa cookies seguros e debug desligado.
O `.env` local não deve substituir o da hospedagem. O configurador de produção
gera segredos diretamente no servidor e se recusa a sobrescrever um `.env`
existente.

## Banco e migrações

O servidor não cria tabelas nem altera o esquema ao carregar. Execute antes
de iniciar uma instalação nova ou uma atualização com migrações:

```bash
python -m flask --app run.py preparar-banco
```

Se o SQLite existente tiver versões pendentes, o comando faz um backup
consistente em `instance/backups/`. Se esse backup falhar, a atualização
não começa. Os dados iniciais só são incluídos na primeira preparação de
um banco vazio; uma lista apagada pelo admin não é recriada.

```bash
python -m flask --app run.py db current
python -m flask --app run.py db check
```

Após alterar modelos, gere uma revisão, leia as operações propostas e teste
a preservação dos dados antes de aplicar:

```bash
python -m flask --app run.py db migrate -m "Descricao da mudanca"
python -m flask --app run.py preparar-banco
```

Não edite revisões já aplicadas, não use `db.create_all` para atualizar
produção e não use `db stamp` para pular operações. As revisões 0001 e 0003
preservam instalações legadas e exigem restauração de backup para reversão.
O backup de migração não inclui fotos e não substitui backups periódicos
baixados para fora da hospedagem.

## Testes

```bash
python -m unittest discover -s tests -v
```

A suíte usa dados fictícios, bancos em memória e arquivos temporários. Não
deve alterar o banco real, chamar pagamentos reais ou depender da conta de
produção. Mudanças em CSS e JavaScript também precisam de conferência visual
no navegador; testes Flask não validam a aparência.

## Organização do código

```text
app/
  __init__.py           configuração, fábrica, erros e segurança
  models.py            modelos de dados
  routes.py            páginas públicas, RSVP e reservas
  admin.py             administração
  forms.py             validação de formulários
  login_limits.py      tentativas de autenticação compartilhadas no banco
  commands.py          preparação do banco e backup antes de migração
  payment_options.py   links públicos das cotas fixas
  static/              estilos, scripts e imagens públicas
  templates/           páginas e layout compartilhado
migrations/            histórico de alterações do esquema
tests/                 testes isolados
deploy/                empacotamento e configuração do PythonAnywhere
```

## Hospedagem e atualização

O site foi configurado no PythonAnywhere gratuito, sem domínio próprio.
Guia completo: [deploy/PYTHONANYWHERE.md](deploy/PYTHONANYWHERE.md).

| Item | Caminho na hospedagem |
| --- | --- |
| Código | `/home/viniciussouss/project/project-casamento` |
| Ambiente virtual | `/home/viniciussouss/.virtualenvs/casamento` |
| Dados e uploads | `/home/viniciussouss/project/casamento-dados/` |
| Entrada WSGI | `deploy/pythonanywhere_wsgi.py` |

**Enviar um commit ao GitHub não atualiza o PythonAnywhere automaticamente.**
O fluxo atual é empacotar e enviar o código:

```bash
python deploy/empacotar.py
```

O resultado é `dist/pythonanywhere-casamento.zip`. Esse ZIP não leva o `.env`,
o banco, as confirmações ou os backups locais. Envie-o pela aba Files para
`/home/viniciussouss/` e, no Bash da hospedagem, execute:

```bash
unzip -o /home/viniciussouss/pythonanywhere-casamento.zip -d /home/viniciussouss/project
```

Depois use **Web → Reload**. Se a alteração incluir dependências ou migrações,
antes do Reload execute:

```bash
workon casamento
cd /home/viniciussouss/project/project-casamento
python -m pip install --no-cache-dir -r requirements.txt
python -m flask --app run.py preparar-banco
```

Preserve `.env`, banco e fotos recebidas na hospedagem. A primeira publicação
usou banco novo; isso não autoriza apagar os dados em atualizações. O plano
gratuito exige atenção à validade mensal da aplicação na aba Web, e não há
tarefas agendadas de backup para contas gratuitas novas. Confira a validade
no painel e mantenha uma rotina de cópias dos dados e das imagens.

## Limites atuais

- Não há confirmação automática de pagamentos nem registro de cota paga.
- Links externos podem alterar condições; o site não verifica estoque, preço ou aprovação de pagamentos.
- O histórico de e-mails antigos é preservado, mas e-mail não é coletado no RSVP atual.
- SQLite atende à instalação atual. PostgreSQL exige configuração do driver e validação das migrações e dados antes de uma troca.
- A configuração de IP confiável é específica do PythonAnywhere; não reutilizá-la em outra hospedagem sem revisão.

## QR Code dos convites

No admin, em **Convites e convidados**, cada convite tem um QR Code privado,
com **Baixar QR Code** (PNG) e **Imprimir**. O link continua em **Link alternativo**.
O QR leva diretamente ao formulario do grupo, sem enviar o codigo para servicos externos.

`PUBLIC_SITE_URL` define o dominio HTTPS publico usado no codigo impresso;
o padrao e `https://viniciussouss.pythonanywhere.com`. `PYTHONANYWHERE_HOST`,
quando configurado e sem `PUBLIC_SITE_URL`, tambem define esse dominio.
Nunca use localhost. Ao trocar de dominio, os QR Codes antigos ainda apontarao
para o endereco anterior. Renovar o link invalida o QR anterior: reimprima-o.

Use a imagem original com sua margem branca; a pagina de impressao usa um QR
de 45 mm. Teste com um celular antes de enviar a arte a grafica. O QR e privado:
qualquer pessoa com acesso a ele pode abrir o convite daquele grupo.

Esta atualizacao adiciona `qrcode[pil]` a `requirements.txt`. Na hospedagem,
execute `workon casamento` e `python -m pip install -r requirements.txt` na
pasta do projeto e depois use **Web > Reload**. Nao ha migracao de banco nova.
