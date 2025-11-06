import from byllm.llm { Model }
import os;
include agent_core;      # must come before we extend `agent`
include main_impl;       # your implementations file (keep as you had)
import from utils { get_current_datetime }

# Configure byLLM to use Gemini 2.5 Plus (needs GEMINI_API_KEY in .env)
glob llm = Model(provider="gemini", model_name="gemini-2.5-flash", verbose=False);

# --------------------
# Data nodes
# --------------------
node RepoMapEntry {
    has path: str = "";
    has type: str = "file";    # file | dir
    has language: str = "";    # heuristic ext
}

node CCGEdge {
    has kind: str = "calls";   # calls | inherits | imports | composes
    has src: str = "";
    has dst: str = "";
}

node DocArtifact {
    has repo_name: str = "";
    has output_dir: str = "";
    has docs_path: str = "";   # outputs/<repo>/docs.md
    has summary: str = "";
}

# --------------------
# Toolbox: Documentation pipeline
# --------------------
node DocHandling(Toolbox) {
    has work_dir: str = "./workdir";
    has outputs_dir: str = "./outputs";
    has repo_url: str = "";
    has repo_name: str = "";

    # Declared here, implemented in main_impl.jac
    def validate_and_clone(repo_url: str) -> str;
    def build_file_tree(root_path: str) -> list[RepoMapEntry];
    def summarize_readme(root_path: str) -> str by llm();
    def parse_and_ccg(root_path: str) -> list[CCGEdge];
    def plan_order(file_tree: list[RepoMapEntry], summary: str) -> list[str] by llm();
    def generate_markdown(repo_name: str, summary: str, file_tree: list[RepoMapEntry], ccg: list[CCGEdge]) -> str by llm();
    def save_output(repo_name: str, markdown: str) -> DocArtifact;

    def route_and_run(utterance: str, history: str) -> str by llm(
        method="ReAct",
        tools=([self.validate_and_clone, self.build_file_tree, self.summarize_readme,
                self.parse_and_ccg, self.plan_order, self.generate_markdown, self.save_output])
    );
}

node GeneralChat(Toolbox) {
    def chat(utterance: str, history: str) -> str by llm();
    def route_and_run(utterance: str, history: str) -> str by llm(
        method="ReAct",
        tools=([self.chat])
    );
}

walker codebase_genius(agent) {
    def route_to_node(utterance: str, history: str) -> RoutingNodes by llm();
}

# Convenience
walker get_last_artifact {
    obj __specs__ { static has auth: bool = False; }
    has repo_name: str = "";
    can get_last_artifact with `root entry;
}
