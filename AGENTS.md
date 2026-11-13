# Instruções para trabalhar neste repositório

## Contexto e decisões aprovadas

Site de casamento de Vinícius & Emanuelle, feito em Flask, Flask-SQLAlchemy e SQLite.
Evento: 13/03/2027 às 17h, em Mari/PB. O prazo exibido para RSVP é 13/02/2027;
o aviso é informativo e não deve bloquear respostas depois da data.

- Identidade visual: oliva, creme e dourado suave; Cormorant Garamond nos títulos e DM Sans nos textos e controles. Reutilizar variáveis e componentes de `app/static/css/style.css`.
- RSVP: um grupo de convidados por link privado aleatório, sem e-mail. Cada grupo envia uma resposta, marcando quem comparece. O total é calculado pelas pessoas marcadas.
- Admin: senha compartilhada com hash, cinco tentativas por quinze minutos por origem, contadas atomicamente no banco. Corrigir e remover respostas por registro. Remover um RSVP preserva o convite e o link, libera nova resposta e não altera presentes. Não recolocar o botão de Excel; a rota autenticada de exportação ainda existe.
- Presentes físicos: reserva identifica a intenção de presentear e o nome do convidado. A compra acontece na loja externa. O admin gerencia produtos, fotos e cancelamentos de reserva.
- Lua de mel: apenas cotas de R$ 150 e R$ 200 por Pix/Nubank e cartão/Mercado Pago. Os links ficam em `app/payment_options.py`. Várias pessoas podem presentear nos mesmos valores. Não exibir a opção de outro valor no cartão.
- Pagamentos: links externos não confirmam recebimentos. Não marcar cota como paga por clique, reserva ou retorno do navegador. Não há integração de API/webhook implementada. URLs de cobrança não são payloads Pix; não gerar QR Code ou Pix Copia e Cola a partir delas.
- Imagens: PNG, JPG/JPEG e WebP; até 5 MB e 20 megapixels; validar e regravar com Pillow. Não alterar arquivos originais sem necessidade.
- Avisos positivos: verde oliva escuro e texto claro, fixos no canto superior direito. Preservar rolagem usando `notifications.js` e `data-scroll-return`; manter erros com semântica própria e validação junto ao campo.

## Forma de colaborar

1. Examine a estrutura e o código antes de editar. Respeite alterações já existentes do usuário.
2. Execute o que estiver autorizado; pergunte quando uma decisão de produto estiver realmente indefinida. Não invente dados, valores, credenciais ou regras para convidados.
3. Faça mudanças proporcionais ao pedido e mantenha o idioma português.
4. Não publique, faça push, altere histórico, apague dados ou troque segredos sem autorização correspondente. Não peça senhas pelo chat.
5. Use dados fictícios nos testes. Nunca imprima `.env`, hashes reais, credenciais ou listas de convidados nas saídas das ferramentas.
6. Ao finalizar, informe mudanças, verificações executadas e limitações reais. Não declare publicação ou teste de navegador quando só houve verificação local.

## Arquitetura

- `app/__init__.py`: fábrica da aplicação, configuração e tratamento de erros.
- `app/models.py`: modelos; `extensions.py`: banco e Flask-Migrate.
- `app/routes.py`: páginas públicas e reservas; `app/admin.py`: ações administrativas.
- `app/forms.py`: validação no servidor; `app/login_limits.py`: controle de tentativas.
- `app/commands.py`: comando `preparar-banco`; `app/seed.py`: presentes iniciais.
- `app/templates/` e `app/static/`: interface e recursos públicos.
- `migrations/versions/`: esquema versionado com Alembic.
- `tests/`: testes isolados com dados fictícios, banco em memória ou temporário.
- `deploy/`: empacotamento, configuração e entrada WSGI do PythonAnywhere.

## Git e dados privados

O repositório local chama-se `project-invite`; os nomes `project-casamento/`
no ZIP e na hospedagem são intencionais. Não renomear caminhos de produção
apenas porque o nome do repositório mudou.

Versionar código, migrações, testes, documentação e imagens públicas revisadas.
Manter a `.env.example` com campos vazios. Nunca versionar `.env` e suas
variantes, banco SQLite, arquivos de journal/WAL, backups, exportações Excel
com dados reais, logs, chaves privadas, ambientes virtuais e ZIPs de publicação.

