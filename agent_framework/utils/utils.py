from sentence_transformers import SentenceTransformer
import numpy as np
import logging
from pathlib import Path
import asyncio
import httpx
import json
import plotly.graph_objects as go
from agent_framework.utils.logger import logger
from typing import Optional
from datetime import datetime
from autogen_agentchat.ui import Console
import requests
from requests.auth import HTTPBasicAuth
import re
import subprocess
from typing import Optional, Dict


try:
    current_dir = Path(__file__).resolve().parent
    config_path = current_dir.parent / "config.json"

    with open(config_path, "r") as file:
        config = json.load(file)
    logger.info("Configuration loaded successfully.")
    api_key = config.get("AZURE_OPENAI_API_KEY")
    api_version = config.get("AZURE_OPENAI_API_VERSION")
    AZURE_OPENAI_ENDPOINT = config.get("AZURE_OPENAI_ENDPOINT")
    model_name = config.get("model_name")
    AZURE_OPENAI_DEPLOYMENT_ID = config.get("AZURE_OPENAI_DEPLOYMENT_ID")

except Exception as e:
    logger.error("Failed to resolve config path: %s", str(e), exc_info=True)
    config_path = None

model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')


def load_prompt(agent_name, dir):
    try:
        filepath = Path(f"agent_framework/prompts/{dir}/{agent_name}.txt")
        if filepath.exists():
            with open(filepath, "r", encoding="utf-8") as f:
                prompt = f.read()
                logger.info("Loaded prompt for agent: %s", agent_name)
                return prompt
        else:
            logger.warning("Prompt file not found for agent: %s", agent_name)
            return ""
    except Exception as e:
        logger.error("Error loading prompt for agent '%s': %s", agent_name, str(e), exc_info=True)
        return ""

def connect():
    import pyodbc
    query = "SELECT * FROM MSreplication_options"
    # Update these values to match your environment
    conn_str = (
        "DRIVER={ODBC Driver 17 for SQL Server};"
        "SERVER=ICPL14678\\SQL2025;"
        "DATABASE=master;"
        "UID=sa;"
        "PWD=Power@123$"
        "Encrypt=yes;"
        "TrustServerCertificate=yes;"
    )

    conn = pyodbc.connect(conn_str)
    cursor = conn.cursor()

    cursor.execute()
    rows = cursor.fetchall()

    for row in rows:
        print(row)

    cursor.close()
    conn.close()

def get_embedding(text):
    embedding = model.encode(text)
    return np.array(embedding)

def compute_similarity(text1, text2):
    emb1 = get_embedding(text1)
    emb2 = get_embedding(text2)
    return np.dot(emb1, emb2) / (np.linalg.norm(emb1) * np.linalg.norm(emb2))

def route_subtask(subtask, agents):
    """
    Route a subtask to the most appropriate agent using agent_hint or keyword matching.
    Returns (agent, score)
    """
    if not isinstance(subtask, dict):
        logger.error(f"Invalid subtask format: {subtask}")
        return None, 0.0

    hint = subtask.get("agent_hint", "").lower()
    task_text = subtask.get("task", "").lower()

    for agent in agents:
        if hint and hint in agent.name.lower():
            return agent, 1.0

    keyword_map = {
        "read": "fs_read_agent",
        "write": "fs_write_agent",
        "qa": "qa_agent",
        "test": "qa_agent",
        "review": "playwright_reviewer_agent",
        "execute": "playwright_execution_agent",
        "playwright": "playwright_dev_agent",
        "cypress": "cypress_developer_agent",
        "puppeteer": "puppeteer_dev_agent",
        "jira": "jira_agent",
        "qtest": "qtest_agent",
        "db": "db_agent"
    }

    for keyword, agent_name in keyword_map.items():
        if keyword in task_text:
            for agent in agents:
                if agent.name == agent_name:
                    return agent, 0.9

    return agents[0], 0.5

def visualize_subtask_agent_mapping(subtask_status):
    subtask_status = convert_to_serializable(subtask_status)

    subtasks = list(subtask_status.keys())
    agents = list(set([v["agent"] for v in subtask_status.values()]))

    label = subtasks + agents
    source, target, value = [], [], []

    for i, subtask in enumerate(subtasks):
        agent_name = subtask_status[subtask]["agent"]
        agent_index = label.index(agent_name)
        source.append(i)
        target.append(agent_index)
        value.append(subtask_status[subtask]["score"])

    fig = go.Figure(data=[go.Sankey(
        node=dict(pad=15, thickness=20, line=dict(color="black", width=0.5), label=label),
        link=dict(source=source, target=target, value=value)
    )])

    try:
        fig.write_image("subtask_agent_mapping.png")
    except ValueError:
        print("Kaleido not installed. Saving as HTML instead.")
        fig.write_html("subtask_agent_mapping.html")

