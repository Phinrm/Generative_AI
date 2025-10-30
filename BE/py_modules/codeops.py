# NOTE: This is called via Jac py_module. Keep imports local to speed up load.
import os, re, json, tempfile, shutil, subprocess, pathlib
from datetime import datetime

# Lightweight git clone (prefer git CLI for fewer compile deps)
def clone_repo(repo_url: str):
    try:
        # allow callers to pass either a raw URL or a full 'git clone <url>' string
        if isinstance(repo_url, str) and repo_url.strip().lower().startswith("git clone"):
            parts = repo_url.strip().split()
            # take the last token as the URL
            if len(parts) >= 2:
                repo_url = parts[-1]

        base = tempfile.mkdtemp(prefix="cbg_")
        repo_name = repo_url.rstrip("/").split("/")[-1].replace(".git", "")
        local = os.path.join(base, repo_name)

        # First try using the git CLI. If git isn't installed (FileNotFoundError),
        # fall back to GitPython (if available).
        try:
            cmd = ["git", "clone", "--depth=1", repo_url, local]
            subprocess.check_output(cmd, stderr=subprocess.STDOUT)
        except Exception as e:
            # If git CLI isn't available, subprocess will raise a FileNotFoundError
            # on Windows this appears as WinError 2. Fall back to GitPython when
            # we detect that situation; otherwise return the subprocess error.
            msg = str(e)
            if isinstance(e, FileNotFoundError) or "winerror 2" in msg.lower() or "no such file" in msg.lower():
                try:
                    from git import Repo
                    Repo.clone_from(repo_url, local)
                except Exception as e2:
                    # GitPython also failed (or not installed). Try GitHub zip download as a last resort
                    try:
                        # Detect GitHub URL and download archive
                        import zipfile, io, urllib.request

                        def _try_download_github_zip(url, dest):
                            # Accept URLs like https://github.com/owner/repo or ending with .git
                            parts = url.rstrip("/").split('/')
                            if len(parts) >= 2 and 'github.com' in parts[2]:
                                owner = parts[3]
                                repo = parts[4].replace('.git','')
                                zip_url = f"https://api.github.com/repos/{owner}/{repo}/zipball"
                                # download into memory (small to moderate repos) then extract
                                req = urllib.request.Request(zip_url, headers={"User-Agent": "CodebaseGenius/1.0"})
                                with urllib.request.urlopen(req, timeout=30) as resp:
                                    data = resp.read()
                                zf = zipfile.ZipFile(io.BytesIO(data))
                                # Ensure dest exists
                                os.makedirs(dest, exist_ok=True)
                                zf.extractall(dest)
                                # GitHub zipballs usually contain a single top-level folder named owner-repo-<hash>.
                                # Normalize by moving nested contents up one level when that's the case so callers
                                # receive a consistent repo root at `dest`.
                                try:
                                    entries = [e for e in os.listdir(dest) if not e.startswith('.')]
                                    if len(entries) == 1:
                                        nested = os.path.join(dest, entries[0])
                                        if os.path.isdir(nested):
                                            for item in os.listdir(nested):
                                                shutil.move(os.path.join(nested, item), dest)
                                            # remove the now-empty nested dir
                                            try:
                                                os.rmdir(nested)
                                            except Exception:
                                                pass
                                except Exception:
                                    # best-effort normalization; ignore failures
                                    pass
                                return True
                            return False

                        ok = _try_download_github_zip(repo_url, local)
                        if not ok:
                            return {"error": f"clone failed (git CLI missing and GitPython fallback failed): {e2}"}
                    except Exception as e3:
                        return {"error": f"clone failed (git CLI missing, GitPython failed, and HTTP fallback failed): {e3}"}
            else:
                # For called process errors we may get CalledProcessError which is
                # handled by the outer except; bubble other errors up to be handled there.
                raise

        return {"ok": True, "repo_url": repo_url, "repo_name": repo_name, "local_path": local}
    except subprocess.CalledProcessError as e:
        return {"error": f"clone failed: {e.output.decode(errors='ignore')}"}
    except Exception as e:
        return {"error": f"clone error: {e}"}

IGNORES = {".git", "node_modules", "__pycache__", ".venv", "dist", "build", ".mypy_cache"}

def build_tree(local_path: str):
    tree = {}
    for root, dirs, files in os.walk(local_path):
        # prune ignores
        dirs[:] = [d for d in dirs if d not in IGNORES]
        rel = os.path.relpath(root, local_path)
        if rel == ".": rel = ""
        tree.setdefault(rel, [])
        for f in files:
            if f.startswith("."): continue
            tree[rel].append(f)
    return {"root": local_path, "tree": tree}

def readme_text(local_path: str):
    # find README.* (md/rst/txt)
    for name in ["README.md","README.MD","readme.md","README.rst","README.txt"]:
        p = os.path.join(local_path, name)
        if os.path.exists(p):
            try:
                with open(p,"r",encoding="utf-8",errors="ignore") as fh:
                    return fh.read()
            except:
                pass
    return "No README found."

