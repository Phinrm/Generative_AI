# ------------------------------


impl DocHandling.parse_and_ccg {
	has edges: list = _simple_ccg(root_path);
	# coerce to list[CCGEdge]
	has out: list = [];
	for e in edges {
		out = out + [CCGEdge(kind=e["kind"], src=e["src"], dst=e["dst"])];
	}
	return out;
}


impl DocHandling.plan_order {
	# LLM plans based on inputs; here we simply return top-level entries + main/app first as a hint
	# The real planning is produced by the LLM via sem above.
	has out: list = [];
	for e in file_tree {
		out = out + [e.path];
	}
	return out;
}


impl DocHandling.generate_markdown {
	# Let LLM synthesize; we also append Mermaid graph derived from ccg
	has tree_lines: list = [];
	for e in file_tree {
		if e.type == "dir" {
			tree_lines = tree_lines + ["- " + e.path + "/"];
		} else {
			tree_lines = tree_lines + ["- " + e.path];
		}
	}

	has ccg_dicts: list = [];
	for e in ccg {
		ccg_dicts = ccg_dicts + [{"kind": e.kind, "src": e.src, "dst": e.dst}];
	}
	has mermaid: str = _build_mermaid_from_ccg(ccg_dicts);

	has base: str = "# " + repo_name + "\n\n" +
		"## Project Overview\n" + summary + "\n\n" +
		"## Repository Structure\n" + "\n".join(tree_lines) + "\n\n" +
		"## Architecture Diagram\n" + mermaid + "\n\n" +
		"## API Reference (outline)\n" + "*Auto-generated from static scan; verify as needed.*\n";
	return base;
}


impl DocHandling.save_output {
	_mkdir_p(self.outputs_dir);
	has out_dir: str = os.path.join(self.outputs_dir, repo_name);
	_mkdir_p(out_dir);
	has out_path: str = os.path.join(out_dir, "docs.md");
	# Use a Python spawn to write the file (safe write in host Python)
	has py: any = spawn("""
import io, os
path = r'{}'
data = r'{}'
with open(path, 'w', encoding='utf-8') as f:
	f.write(data)
""".format(out_path.replace('\\','/'), markdown.replace('"', '\\"')));
	return DocArtifact(repo_name=repo_name, output_dir=out_dir, docs_path=out_path.replace('\\','/'), summary="Generated successfully");
}


# ------------------------------
# Router walker impls
# ------------------------------
impl codebase_genius.route_to_node {
# Simple router: if message contains a GitHub URL -> DocHandling, else GeneralChat
if "github.com" in utterance.lower() {
return RoutingNodes.DOC_HANDLING;
}
return RoutingNodes.GENERAL_CHAT;
}


impl get_last_artifact.get_last_artifact {
	# fetch latest docs for repo_name (by mtime)
	import glob;
	import os;
	has out_dir: str = "./outputs";
	if self.repo_name != "" {
		out_dir = os.path.join("./outputs", self.repo_name);
	}
	if not os.path.exists(out_dir) {
		report {"error": "No artifacts yet."};
		disengage;
	}
	has pattern: str = "";
	if self.repo_name != "" {
		pattern = os.path.join(out_dir, "docs.md");
	} else {
		pattern = os.path.join(out_dir, "*", "docs.md");
	}
	has files: list = glob.glob(pattern);
	if not files {
		report {"error": "No docs found."};
		disengage;
	}
	# pick latest by mtime
	has latest: str = "";
	has latest_mtime: float = 0.0;
	for p in files {
		has m: float = os.path.getmtime(p);
		if latest == "" || m > latest_mtime {
			latest = p;
			latest_mtime = m;
		}
	}
	# read file content via Python spawn to preserve encoding handling
	has py: any = spawn("""
import io, os
path = r'{}'
with open(path, 'r', encoding='utf-8') as f:
	data = f.read()
print(data)
""".format(latest.replace('\\','/')));
	has content: str = py.result;
	report {"path": latest.replace('\\','/'), "content": content};
}

# --- Minimal stubs for other tools (placeholder implementations).
impl DocHandling.validate_and_clone {
	# Placeholder: in a real impl this would clone the repo and return local path.
	# Here we simply echo back the repo_url so callers have a string to work with.
	return repo_url;
}

impl DocHandling.build_file_tree {
	# Placeholder: should scan root_path and return list[RepoMapEntry].
	# Return an empty list for now; later replace with a filesystem scan.
	return [];
}

impl DocHandling.summarize_readme {
	# Placeholder LLM summary: return empty string. The real impl should call llm.
	return "";
}