As fotos do casal, endereços do evento e links de pagamento existentes são
conteúdo público do site. Não confundi-los com credenciais. Novas fotos ou
documentos privados precisam de revisão antes de entrar no repositório.

Por padrão, `.gitignore` permite somente as três imagens iniciais em
`app/static/img/presentes/`. Uploads do admin permanecem fora do Git. Para
adicionar uma imagem inicial nova, revisar o arquivo e incluir uma exceção
explícita no ignore, em vez de usar `git add -f` para a pasta inteira.

`.gitignore` não remove arquivos já rastreados nem apaga histórico remoto.
Caso encontre segredo versionado, informe somente caminho e tipo, sem expor
o valor. A remoção do histórico e a rotação de credenciais exigem um plano
adequado à situação; não executar reescrita ou force push por conta própria.

## Banco e execução local

Python 3.10 ou superior, dependências em `requirements.txt`.

```text
python -m pip install -r requirements.txt
python -m flask --app run.py preparar-banco
python -m flask --app run.py run --debug
```

No Windows, `run.cmd` prepara o banco e inicia em `http://127.0.0.1:5000`.
O SQLite local padrão fica em `instance/casamento.db`.

- A fábrica da aplicação não deve criar tabelas, alterar esquema ou semear dados.
- Alterações de modelos precisam de migração nova e revisada. Não modificar revisões já aplicadas nem usar `db.create_all` ou `db stamp` para atualizar produção.
- `preparar-banco` faz backup consistente do SQLite quando há dados e migrações pendentes. Se o backup falhar, a atualização deve parar.
- Preservar os registros legados. As revisões 0001 e 0003 têm reversão por restauração de backup, não downgrade automático.
- Presentes iniciais só são criados na primeira preparação de banco vazio; não repopular uma lista apagada pelo admin.

## Segurança e verificações

- Produção: `APP_ENV=production`, `SECRET_KEY` aleatória com pelo menos 32 caracteres, `ADMIN_PASSWORD_HASH`, HTTPS e debug desligado.
- Preservar CSRF e `Referrer-Policy: same-origin`; `no-referrer` impede formulários HTTPS com verificação estrita.
- Validar entradas no servidor e manter reservas atômicas. Remoções usam POST, autenticação e CSRF.
- O proxy específico do PythonAnywhere confia em `X-Real-IP` somente na entrada WSGI do provedor. A execução local não confia em cabeçalhos de IP enviados pelo cliente.
- Rode testes pertinentes. Para mudanças em banco, autenticação ou comportamento compartilhado, rode a suíte completa:

```text
python -m unittest discover -s tests -v
```

- Documentação e ignore: validar os arquivos candidatos e regras do Git; não é necessário rodar toda a aplicação.
- Não fixar um número de testes na documentação, pois a suíte evolui.

## Hospedagem e atualizações

Hospedagem escolhida: PythonAnywhere Beginner gratuito, conta `viniciussouss`,
site `https://viniciussouss.pythonanywhere.com`, sem domínio próprio. A primeira
publicação começou com banco novo. Em atualizações, preservar os dados que
passaram a ser recebidos na hospedagem; nunca reinicializar o banco.

- Código remoto: `/home/viniciussouss/project/project-casamento`.
- Ambiente virtual: `/home/viniciussouss/.virtualenvs/casamento`; Python 3.13.
- Dados: `/home/viniciussouss/project/casamento-dados/`.
- WSGI: `deploy/pythonanywhere_wsgi.py`; guia em `deploy/PYTHONANYWHERE.md`.
- Gerar ZIP: `python deploy/empacotar.py`; não commitá-lo.
- GitHub guarda o código. Não há deploy automático configurado por push.
- Atualização atual: enviar o ZIP correto, extrair na pasta acima e usar Web → Reload. Dependências/migrações só quando exigidas pela alteração.
- Preservar `.env`, banco, fotos enviadas e backups. Mapear como estático somente `app/static`.

## QR Code de convites

Gerar localmente com qrcode/Pillow em rotas autenticadas; nao enviar tokens
para geradores externos. Usar PUBLIC_SITE_URL (HTTPS publico), nunca o Host
recebido nem localhost. PNG sem cache, preto em fundo branco com margem de
quatro modulos; preservar essa margem na impressao. Renovar invite_token
invalida tambem os QR Codes impressos. Nao persistir QR Codes no Git ou banco.