# ---------------- Code Parsing & CCG ----------------
# We try to use tree_sitter for Python and fallback to regex if not installed.
def _try_import_tree_sitter():
    try:
        from tree_sitter import Language, Parser
        return Language, Parser
    except Exception:
        return None, None

def _py_symbols_regex(src: str, path: str):
    # Basic fallback: discover classes, defs, and simplistic calls
    classes = re.findall(r'^\s*class\s+([A-Za-z_][A-Za-z0-9_]*)', src, re.M)
    funcs   = re.findall(r'^\s*def\s+([A-Za-z_][A-Za-z0-9_]*)', src, re.M)
    calls   = re.findall(r'([A-Za-z_][A-Za-z0-9_]*)\s*\(', src)
    return {
        "path": path,
        "classes": list(set(classes)),
        "functions": list(set(funcs)),
        "calls": list(set(calls))
    }

def _gather_files(local_path: str):
    exts = (".py", ".jac")
    files = []
    for root, dirs, fs in os.walk(local_path):
        dirs[:] = [d for d in dirs if d not in IGNORES]
        for f in fs:
            if f.endswith(exts):
                files.append(os.path.join(root, f))
    return files

def parse_python_and_jac(local_path: str):
    files = _gather_files(local_path)
    nodes = []
    edges = {"calls": [], "inherits": [], "contains": []}

    for p in files:
        try:
            with open(p,"r",encoding="utf-8",errors="ignore") as fh:
                src = fh.read()
        except:
            continue
        info = _py_symbols_regex(src, p)
        # module container node
        mod_id = f"module::{p}"
        nodes.append({"id": mod_id, "kind": "module", "name": pathlib.Path(p).name, "path": p})
        for cls in info["classes"]:
            cid = f"class::{p}::{cls}"
            nodes.append({"id": cid, "kind": "class", "name": cls, "path": p})
            edges["contains"].append([mod_id, cid])
        for fn in info["functions"]:
            fid = f"func::{p}::{fn}"
            nodes.append({"id": fid, "kind": "function", "name": fn, "path": p})
            edges["contains"].append([mod_id, fid])
        for callee in info["calls"]:
            # we don't know exact definition site; just record usage from each function in file
            for n in nodes:
                if n["path"]==p and n["kind"]=="function":
                    edges["calls"].append([n["id"], f"sym::{callee}"])

    # store last CCG for query API
    global _last_ccg
    _last_ccg = {"nodes": nodes, "edges": edges}
    return {"nodes": nodes, "edges": edges}

# Simple query API over the generated CCG artifact
_last_ccg = None
def query_calls(target: str):
    global _last_ccg
    if not _last_ccg: return []
    res = []
    tgt = f"sym::{target}"
    for s, d in _last_ccg.get("edges", {}).get("calls", []):
        if d == tgt: res.append(s)
    return res

# ---------------- Rendering ----------------
def _mermaid_from_ccg(ccg: dict):
    # Simplified Mermaid class diagram + call graph
    lines = ["```mermaid","graph LR"]
    shown = set()
    for s, d in ccg.get("edges",{}).get("contains", []):
        if s not in shown: lines.append(f'    "{s}"'); shown.add(s)
        if d not in shown: lines.append(f'    "{d}"'); shown.add(d)
        lines.append(f'    "{s}" --> "{d}"')
    for s, d in ccg.get("edges",{}).get("calls", []):
        lines.append(f'    "{s}" -.calls.-> "{d}"')
    lines.append("```")
    return "\n".join(lines)

def render_markdown(payload: dict):
    """
    payload = {
      repo_url, repo_name, local_path, file_tree, readme_summary, ccg
    }
    """
    ccg = payload.get("ccg", {})
    # store for query API
    global _last_ccg; _last_ccg = ccg

    tree = payload.get("file_tree", {}).get("tree", {})
    tree_md = []
    for folder, files in sorted(tree.items()):
        if folder == "": folder = "."
        tree_md.append(f"- **{folder}/**")
        for f in sorted(files):
            tree_md.append(f"  - {f}")
    mermaid = _mermaid_from_ccg(ccg)

    md = f"""# Codebase Genius Documentation: {payload.get('repo_name','')}

**Source:** {payload.get('repo_url','')}

## Overview
{payload.get('readme_summary','(No README summary)')}

## Repository Structure
{"\n".join(tree_md)}

## API & Relationships (CCG)
Below is a high-level graph of modules, their members, and function call edges:

{mermaid}

## How to Run
1. Create a virtualenv and install project deps (see repo README).
2. Identify entrypoints (main/app modules) from the tree above.
3. Use the CCG to navigate call paths.

*Generated by Codebase Genius on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*
"""
    return md

def write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path,"w",encoding="utf-8") as fh:
        fh.write(text)
    return True