def convert_to_serializable(obj):
    if isinstance(obj, dict):
        return {k: convert_to_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_to_serializable(v) for v in obj]
    elif isinstance(obj, np.float32):
        return float(obj)
    else:
        return obj

def normalize_embeddings(embeddings):
    if not embeddings:
        return embeddings
    while isinstance(embeddings[0], list):
        embeddings = embeddings[0]
    return embeddings

def get_output_path(
    agent: str,
    input_file_name: Optional[str] = None,
    output_suffix: str = "",
) -> Optional[Path]:
    repo_root = Path(__file__).resolve().parent.parent.parent
    output_dir = repo_root / output_suffix
    if agent == "qa_agent" or agent == "write_agent":
        if not input_file_name:
            raise ValueError("input_file_name is required for qa_agent")
        base_name = Path(input_file_name).stem
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file_name = f"{base_name}_ManualTCs_{timestamp}.csv"


        output_file_path = output_dir / output_file_name
        output_file_path.touch(exist_ok=True)

        logger.info(f"Dynamic output file: {output_file_name}")
        logger.info(f"Full path: {output_file_path}")

        return output_file_path

    elif agent == "qe_agent" or agent == "auto_write_agent":
        if not input_file_name:
            raise ValueError("input_file_name is required for qe_agent")
        base_name = Path(input_file_name).stem
        output_dir.mkdir(parents=True, exist_ok=True)

        folder_name = f"AutomationRepo_Play_Js_{base_name}_Repo"
        folder_path = output_dir / folder_name
        folder_path.mkdir(parents=True, exist_ok=True)

        logger.info(f"QE folder ensured: {folder_path}")
        return folder_path

    if agent == "jira_agent":
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file_name = f"{input_file_name}_JiraTCs_{timestamp}.csv"


        output_file_path = output_dir / output_file_name
        output_file_path.touch(exist_ok=True)

        logger.info(f"Dynamic output file: {output_file_name}")
        logger.info(f"Full path: {output_file_path}")

        return output_file_path


    else:
        raise ValueError("agent must be 'qa_agent' or 'qe_agent'")

def load_input_path(filename, target_dir):
    base_dir = Path(__file__).resolve().parent.parent.parent
    target_dir = Path(target_dir)
    full_path = base_dir / target_dir / filename
    print(full_path)

    if not full_path.exists():
        raise FileNotFoundError(f"Input file not found: {full_path}")
    return full_path

async def RateLimiter(coroutine_func, *args, max_retries=5, base_delay=1, **kwargs):
    """
    Implements an exponential backoff and 'Retry-After' header check
    for handling 429 (Too Many Requests) errors from API calls.

    Args:
        coroutine_func: The asynchronous function (e.g., an OpenAI call) to wrap.
        *args: Positional arguments for coroutine_func.
        max_retries: Maximum number of times to retry on a 429 error.
        base_delay: The initial delay in seconds for exponential backoff.
        **kwargs: Keyword arguments for coroutine_func.

    Raises:
        Exception: If max retry attempts are reached or a non-429 HTTP error occurs.
    """
    for attempt in range(max_retries):
        try:
            # 1. Attempt the coroutine call
            result = await coroutine_func(*args, **kwargs)
            return result

        except httpx.HTTPStatusError as e:
            # 2. Check if the error is a 429 (Rate Limit)
            if e.response.status_code == 429:
                retry_after = e.response.headers.get("Retry-After")

                # Calculate wait time: Use 'Retry-After' if available and valid, otherwise exponential backoff
                wait_time = base_delay * (2 ** attempt)
                if retry_after and retry_after.isdigit():
                    wait_time = int(retry_after)

                print(f"429 Too Many Requests. Backing off for {wait_time}s (attempt {attempt + 1}/{max_retries})")

                # Sleep only if there are more attempts left
                if attempt < max_retries - 1:
                    await asyncio.sleep(wait_time)

            # 3. Re-raise any other HTTP error (e.g., 400, 401, 500)
            else:
                raise e

                # 4. Catch non-HTTP errors (e.g., connection issues) and allow retries
        except Exception as e:
            print(f"An unexpected error occurred: {e} (attempt {attempt + 1}/{max_retries})")
            if attempt < max_retries - 1:
                await asyncio.sleep(base_delay)  # Use a simple delay for non-429 errors
            else:
                raise e

    # 5. If the loop completes without returning, max retries were reached
    raise Exception(f"Max retry attempts ({max_retries}) reached due to persistent errors.")


