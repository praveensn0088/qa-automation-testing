import json
import logging
import os
from pathlib import Path
from autogen_ext.tools.mcp import StdioServerParams, McpWorkbench as BaseMcpWorkbench, McpWorkbench
from agent_framework.utils.utils import config_path
from agent_framework.utils.logger import logger
from agent_framework.agent_config.AgentFeedback import AgentFeedback
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_agentchat.conditions import MaxMessageTermination
from autogen_agentchat.ui import Console


class Mcp_config:

    def __init__(self, config_path=config_path):
        try:
            with open(config_path, "r") as file:
                self.config = json.load(file)
            logger.info("Configuration loaded successfully.")
        except FileNotFoundError:
            logger.error(f"Configuration file not found at {config_path}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON config: {e}")
            raise
        except Exception as e:
            logger.exception("Unexpected error loading configuration.")
            raise

    def get_fs_workbench(self, input_dir="", output_dir=""):
        rag_dir = "C:\\Praveen\\Projects\\qa-project-domain\\agent_framework\\memory\\chroma"
        try:
            base_dir = Path(__file__).resolve().parent.parent.parent
            input_path = base_dir / input_dir
            output_path = base_dir / output_dir
            file_system_server_params = StdioServerParams(
                command="cmd",
                args=["/c", "npx", "-y", "@modelcontextprotocol/server-filesystem",
                        str(input_path), str(output_path), str(rag_dir)],
                read_timeout_seconds=120,
                env={**os.environ, "NODE_NO_WARNINGS": "1"}
            )
            logger.info("File System Workbench initialized.")
            return FeedbackEnabledWorkbench(server_params=file_system_server_params)
        except Exception as e:
            logger.exception("Failed to initialize File System Workbench.")
            raise

    def get_jira_workbench(self):
        try:
            jira_entry = Path(
                r"C:\\Praveen\\Projects\\qa-project-domain-transcribe\agent_framework\mcp\mcp-jira-cloud-v2-main\build\index.js"
            )

            jira_server_params = StdioServerParams(
                command="node",
                args=[str(jira_entry)],
                env={
                    "JIRA_URL": self.config["JIRA_URL"],
                    "JIRA_USER_EMAIL": self.config["JIRA_USERNAME"],
                    "JIRA_API_TOKEN": self.config["JIRA_API_TOKEN"],
                },
                read_timeout_seconds=self.config["time_out"],
            )

            logger.info("JIRA Workbench initialized.")
            return McpWorkbench(server_params=jira_server_params)

        except KeyError as e:
            logger.error(f"Missing config key: {e}")
            raise
        except Exception as e:
            logger.exception("Failed to initialize JIRA Workbench.")
            raise

    def get_bitbucket_workbench(self):
        try:
            bitbucket_entry = Path(
                r"C:\\Praveen\\Projects\\qa-project-domain-transcribe\\agent_framework\\mcp\\bitbucket_mcp\\bitbucket-mcp\\dist\\index.js"
            )

            bitbucket_server_params = StdioServerParams(
                command="node",
                args=[str(bitbucket_entry)],
                env={
                    "BITBUCKET_URL": self.config.get("BITBUCKET_URL", "https://api.bitbucket.org/2.0"),
                    "BITBUCKET_WORKSPACE": "is_corp",
                    "BITBUCKET_USERNAME": self.config["BITBUCKET_USERNAME"],
                    "BITBUCKET_PASSWORD": self.config["BITBUCKET_PASSWORD"],
                },
                read_timeout_seconds=self.config["time_out"],
            )
            logger.info("Bitbucket Workbench initialized.")
            return McpWorkbench(server_params=bitbucket_server_params)

        except KeyError as e:
            logger.error(f"Missing config key: {e}")
            raise
        except Exception as e:
            logger.exception("Failed to initialize Bitbucket Workbench.")
            raise

    def get_qTest_workbench(self):
        try:
            qTest_server_params = StdioServerParams(
                command="npx",
                args=[
                    "-y",
                    "mcp-remote",
                    "https://<tenantname>.qtestnet.com/mcp",
                    "--header",
                    "Authorization:${QTEST_TOKEN}"
                ],
                env={
                    "QTEST_TOKEN": "<Bearer xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx>"
                })
            logger.info("qTest Workbench initialized.")
            return McpWorkbench(server_params=qTest_server_params)
        except KeyError as e:
            logger.error(f"Missing config key: {e}")
            raise
        except Exception as e:
            logger.exception("Failed to initialize qTest Workbench.")
            raise

    def get_playwright_workbench(self):
        try:
            playwright_server_params = StdioServerParams(
                command="npx",
                args=["@playwright/mcp@latest", "--headless"],
                read_timeout_seconds=30
            )
            logger.info("Playwright Workbench initialized.")
            return McpWorkbench(server_params=playwright_server_params)
        except Exception as e:
            logger.exception("Failed to initialize Playwright Workbench.")
            raise

    def get_sqlserver_workbench(self):
        try:
            # sqlserver_server_params = StdioServerParams(
            #     command= "uvx",
            # args= ["microsoft_sql_server_mcp"],
            # env = {
            #     "MSSQL_SERVER": self.config['MSSQL_SERVER'],
            #     "MSSQL_DATABASE": self.config['MSSQL_DATABASE'],
            #     "MSSQL_USER": self.config['MSSQL_USER'],
            #     "MSSQL_PASSWORD": self.config['MSSQL_PASSWORD']
            # })

            sqlserver_server_params = StdioServerParams(
                command="npx",
                args=[
                    "-y",
                    "@executeautomation/database-server",
                    "--sqlserver",
                    "--server", self.config['MSSQL_SERVER'],
                    "--database", self.config['MSSQL_DATABASE'],
                    "--user", self.config['MSSQL_USER'],
                    "--password", self.config['MSSQL_PASSWORD'],
                    "--port", self.config['MSSQL_PORT']
                ])
            logger.info("SqlServer Workbench initialized.")
            return McpWorkbench(server_params=sqlserver_server_params)
        except Exception as e:
            logger.exception("Failed to initialize SqlServer Workbench.")
            raise

    def get_cypress_workbench(self):
        try:
            cypress_server_params = StdioServerParams(
                command="npx",
                args=[
                    "tsx", "../mcp/cypress_mcp/test-server.js"],
                read_timeout_seconds=60
            )
            logger.info("Cypress Workbench initialized.")
            return McpWorkbench(server_params=cypress_server_params)
        except Exception as e:
            logger.exception("Failed to initialize Cypress Workbench.")
            raise

    def get_puppeteer_workbench(self):
        try:
            puppeteer_server_params = StdioServerParams(
                command="npx",
                args=[
                    "-y",
                    "@modelcontextprotocol/server-puppeteer"
                ]
            )
            logger.info("Puppeteer Workbench initialized.")
            return McpWorkbench(server_params=puppeteer_server_params)
        except Exception as e:
            logger.exception("Failed to initialize Puppeteer Workbench.")
            raise

    def get_rag_workbench(self):
        try:
            chroma_db_server_params = StdioServerParams(
                command="uvx",
                args=[
                    "chroma-mcp",
                    "--client-type", "persistent",
                    "--data-dir", "C:\\Praveen\\Projects\\qa-project-domain-transcribe\\agent_framework\\memory\\chroma"
                ],
                read_timeout_seconds=120,
            )
            logger.info("Initializing Chroma MCP Workbench...")
            return FeedbackEnabledWorkbench(server_params=chroma_db_server_params)
        except Exception as e:
            logger.exception("Failed to initialize Chroma RAG Workbench.")
            raise

