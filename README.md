# Lume Saúde — pré-consulta demonstrativa

Protótipo Django da tela **Pré-consulta pronta**, destinado exclusivamente a
apresentações com dados fictícios. Não use este projeto com dados reais de pacientes.

## Instalação local

Requisitos: Python 3.14 e SQLite (incluído no Python).

```powershell
git clone https://github.com/projetopreconsulta-stack/preconsulta.git
Set-Location preconsulta
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edite `.env` e substitua `DJANGO_SECRET_KEY` por uma chave local aleatória. O
projeto falha com uma mensagem clara se chave, modo debug ou hosts permitidos não
estiverem configurados. `DEBUG=True` é apenas para desenvolvimento local.

Cada desenvolvedor deve manter seu próprio `.env` e banco `db.sqlite3`. Esses
arquivos, ambientes virtuais, caches, logs e mídias locais estão ignorados pelo Git
e não devem ser compartilhados ou enviados ao repositório.

## Preparar e iniciar

```powershell
python manage.py migrate
python manage.py load_demo
python manage.py runserver 127.0.0.1:8000
```

Acesse:

- Painel médico: <http://127.0.0.1:8000/medico/painel/>
- Pré-consulta pronta: <http://127.0.0.1:8000/medico/pre-consultas/demo/>
- Operação da recepção: <http://127.0.0.1:8000/recepcao/pre-consultas/>

`load_demo` pode ser executado novamente para restaurar os dados-base fictícios:
ele atualiza o caso conhecido, não duplica registros e não apaga notas, correções,
feedback nem dados não relacionados. Não é necessário apagar o banco.

Os horários da agenda demonstrativa usam deslocamentos em relação à data local
configurada no Django. Assim, para a médica demonstrativa, cinco casos permanecem
em “Hoje” e um em “Amanhã” mesmo com a passagem dos dias. A recepção inclui ainda
um atendimento de um segundo médico para demonstrar o filtro e os vínculos entre
profissionais e clínicas. A execução idempotente de `load_demo` mantém também as
datas persistidas alinhadas ao dia local, sem duplicar consultas ou eventos.

A recepção reutiliza esses mesmos agendamentos e mostra apenas dados e eventos
operacionais. Novos cadastros começam como `Não iniciada`, exigem no servidor um
vínculo médico–clínica cadastrado e não criam fontes, respostas ou resumos clínicos.

## Regras ainda provisórias

- A antecedência de 24, 48 ou 72 horas é apenas demonstrativa.
- Não há regra definitiva de elegibilidade ou liberação de casos incompletos.
- Nenhum convite é agendado ou enviado; eventos de convite existentes são marcados
  como `SIMULADO` e não representam mensagem de WhatsApp.
- A separação visual entre recepção e médico não substitui autenticação e autorização
  em uma futura versão de produção.

Para reiniciar somente as interações do protótipo (notas, correções e feedback),
mantendo o caso, suas fontes e quaisquer dados não relacionados:

```powershell
python manage.py load_demo --reset-interactions
```

## PDFs e MP3 locais

Coloque os arquivos em `demo_media/`, usando os nomes documentados em
[`demo_media/README.md`](demo_media/README.md). O mapeamento central fica em
[`preconsultas/demo_media.py`](preconsultas/demo_media.py). Os binários são ignorados
pelo Git e servidos somente pelo Django local; nenhum upload externo é feito.

Enquanto os arquivos não existirem, o protótipo mantém as referências, mostra um
estado amigável no visualizador e identifica áudio/transcrição como conteúdo
fictício — sem alegar processamento dos arquivos ausentes.

## Verificação

```powershell
python manage.py check
python manage.py test
```

Os testes usam um banco temporário separado e não alteram o `db.sqlite3` local.

## Colaboração

O desenvolvimento acontece em branches curtas por tarefa, sempre integradas por
Pull Request para `main`, com CI aprovado e revisão do outro desenvolvedor. Consulte
[`CONTRIBUTING.md`](CONTRIBUTING.md) para os padrões de branches, revisão e cuidados
com dados e arquivos locais.