async def get_jira_story(story_id: str) -> Optional[str]:
    jira_base_url = config.get("JIRA_URL")
    email = config.get("JIRA_USERNAME")
    api_token = config.get("JIRA_API_TOKEN")

    if not all([jira_base_url, email, api_token]):
        raise ValueError("Jira credentials not provided")

    url = f"{jira_base_url}/rest/api/3/issue/{story_id.strip()}"
    auth = HTTPBasicAuth(email, api_token)
    headers = {"Accept": "application/json"}

    try:
        response = await asyncio.to_thread(
            requests.get, url, headers=headers, auth=auth, timeout=30
        )
        response.raise_for_status()
        data = response.json()
        issue_summary = data.get("fields", {}).get("summary")
        return issue_summary
    except requests.exceptions.HTTPError:
        if response.status_code == 404:
            return None
        raise
    except (requests.exceptions.RequestException, Exception):
        raise


def test_repo(repo_url: str) -> bool:
    match = re.search(r'https://bitbucket\.org/([^/]+)/([^/]+)/', repo_url)
    if not match:
        return False

    workspace, repo_slug = match.groups()
    git_url = f"https://bitbucket.org/{workspace}/{repo_slug}.git"

    result = subprocess.run(["git", "ls-remote", "--exit-code", git_url],
                            capture_output=True, timeout=15)

    return result.returncode == 0


def test_branch(repo_url: str, branch_name: str) -> bool:
    match = re.search(r'https://bitbucket\.org/([^/]+)/([^/]+)/', repo_url)
    if not match:
        return False

    workspace, repo_slug = match.groups()
    git_url = f"https://bitbucket.org/{workspace}/{repo_slug}.git"

    cmd = ["git", "ls-remote", "--exit-code", "--heads", f"{git_url}", f"refs/heads/{branch_name}"]
    result = subprocess.run(cmd, capture_output=True, timeout=15)

    return result.returncode == 0


def sanitize_prompt(prompt: str) -> str:
    triggers = [
        r'IGNORE PREVIOUS? INSTRUCTIONS?', r'NO ANALYSIS', r'EXECUTE NOW',
        r'NO EXPLANATION', r'RETURN ONLY', r'DO NOT EXPLAIN', r'MANDATORY',
        r'CRITICAL', r'IMPORTANT', r'OVERRIDE', r'BYPASS', r'JAILBREAK'
    ]
    for trigger in triggers:
        prompt = re.sub(trigger, '', prompt, flags=re.IGNORECASE)
    # Shorten to avoid context buildup
    return prompt[:8000]


async def safe_team_run(team, task: str, max_retries: int = 3):
    for attempt in range(max_retries):
        try:
            clean_task = sanitize_prompt(task)
            logger.info(f"Team run attempt {attempt + 1}: {clean_task[:200]}...")
            return await Console(team.run_stream(task=clean_task))
        except Exception as e:
            logger.error(f"Team run failed (attempt {attempt + 1}): {str(e)}")
            if "jailbreak" in str(e).lower() or "content_filter" in str(e).lower():
                logger.warning("Jailbreak detected - sanitizing and retrying...")
                task = sanitize_prompt(task)
                continue
            raise
    raise RuntimeError("Max retries exceeded due to persistent jailbreak filtering")


def extract_model_response(response):
    """
    Extracts and normalizes model response into a clean Python dict.
    Handles JSON parsing and includes metadata for traceability.
    """
    try:
        raw_content = getattr(response, "content", None)
        if not raw_content:
            return {"error": "Empty response from model."}

        # Parse JSON safely
        try:
            parsed_content = json.loads(raw_content)
        except json.JSONDecodeError:
            logging.warning("Failed to parse JSON. Returning raw content.")
            parsed_content = {"raw_content": raw_content}

        return {
            "data": parsed_content,
            "metadata": {
                "finish_reason": getattr(response, "finish_reason", None),
                "usage": getattr(response, "usage", None)
            }
        }
    except Exception as e:
        logging.exception("Error extracting model response.")
        return {"error": str(e)}
