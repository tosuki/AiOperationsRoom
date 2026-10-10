# AI Operations Room (Gemini & Claude Code)

Uma sala de operações local com estética de pixel art (estilo *Pixel Agents* e *Habbo Hotel*) para visualizar em tempo real o que seus agentes e subagentes de IA estão fazendo.

---

## 📌 Origem do Projeto & Este Fork

Este projeto é um fork do repositório original [**mewsdev/AiOperationsRoom**](https://github.com/mewsdev/AiOperationsRoom), desenvolvido originalmente com foco em monitorar sessões do **Claude Code** em ambiente Windows via hooks em `~/.claude/settings.json`.

### Principais modificações introduzidas neste fork:

1. **Suporte Nativo ao Gemini (`agy` / Antigravity CLI):**
   - **Observador Passivo (Zero Configuração):** Ingestão automática lendo o banco SQLite local do Gemini (`~/.gemini/antigravity-cli/conversation_summaries.db`). Você não precisa instalar nem rodar scripts no terminal durante o uso da IA.
   - **Zero impacto em contas comerciais / Google OAuth:** O aplicativo funciona 100% offline em `127.0.0.1`, sem tocar em credenciais (`oauth_creds.json`), sem fazer chamadas a APIs externas e sem interferir na sua autenticação corporativa.
   - **Detecção de Sessão Ativa por Presence Locks:** Monitoramento de locks (`~/.gemini/antigravity-cli/presence/*.lock`) via `fcntl.flock`, identificando com precisão quando o processo está rodando, ocioso ou encerrou.
   - **Suporte a Subagentes e Delegação:** O agente principal e subagentes são mapeados hierarquicamente para os estados `trabalhando`, `delegando`, `aguardando` e `concluida`.
   - **Hooks Opcionais do Gemini:** Suporte ao formato `hooks.json` do Gemini (`PreInvocation`, `PreToolUse`, `PostToolUse`, `Stop`) via flag `--provider gemini`.

2. **Compatibilidade Multiplataforma (macOS & Linux):**
   - Corrigida a detecção de processos órfãos para POSIX no macOS e Linux (`os.kill(pid, 0)`), substituindo chamadas que antes dependiam exclusivamente da Win32 API ou `/proc`.
   - Adicionado script de inicialização para macOS/Linux: [`scripts/start-room.sh`](scripts/start-room.sh).
   - Ajustada a configuração de empacotamento em `pyproject.toml` para descoberta de pacotes no setuptools/pip em Python 3.12+.

3. **Adaptação Visual:**
   - Cores do avatar principal ajustadas em [`frontend/pixel.js`](frontend/pixel.js) para o fone azul/ciano característico do Gemini.
   - Interface web e documentação atualizadas para refletir o Gemini e múltiplos provedores.

4. **Suíte de Testes Estendida:**
   - Adicionados testes unitários em [`tests/test_gemini.py`](tests/test_gemini.py) cobrindo sincronização, locks, subagentes e payloads de hooks.

---

## Requisitos

- Python 3.12 ou superior
- [`uv` instalado](https://docs.astral.sh/uv/getting-started/installation/) ou `python3 -m venv` disponível no terminal
- Gemini (`agy`) ou Claude Code

---

## Início rápido

```bash
# 1. Instale as dependências
uv sync --extra dev  # ou: python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"

# 2. Inicie o servidor
uv run python -m backend.cli serve  # ou: .venv/bin/python -m backend.cli serve
```

Abra [http://127.0.0.1:8765](http://127.0.0.1:8765) no navegador.

### Iniciar com Script Automático

No **macOS ou Linux**:
```bash
./scripts/start-room.sh
```

No **Windows**:
```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-room.ps1
```

O script inicia o servidor em segundo plano na porta 8765, aguarda a API responder com sucesso e abre o navegador automaticamente.

---

## Como Funciona

```text
Gemini (agy)  ──[observador passivo / locks]──┐
                                              ├──> SQLite local ──> FastAPI (127.0.0.1) ──> Web UI
Claude Code   ──[command hooks locais]────────┘
```

1. **Associação por Projetos:** Na aba **Projetos**, cadastre a pasta local do seu repositório. Quando uma sessão roda nessa pasta (ou subpasta), ela é direcionada automaticamente para a sala correspondente.
2. **Estados dos Agentes:**
   - 🟢 **Trabalhando:** O agente senta na mesa, digita no computador e a tela acende.
   - 🔵 **Delegando:** O agente principal com fone de ouvido coordena um ou mais subagentes.
   - 🟠 **Aguardando:** O agente aguarda novo comando ou circula pelo escritório.
   - ⚪ **Concluída:** O agente se desloca para a área de descanso (café ou lounge) e permanece visível por até 12 horas.
   - 🔴 **Órfã:** A sessão foi encerrada de forma abrupta sem sinal de saída (exibe balão `!`).

---

## Modo Demonstração

Para visualizar a sala funcionando com dados simulados (sem precisar de sessões ativas de IA):

```bash
uv run python -m backend.cli demo --serve
```

---

## Hooks de Terminal (Opcional)

Caso queira usar hooks baseados em eventos no terminal:

```bash
# Para Gemini / agy (registra em ~/.gemini/config/hooks.json):
uv run python -m backend.cli hooks-install --provider gemini
uv run python -m backend.cli hooks-remove --provider gemini

# Para Claude Code (registra em ~/.claude/settings.json):
uv run python -m backend.cli hooks-install --provider claude
uv run python -m backend.cli hooks-remove --provider claude
```

---

## Testes

```bash
pytest -v
node --check frontend/app.js
node --test tests/js/pixel.test.js
```

---

## Inspiração Visual & Licença

- A sala em pixel art foi inspirada pelo [Pixel Agents](https://github.com/pixel-agents-hq/pixel-agents). Todos os personagens, móveis e caminhos foram desenhados em código procedural vetorial (SVG); nenhum asset externo é utilizado.
- Distribuído sob a [licença MIT](LICENSE).
