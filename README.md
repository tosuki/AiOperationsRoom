# AI Operations Room (Gemini & Claude Code)

Uma sala local inspirada em pixel art para acompanhar sessões e subagentes do **Gemini (`agy`)** e **Claude Code**. O aplicativo pode observar as sessões locais de forma passiva (zero-config) ou via hooks, mantém os dados em SQLite local e serve a interface em `127.0.0.1`.

## Requisitos

- Python 3.12 ou superior
- [`uv` instalado](https://docs.astral.sh/uv/getting-started/installation/) ou `python3 -m venv` disponível no terminal
- Gemini (`agy`) ou Claude Code para acompanhar sessões reais

## Início rápido

```bash
# Instale as dependências
uv sync --extra dev  # ou: python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"

# Inicie o servidor
uv run python -m backend.cli serve  # ou: .venv/bin/python -m backend.cli serve
```

Execute os comandos na pasta deste repositório. Abra [http://127.0.0.1:8765](http://127.0.0.1:8765) e **deixe o terminal do servidor aberto** enquanto usa a sala; `Ctrl+C` encerra o servidor.

### Integração com Gemini (`agy`) — Zero Configuração
Se você já utiliza o client `agy` (mesmo autenticado com conta corporativa Google OAuth), o Operations Room se integra em **modo leitor (read-only)**:
- Lê o banco local de sessões em `~/.gemini/antigravity-cli/conversation_summaries.db`
- Detecta sessões ativas por presença de locks em `~/.gemini/antigravity-cli/presence/`
- **Não altera seu OAuth, não consome tokens de IA e não requer nenhuma configuração no terminal!**

### Iniciar com script local (macOS / Linux / Windows)

No macOS ou Linux:
```bash
./scripts/start-room.sh
```

No Windows:
```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-room.ps1
```

O script usa a porta 8765, espera a API responder e abre o navegador automaticamente.

## Demonstração

O modo demo cria uma fila e um banco separados em `~/.ai-operations-room-demo`, sem acessar dados reais ou precisar de ferramentas externas:

```bash
uv run python -m backend.cli demo --serve
```

Abra `http://127.0.0.1:8765` e interrompa o processo quando terminar. Para apenas gerar os dados fictícios, omita `--serve`.

## Hooks Opcionais

Caso queira usar hooks baseados em eventos no terminal:

```bash
# Para Gemini / agy (registra em ~/.gemini/config/hooks.json):
uv run python -m backend.cli hooks-install --provider gemini
uv run python -m backend.cli hooks-remove --provider gemini

# Para Claude Code (registra em ~/.claude/settings.json):
uv run python -m backend.cli hooks-install --provider claude
uv run python -m backend.cli hooks-remove --provider claude
```

O hook registra identificadores, tipo de agente, diretório de trabalho, razão de encerramento e a hora do evento. Ele **nunca** salva prompts, respostas nem código por privacidade.

O Painel usa um período selecionável de 6, 12 ou 24 horas. O Escritório mostra execuções ativas e as encerradas nas últimas 12 horas.

## Testes

```bash
pytest -v
node --check frontend/app.js
node --test tests/js/pixel.test.js
```

Consulte [ARCHITECTURE.md](ARCHITECTURE.md), [DEVELOPMENT.md](DEVELOPMENT.md) e [HANDOFF.md](HANDOFF.md) para detalhes de arquitetura.

## Inspiração visual

A sala pixel foi inspirada pelo [Pixel Agents](https://github.com/pixel-agents-hq/pixel-agents). Os personagens e móveis foram criados em código procedural vetorial (SVG); nenhum asset externo é utilizado.

## Licença

Distribuído sob a [licença MIT](LICENSE).
