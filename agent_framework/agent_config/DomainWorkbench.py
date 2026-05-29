import os
import re
import json
import glob
import logging
import subprocess
from typing import Dict, List, Any, Optional, Tuple

import requests
from chromadb import PersistentClient
from langchain_text_splitters import RecursiveCharacterTextSplitter

from agent_framework.agent_config.Mcp_config import FeedbackEnabledWorkbench
# NOTE: MemoryAwareAssistantAgent is used in AgentFactory, not required here.

# ---------- Logging ----------
logger = logging.getLogger("DomainWorkbench")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("[%(levelname)s] %(asctime)s - %(name)s - %(message)s"))
logger.addHandler(handler)

# ---------- Helpers ----------
DEFAULT_INCLUDE = [
    "**/*.py", "**/*.java", "**/*.js", "**/*.ts", "**/*.cs",
    "**/*.go", "**/*.rb", "**/*.php", "**/*.kt",
    "**/*.yml", "**/*.yaml", "Dockerfile", "**/*.tf", "**/*.md"
]
DEFAULT_EXCLUDE = ["**/node_modules/**", "**/.git/**", "**/build/**", "**/dist/**", "**/.venv/**", "**/__pycache__/**"]


class DomainWorkbench(FeedbackEnabledWorkbench):
    """
    Workbench for the Domain Agent:
      - Clone/prepare repos
      - Analyze code & workflows
      - Retrieve KB context (RAG via Chroma)
      - Generate FRD/TRD and write to configured paths (Markdown)
    """

    def __init__(self, config_path: str = "config.json", model_client: Any = None):
        self.config = self._load_config(config_path)
        self.model_client = model_client  # optional, if your agent passes it

        # Initialize Chroma persistent client for KB (supports both `kb.vector_db_path` or fallback to `chroma_path`)
        kb_cfg = self.config.get("kb", {})
        kb_path = kb_cfg.get("vector_db_path") or self.config.get("chroma_path")
        if kb_path:
            try:
                self.chroma_client = PersistentClient(path=kb_path)
                self.kb_collection_name = kb_cfg.get("collection_name", "domainkb")
                self.kb_collection = self.chroma_client.get_or_create_collection(name=self.kb_collection_name)
            except Exception as e:
                logger.error(f"Failed to open KB collection '{self.kb_collection_name}': {e}")
                self.chroma_client = None
                self.kb_collection = None
        else:
            self.chroma_client = None
            self.kb_collection = None
            logger.warning("KB vector_db_path (or chroma_path) not configured; proceeding without KB RAG context.")

        # Optional: persistent collection for generated docs
        self.docs_collection_name = (self.config.get("rag", {}) or {}).get("docs_collection", "domain_docs")
        if self.chroma_client:
            try:
                self.docs_collection = self.chroma_client.get_or_create_collection(name=self.docs_collection_name)
            except Exception as e:
                logger.error(f"Failed to open docs collection '{self.docs_collection_name}': {e}")
                self.docs_collection = None
        else:
            self.docs_collection = None

        # Output paths (Markdown as per your format)
        output_cfg = self.config.get("output", {}) or {}
        self.frd_path = output_cfg.get("frd_path", os.path.join("artifacts", "FRD.md"))
        self.trd_path = output_cfg.get("trd_path", os.path.join("artifacts", "TRD.md"))

        # Include/exclude globs
        repo_cfg = self.config.get("repo", {}) or {}
        self.include_globs = repo_cfg.get("include_globs", DEFAULT_INCLUDE)
        self.exclude_globs = repo_cfg.get("exclude_globs", DEFAULT_EXCLUDE)

        super().__init__(server_params=None)

    # ------------------- Public MCP tool API -------------------
    async def list_tools(self) -> List[str]:
        # return ["clone_repo", "analyze_code", "generate_docs"]
        return []

    async def call_tool(self, tool_name: str, params: Dict[str, Any]):
        if tool_name == "clone_repo":
            return self.clone_repos()
        elif tool_name == "analyze_code":
            return self.analyze_code()
        elif tool_name == "generate_docs":
            top_k_kb = params.get("top_k_kb", 8)
            return self.generate_docs(top_k_kb=top_k_kb)
        else:
            return {"error": f"Unknown tool '{tool_name}'"}

    # ------------------- Core functions -------------------
    def _load_config(self, path: str) -> Dict[str, Any]:
        if not os.path.exists(path):
            raise FileNotFoundError(f"Config not found at {path}")
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        return cfg

    def _expand_repo_globs(self, base_path: str) -> List[str]:
        files: List[str] = []
        for pattern in self.include_globs:
            files.extend(glob.glob(os.path.join(base_path, pattern), recursive=True))

        def excluded(p: str) -> bool:
            # Normalize path separators for matching
            p_norm = p.replace("\\", "/")
            for ex in self.exclude_globs:
                ex_norm = os.path.join(base_path, ex).replace("\\", "/")
                if glob.fnmatch.fnmatch(p_norm, ex_norm):
                    return True
            return False

        return [f for f in files if os.path.isfile(f) and not excluded(f)]

    def clone_repos(self) -> Dict[str, Any]:
        """
        Clone or prepare local paths from config['repos'].
        Supports:
          - github: {url, token?}
          - bitbucket: {url, username?, password?}
          - local: {path}
        """
        repos = self.config.get("repos", []) or []
        prepared_paths: List[str] = []
        os.makedirs("repos", exist_ok=True)

        for repo in repos:
            rtype = (repo.get("type") or "").lower()
            if rtype == "local":
                path = os.path.normpath(repo.get("path", ""))
                if not path or not os.path.exists(path):
                    logger.error(f"Local repo path not found: {path}")
                    continue
                prepared_paths.append(path)
                logger.info(f"Using local repo: {path}")
                continue

            # derive local clone path
            url = repo.get("url", "")
            repo_name = repo.get("name") or url.rstrip("/").split("/")[-1] or "repo"
            local_path = os.path.join("repos", repo_name.replace(".git", ""))

            if os.path.exists(local_path) and os.path.isdir(local_path):
                # pull latest
                logger.info(f"Repo exists: {local_path}. Fetching updates...")
                try:
                    subprocess.run(["git", "-C", local_path, "pull", "--ff-only"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                except subprocess.CalledProcessError as e:
                    logger.warning(f"git pull failed for {local_path}: {e}")
                prepared_paths.append(local_path)
                continue

            # authenticated URL crafting (URL-embedded credentials)
            auth_url = url
            if rtype == "github":
                token = repo.get("token") or os.environ.get("GITHUB_TOKEN")
                if token:
                    # e.g., https://TOKEN@github.com/org/repo.git
                    auth_url = re.sub(r"^https://", f"https://{token}@", url)
            elif rtype == "bitbucket":
                username = repo.get("username") or os.environ.get("BITBUCKET_USERNAME")
                password = repo.get("password") or os.environ.get("BITBUCKET_PASSWORD")
                if username and password:
                    # e.g., https://username:password@bitbucket.org/org/repo.git
                    auth_url = re.sub(r"^https://", f"https://{username}:{password}@", url)

            logger.info(f"Cloning {url} -> {local_path}")
            try:
                subprocess.run(["git", "clone", auth_url, local_path], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                prepared_paths.append(local_path)
            except subprocess.CalledProcessError as e:
                logger.error(f"Failed to clone {url}: {e}")

        return {"status": "Repos ready", "paths": prepared_paths}

    def analyze_code(self) -> Dict[str, Dict[str, Any]]:
        """
        Returns dict: {file_path: {"content": str, "lang": str}}
        Includes code + workflows + infra files.
        """
        repos = self.config.get("repos", []) or []
        analysis: Dict[str, Dict[str, Any]] = {}

        for repo in repos:
            # prefer explicit local path; else infer from clone folder
            base_path = repo.get("path") or os.path.join("repos", (repo.get("name") or repo.get("url", "repo")).rstrip("/").split("/")[-1].replace(".git", ""))
            if not base_path or not os.path.exists(base_path):
                logger.warning(f"Repo path missing: {base_path}")
                continue

            files = self._expand_repo_globs(base_path)
            for fp in files:
                ext = os.path.splitext(fp)[1].lower() or "misc"
                try:
                    with open(fp, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                    analysis[fp] = {"content": content, "lang": ext.lstrip(".")}
                except Exception as e:
                    logger.warning(f"Failed to read {fp}: {e}")

        logger.info(f"Analyzed {len(analysis)} files.")
        return analysis

    # ------------------- RAG helpers -------------------
    def _extract_intents(self, analysis: Dict[str, Dict[str, Any]], max_intents: int = 12) -> List[str]:
        """
        Very light heuristic to derive intents/keywords from filenames and content.
        """
        freq: Dict[str, int] = {}
        keyword_pattern = re.compile(
            r"\b(payments?|refunds?|orders?|auth|login|ledger|webhook|invoice|gateway|limits?|profile|account|"
            r"service|controller|handler|job|cron|topic|queue|event|deploy|build|test|ci|cd|terraform|kubernetes|docker)\b",
            re.IGNORECASE
        )

        for fp, meta in analysis.items():
            # filename tokens
            for tok in re.findall(r"[A-Za-z][A-Za-z0-9]+", os.path.basename(fp)):
                if len(tok) >= 4:
                    freq[tok.lower()] = freq.get(tok.lower(), 0) + 1
            # content keywords (truncate long files for perf)
            for kw in keyword_pattern.findall(meta["content"][:20000]):
                freq[kw.lower()] = freq.get(kw.lower(), 0) + 2

        # pick top N
        intents = sorted(freq.items(), key=lambda x: x[1], reverse=True)[:max_intents]
        intents = [k for k, _ in intents]
        if not intents:
            intents = ["system", "service", "controller", "workflow"]
        logger.info(f"Derived intents: {intents}")
        return intents

    def _query_kb(self, intents: List[str], top_k: int = 8) -> List[Dict[str, Any]]:
        """
        Query KB collection for each intent and return combined docs with scores.
        """
        if not self.kb_collection:
            return []

        results: List[Dict[str, Any]] = []
        for intent in intents:
            try:
                q = self.kb_collection.query(
                    query_texts=[intent], n_results=top_k, include=["documents", "metadatas", "distances"]
                )
                docs = q.get("documents", [[]])[0]
                metas = q.get("metadatas", [[]])[0]
                dists = q.get("distances", [[]])[0]
                for doc, meta, dist in zip(docs, metas, dists):
                    results.append({"text": doc, "metadata": meta or {}, "score": 1.0 - float(dist or 0.0)})
            except Exception as e:
                logger.warning(f"KB query failed for intent '{intent}': {e}")
        # sort by score desc and de-dup by text
        uniq: Dict[str, Dict[str, Any]] = {}
        for r in sorted(results, key=lambda x: x["score"], reverse=True):
            if r["text"] not in uniq:
                uniq[r["text"]] = r
        merged = list(uniq.values())[:max(8, len(intents))]
        return merged

    # ------------------- LLM integration -------------------
    def _llm_generate(self, system_prompt: str, user_prompt: str, max_tokens: int = 4000) -> str:
        """
        Try model_client first; else HTTP endpoint; else fallback.
        Supports either:
          - model_client.generate(system_prompt=..., user_prompt=..., max_tokens=...)
          - model_client.create(messages=[...])
        """
        # 1) model_client.generate(...)
        if self.model_client and hasattr(self.model_client, "generate"):
            try:
                return self.model_client.generate(system_prompt=system_prompt, user_prompt=user_prompt, max_tokens=max_tokens)
            except Exception as e:
                logger.warning(f"model_client.generate failed: {e}")

        # 1b) model_client.create(messages=[...])
        if self.model_client and hasattr(self.model_client, "create"):
            try:
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ]
                resp = self.model_client.create(messages=messages, max_tokens=max_tokens)
                # try to extract content
                if isinstance(resp, dict):
                    choices = resp.get("choices") or []
                    if choices and "message" in choices[0]:
                        return choices[0]["message"].get("content", "")
                # fallback: stringify
                return str(resp)
            except Exception as e:
                logger.warning(f"model_client.create failed: {e}")

        # 2) HTTP endpoint (OpenAI/Azure-compatible)
        llm_cfg = self.config.get("llm", {}) or {}
        endpoint = llm_cfg.get("endpoint")
        api_key = llm_cfg.get("api_key") or os.environ.get("LLM_API_KEY")
        model = llm_cfg.get("model", "gpt-4")
        provider = llm_cfg.get("provider", "openai")  # "openai" | "azure"

        if endpoint and api_key:
            try:
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "temperature": llm_cfg.get("temperature", 0.2),
                    "max_tokens": max_tokens
                }
                url = endpoint.rstrip("/")
                # If azure, some gateways use /openai/deployments/<model>/chat/completions
                # But we keep generic /v1/chat/completions for compatibility
                resp = requests.post(url + "/v1/chat/completions", headers=headers, json=payload, timeout=90)
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"]
            except Exception as e:
                logger.warning(f"LLM HTTP call failed: {e}")

        # 3) Fallback
        return "Fallback summary: (LLM not configured)."

    def _compose_file_summary_prompt(self, file_path: str, content: str, kb_snippets: List[Dict[str, Any]]) -> Tuple[str, str]:
        kb_text = "\n\n".join([f"- {s['text']}" for s in kb_snippets[:6]])
        system_prompt = (
            "You are a senior analyst and architect. Derive functional and technical summaries from code/workflow CONTEXT. "
            "Ground with the provided KB snippets. Include citations using file paths. If unsure, list open questions."
        )
        user_prompt = (
            f"KB CONTEXT:\n{kb_text or '(none)'}\n\n"
            f"FILE: {file_path}\n"
            f"CONTENT (truncated if large):\n{content[:12000]}\n\n"
            "Return two sections:\n"
            "1) Functional Summary\n"
            "2) Technical Summary\n"
            "Include a short list of {Assumptions} and {Open Questions}.\n"
            f"Cite as ({file_path})."
        )
        return system_prompt, user_prompt

    def _compose_global_docs_prompt(self, per_file_functionals: List[str], per_file_technicals: List[str], kb_snippets: List[Dict[str, Any]]) -> Tuple[str, str]:
        kb_text = "\n".join([f"- {s['text']}" for s in kb_snippets[:10]])
        func_body = "\n\n".join(per_file_functionals)
        tech_body = "\n\n".join(per_file_technicals)
        system_prompt = (
            "You are producing a formal FRD and TRD. Synthesize from the provided functional/technical summaries and KB context. "
            "Ensure traceability (citations by file paths), measurable NFRs, assumptions, and open questions."
        )
        user_prompt = (
            f"KB CONTEXT:\n{kb_text or '(none)'}\n\n"
            f"FUNCTIONAL SUMMARIES:\n{func_body[:24000]}\n\n"
            f"TECHNICAL SUMMARIES:\n{tech_body[:24000]}\n\n"
            "Tasks:\n"
            "FRD:\n- Actors & Glossary\n- Use Cases (preconditions, main/alt flows, postconditions)\n"
            "- Constraints/Policies\n- NFRs (targets)\n- Assumptions + Open Questions\n- Include citations (file paths).\n\n"
            "TRD:\n- Architecture style (+ ASCII diagram)\n- Modules & Public Interfaces\n- Data Models & Storage\n"
            "- Integrations (protocols/auth/errors)\n- CI/CD stages & gates\n- Security & Observability\n- Scalability & Resilience\n"
            "- NFRs with measurable targets\n- Assumptions + Risks + Open Questions\n- Include citations (file paths).\n\n"
            "Output:\n1) A Markdown FRD\n2) A Markdown TRD"
        )
        return system_prompt, user_prompt

    def _store_docs_in_chroma(self, file_path: str, functional: str, technical: str):
        if not self.docs_collection:
            return
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
        chunks = text_splitter.split_text((functional or "") + "\n" + (technical or ""))
        ids = []
        docs = []
        metas = []
        for i, chunk in enumerate(chunks):
            ids.append(f"{file_path}::{i}")
            docs.append(chunk)
            metas.append({"source": file_path})
        try:
            self.docs_collection.add(ids=ids, documents=docs, metadatas=metas)
        except Exception as e:
            logger.warning(f"Failed to store docs in Chroma for {file_path}: {e}")

    def generate_docs(self, top_k_kb: int = 8) -> Dict[str, Any]:
        """
        - Analyze code/workflows
        - Derive intents and retrieve KB snippets
        - Summarize per-file
        - Synthesize FRD/TRD
        - Write MD files to configured paths
        """
        analysis = self.analyze_code()
        intents = self._extract_intents(analysis)
        kb_snippets = self._query_kb(intents, top_k=top_k_kb)

        per_file_functionals: List[str] = []
        per_file_technicals: List[str] = []

        for file_path, meta in analysis.items():
            system_prompt, user_prompt = self._compose_file_summary_prompt(file_path, meta["content"], kb_snippets)
            summary = self._llm_generate(system_prompt=system_prompt, user_prompt=user_prompt, max_tokens=1800)

            # naive split into functional vs technical sections if LLM returns both
            functional = ""
            technical = ""
            lower = summary.lower()
            if "functional" in lower and "technical" in lower:
                # try to split on headings
                parts = re.split(r"(?i)\n+2\)\s*technical summary|\n+technical summary|\n#+\s*technical", summary)
                if len(parts) >= 2:
                    functional = parts[0].strip()
                    technical = parts[1].strip()
                else:
                    functional = summary
                    technical = summary
            else:
                functional = summary
                technical = summary

            per_file_functionals.append(f"### {file_path}\n{functional}")
            per_file_technicals.append(f"### {file_path}\n{technical}")

            # store chunks in Chroma for future retrieval (optional)
            self._store_docs_in_chroma(file_path, functional, technical)

        # Global synthesis for FRD & TRD
        sys2, usr2 = self._compose_global_docs_prompt(per_file_functionals, per_file_technicals, kb_snippets)
        combined_docs = self._llm_generate(system_prompt=sys2, user_prompt=usr2, max_tokens=6000)

        # Try to split combined into FRD and TRD
        frd_md, trd_md = self._split_frd_trd(combined_docs)
        self._write_output_files(frd_md, trd_md)

        return {
            "status": "Completed",
            "frd_path": os.path.abspath(self.frd_path),
            "trd_path": os.path.abspath(self.trd_path),
        }

    def _split_frd_trd(self, combined: str) -> Tuple[str, str]:
        """
        Split the combined markdown into FRD and TRD sections.
        """
        # Look for 'TRD' or 'Technical Requirements' header markers
        parts = re.split(r"(?i)^#\s*TRD|^##\s*TRD|^#\s*Technical Requirements|^##\s*Technical Requirements",
                         combined, flags=re.MULTILINE)
        if len(parts) >= 2:
            frd_md = parts[0].strip()
            trd_md = parts[1].strip()
            return frd_md, trd_md

        # If not separable, duplicate: better to have both than none
        return combined, combined

    def _write_output_files(self, frd_md: str, trd_md: str):
        """
        Ensure directories exist and write FRD/TRD to configured paths.
        """
        for path in [self.frd_path, self.trd_path]:
            os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            with open(self.frd_path, "w", encoding="utf-8") as f:
                f.write(frd_md or "# FRD\n(No content)")
            with open(self.trd_path, "w", encoding="utf-8") as f:
                f.write(trd_md or "# TRD\n(No content)")
            logger.info(f"Wrote FRD -> {self.frd_path}")
            logger.info(f"Wrote TRD -> {self.trd_path}")
        except Exception as e:
            logger.error(f"Failed to write FRD/TRD: {e}")