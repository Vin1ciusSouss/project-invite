# PythonAnywhere — publicação e atualização

Site: **https://viniciussouss.pythonanywhere.com**.
Conta: `viniciussouss`, plano Beginner gratuito, sem domínio próprio.

O repositório no computador chama-se `project-invite`. O pacote contém a
pasta `project-casamento/`, nome que deve continuar sendo usado na hospedagem.

## Atualizar o site existente

Na raiz do repositório local:

```powershell
python deploy/empacotar.py
```

O arquivo atualizado fica em `dist/pythonanywhere-casamento.zip`. Ele não
contém `.env`, banco ou backups locais. Não reutilize um ZIP antigo salvo
na pasta de downloads.

Na aba **Files** do PythonAnywhere, envie o ZIP para `/home/viniciussouss/`
e confirme a substituição do ZIP anterior. Depois, no console **Bash**:

```bash
unzip -o /home/viniciussouss/pythonanywhere-casamento.zip -d /home/viniciussouss/project
```

O comando substitui os arquivos de código dentro de
`/home/viniciussouss/project/project-casamento`. Não é necessário remover
pastas antes de extrair. O ZIP não substitui `.env`, banco ou backups.

Se houver dependências ou migrações novas:

```bash
workon casamento
cd /home/viniciussouss/project/project-casamento
python -m pip install --no-cache-dir -r requirements.txt
python -m flask --app run.py preparar-banco
```

Use **Web → Reload** ao terminar. Alterações enviadas ao GitHub não são
aplicadas automaticamente na hospedagem.

## Caminhos que devem permanecer configurados

| Configuração | Valor |
| --- | --- |
| Python da aplicação | 3.13 |
| Source code | `/home/viniciussouss/project/project-casamento` |
| Working directory | `/home/viniciussouss/project/project-casamento` |
| Virtualenv | `/home/viniciussouss/.virtualenvs/casamento` |
| Dados persistentes | `/home/viniciussouss/project/casamento-dados/` |
| Banco | `casamento-dados/casamento.db` |
| Imagens enviadas | `casamento-dados/presentes/` |

O arquivo WSGI da aba **Web** deve conter:

```python
import sys
sys.path.insert(0, '/home/viniciussouss/project/project-casamento')
from deploy.pythonanywhere_wsgi import application
```

Em **Static files**, manter somente este mapeamento:

| URL | Directory |
| --- | --- |
| `/static/` | `/home/viniciussouss/project/project-casamento/app/static/` |

Não mapear a raiz do projeto, `.env`, `instance/` ou `casamento-dados/`.
As fotos enviadas pelo admin são servidas pela própria aplicação.
Manter **Force HTTPS** ativado. O site é iniciado pelo WSGI da plataforma;
não executar `flask run`, `python run.py` ou `run.cmd` para publicar.

## Instalação inicial em uma conta nova

Estes passos são somente para uma instalação nova. O site atual já tem
configuração e pode estar recebendo dados; atualizá-lo conforme a seção anterior.

1. Criar uma aplicação em Web → Add a new web app → Manual configuration → Python 3.13.
2. Enviar o ZIP para a pasta inicial e extrair com o comando de atualização.
3. No Bash, entrar na pasta do projeto e criar o ambiente com `mkvirtualenv --python=/usr/bin/python3.13 casamento`.
4. Instalar as dependências com `python -m pip install --no-cache-dir -r requirements.txt`.
5. Configurar segredos diretamente no servidor:

```bash
python deploy/configurar_pythonanywhere.py --host viniciussouss.pythonanywhere.com
```

O configurador pede uma senha administrativa de pelo menos 12 caracteres
sem exibi-la e gera a chave secreta. Ele para se o `.env` já existir.
Não copiar o `.env` do computador nem enviar sua senha pelo chat.

A primeira publicação deste projeto foi autorizada com banco novo.
Depois da configuração inicial, executar `python -m flask --app run.py preparar-banco`
e preencher os caminhos da aba Web. Não importar os dados locais por padrão.

## Conferir e manter

- Conferir home, foto da lua de mel, valores e links Pix/cartão, `/admin/`, RSVP, reservas e upload de imagem.
- Conferir os valores e o destinatário na tela do provedor antes de divulgar links de cobrança. O site não confirma pagamentos automaticamente.
- Se a atualização não aparecer, verificar o nome e o conteúdo do ZIP e os caminhos da aba Web; não criar outra pasta por tentativa.
- Em erros, consultar o **Error log**, sem divulgar segredos ou dados de convidados.
- Conferir a validade mensal na aba Web e usar **Run until 1 month from today** antes de expirar.
- Fazer cópias do banco e das fotos para fora da hospedagem. O backup de migração cobre apenas SQLite e só é criado antes de alterações pendentes.
- Contas gratuitas novas não têm tarefas agendadas para backups; a rotina periódica precisa ser manual ou externa.

## Referências oficiais

- [Flask e WSGI](https://help.pythonanywhere.com/pages/Flask/)
- [Variáveis de ambiente](https://help.pythonanywhere.com/pages/EnvironmentVariables/)
- [IP informado pelo balanceador](https://help.pythonanywhere.com/pages/WebAppClientIPAddresses)
- [Forçar HTTPS](https://help.pythonanywhere.com/pages/ForcingHTTPS)
- [Limites do plano gratuito](https://help.pythonanywhere.com/pages/FreeAccountsFeatures/)
