# Codebase Genius (Backend)

Jac-based multi-agent system that:
- clones a public GitHub repo
- builds a file tree
- parses Python/Jac to build a Code Context Graph (CCG)
- generates Markdown docs (with Mermaid diagram)
- exposes walkers to run end-to-end

## Quickstart
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
jac serve main.jac