class FeedbackEnabledWorkbench(BaseMcpWorkbench):
    def __init__(self, server_params):
        super().__init__(server_params=server_params)
        self.feedback_log = []
        self.agent_registry = {}

    async def receive_feedback(self, feedback: AgentFeedback):
        self.feedback_log.append(feedback.to_dict())
        logger.info(f"Feedback received: {feedback}")
        if not feedback.success:
            await self.handle_failure(feedback)

    async def handle_failure(self, feedback: AgentFeedback):
        logger.warning(f"Handling failure for task '{feedback.task_id}' by {feedback.agent_name}")

        retry_agent = self.get_agent_by_name(feedback.agent_name)
        fallback_agent = self.get_agent_by_name("user_proxy_agent")

        # Retry logic
        if retry_agent:
            try:
                logger.info(f"Retrying task '{feedback.task_id}' with agent '{retry_agent.name}'")
                team = RoundRobinGroupChat(
                    participants=[retry_agent],
                    termination_condition=MaxMessageTermination(max_messages=2)
                )
                result = await Console(team.run_stream(task=feedback.task_id))
                retry_feedback = await retry_agent.generate_feedback(feedback.task_id, result)
                await self.receive_feedback(retry_feedback)
                return
            except Exception as retry_error:
                logger.error(f"Retry failed for task '{feedback.task_id}': {retry_error}")

        # Escalation logic
        logger.warning(f"Escalating task '{feedback.task_id}' for manual review.")
        self.feedback_log.append({
            "task_id": feedback.task_id,
            "agent_name": feedback.agent_name,
            "status": "Escalated",
            "message": feedback.message
        })

        # Fallback logic
        if fallback_agent:
            try:
                logger.info(f"Routing task '{feedback.task_id}' to fallback agent '{fallback_agent.name}'")
                team = RoundRobinGroupChat(
                    participants=[fallback_agent],
                    termination_condition=MaxMessageTermination(max_messages=2)
                )
                result = await Console(team.run_stream(task=feedback.task_id))
                fallback_feedback = await fallback_agent.generate_feedback(feedback.task_id, result)
                await self.receive_feedback(fallback_feedback)
            except Exception as fallback_error:
                logger.error(f"Fallback agent failed for task '{feedback.task_id}': {fallback_error}")

    def register_agents(self, agents: list):
        for agent in agents:
            self.agent_registry[agent.name] = agent
        logger.info(f"🔗 Registered {len(agents)} agents in workbench.")

    def get_agent_by_name(self, name: str):
        return self.agent_registry.get(name)

    async def cleanup(self) -> None:
        try:
            await self.stop()
        except AttributeError:
            logger.debug("BaseMcpWorkbench has no stop() to call during cleanup")
        self.feedback_log.clear()
        self.agent_registry.clear()
        logger.info("FeedbackEnabledWorkbench cleanup completed.")
