# Arquitetura

```text
Gemini (agy)  ──[observer / hooks]──┐
                                     ├──> events.jsonl / SQLite ──> FastAPI em 127.0.0.1 ──> navegador
Claude Code   ──[hooks locais]──────┘
```

O sistema possui duas formas de ingestão complementares e desacopladas:
1. **Gemini Observer (Modo Passivo / Read-only):** Lê diretamente o banco local do Gemini (`~/.gemini/antigravity-cli/conversation_summaries.db`) e o diretório de presença de locks (`~/.gemini/antigravity-cli/presence/*.lock`), sem exigir configuração de hooks ou alteração no client.
2. **Fila de Eventos (Hooks):** Hooks executados pelo Gemini (`~/.gemini/config/hooks.json`) ou pelo Claude Code (`~/.claude/settings.json`) adicionam metadados atômicos na fila `events.jsonl`, consumida pelo FastAPI.

## Dados

- `projeto`: nome e um diretório local para associação por `cwd`.
- `sessao`: último metadado recebido por sessão, usado pela tela de mapeamento.
- `evento`: histórico deduplicado, sem texto de conversa ou código.
- `execucao`: projeção da sessão principal e dos subagentes.

### Estados e Ciclo de Vida
- **`trabalhando`:** agente executando tarefas ou aguardando resposta de modelo (senta na mesa e digita).
- **`delegando`:** agente principal coordenando subagentes ativos.
- **`aguardando`:** sessão pronta esperando novo comando do usuário.
- **`concluida`:** execução encerrada (permanece na convivência por até 12 horas).
- **`orfa`:** processo encerrado abruptamente ou lock perdido sem sinal de encerramento.

## Privacidade e rede

O backend só escuta em `127.0.0.1`. Nem o observer nem os hooks capturam prompts, respostas de modelo ou arquivos de código. Não há transmissão de dados para serviços de nuvem ou externos.
