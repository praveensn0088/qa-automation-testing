from agent_framework.agent_config.DomainWorkbench import DomainWorkbench
from agent_framework.agent_config.Mcp_config import Mcp_config
from agent_framework.agent_config.RequirementAgent import RequirementAgent
from agent_framework.utils.utils import load_prompt, load_input_path, get_output_path
from agent_framework.utils.logger import logger
from agent_framework.agent_config.MemoryManager import ShortTermMemory, LongTermMemory
from agent_framework.agent_config.MemoryAwareAssistantAgent import MemoryAwareAssistantAgent
from agent_framework.agent_config.TaskDecompositionAgent import TaskDecompositionAgent
import json
from pathlib import Path
from agent_framework.agent_interface.stt_strategy import HuggingFaceSTTStrategy, AzureSTTStrategy, TranscriptAgent
from metrics.instrumentation_agent import instrument_agent
from metrics.track_latency_agent import track_agent_latency

class AgentFactory:

    def __init__(self, model_client, config_path):
        self.model_client = model_client
        try:
            self.mcp_config = Mcp_config(config_path=config_path)
            logger.info("Mcp_config initialized successfully.")
        except Exception as e:
            logger.exception("Failed to initialize Mcp_config.")
            raise

        config = self.mcp_config.config
        use_chroma = config.get("use_chroma_memory", False)
        storage_path=config.get("storage_path")

        self.stm = ShortTermMemory()
        self.ltm = LongTermMemory(storage_path=storage_path, use_chroma=use_chroma)

    def create_task_decomposition_agent(self, system_message=None):
        try:
            system_message = system_message or (
                "You are a Task Decomposition Agent. Break down tasks into subtasks with metadata."
            )
            task_decomposer = TaskDecompositionAgent(
                name="task_decomposer",
                model_client=self.model_client,
                short_term_memory=self.stm,
                long_term_memory=self.ltm,
                system_message=system_message
            )

            print("=== MESSAGE METHODS ===")
            print("message:", [m for m in dir(task_decomposer) if "message" in m.lower()])
            print("receive:", [m for m in dir(task_decomposer) if "receive" in m.lower()])
            print("handle:", [m for m in dir(task_decomposer) if "handle" in m.lower()])
            print("process:", [m for m in dir(task_decomposer) if "process" in m.lower()])

            logger.info("Task Decomposition Agent created successfully.")
            return instrument_agent(task_decomposer)
        except Exception as e:
            logger.exception("Failed to create Task Decomposition Agent.")
            raise


    def create_user_proxy_agent(self, file_path, name, system_message=None):
        try:
            system_message = system_message or load_prompt("user_proxy_agent", "role_prompts") or (
                "You are a UserProxyAgent acting on behalf of a human user in a multi-agent collaboration system. Your role is to receive messages from other agents, interpret them as if you were the user, and respond with appropriate actions, decisions, or clarifications."
            )
            name = name or ("user_proxy_agent")

            user_proxy_agent = MemoryAwareAssistantAgent(
                name="user_proxy_agent",
                model_client=self.model_client,
                workbench=self.mcp_config.get_fs_workbench(),
                system_message=system_message,
                short_term_memory = self.stm,
                long_term_memory = self.ltm,
                memory_enabled=False
            )
            logger.info("User Proxy agent created successfully.")
            return instrument_agent(user_proxy_agent)
        except Exception as e:
            logger.exception("Failed to create User Proxy agent.")
            raise

    def create_jira_agent(self, system_message=None):
        try:
            system_message = system_message or load_prompt("jira_agent", "role_prompts") or (
            f"You are a Jira client. You need to fetch all issues using the project filter. "
            "**Log all issue keys retrieved.** "
            "**Search for the issue key provided by user among them and log whether it was found.** "
            "If found, extract its summary and acceptance criteria. "
            "If not found, fallback to using all issues. "
            "Then share this information to qa_agent to generate manual test cases."
        )
            workbench = self.mcp_config.get_jira_workbench()
            workbench.tool_call_timeout = 60

            jira_agent = MemoryAwareAssistantAgent(
                name="jira_agent",
                model_client=self.model_client,
                workbench=workbench,
                system_message=system_message,
                short_term_memory=self.stm,
                long_term_memory=self.ltm,
                memory_enabled=True
            )
            logger.info("JIRA agent created successfully.")
            return instrument_agent(jira_agent)
        except Exception as e:
            logger.exception("Failed to create JIRA agent.")
            raise

    def create_bitbucket_agent(self, system_message=None):
        try:
            system_message = system_message or load_prompt("bitbucket_agent", "role_prompts") or (
                f"You are a Bitbucket agent. You need to verify repository and branch existence using the repo URL and branch name filter. "
                "**Log the repo URL and branch name provided.** "
                "**Use test_repo() and test_branch() functions to check existence.** "
                "**Log whether repo and branch were found.** "
                "If both exist, extract workspace/repo_slug/branch details. "
                "If repo/branch missing, report specific errors. "
                "Then share this information to qa_agent for test case generation."
            )
            workbench = self.mcp_config.get_bitbucket_workbench()
            workbench.tool_call_timeout = 60

            bitbucket_agent = MemoryAwareAssistantAgent(
                name="bitbucket_agent",
                model_client=self.model_client,
                workbench=workbench,
                system_message=system_message,
                short_term_memory=self.stm,
                long_term_memory=self.ltm,
                memory_enabled=True
            )
            logger.info("Bitbucket agent created successfully.")
            return instrument_agent(bitbucket_agent)
        except Exception as e:
            logger.exception("Failed to create JIRA agent.")
            raise


    def create_qtest_agent(self, system_message=None):
        try:
            system_message = system_message or load_prompt("qtest_agent") or (
            f"You are a qTest client. You need to fetch all issues using the project filter. "
            "**Log all issue keys retrieved.** "
            "**Search for the issue key provided by user among them and log whether it was found.** "
            "If found, extract its summary and acceptance criteria. "
            "If not found, fallback to using all issues. "
            "Then share this information to qa_agent to generate manual test cases."
        )

            qtest_agent = MemoryAwareAssistantAgent(
                name="qtest_agent",
                model_client=self.model_client,
                workbench=self.mcp_config.get_qTest_workbench(),
                system_message=system_message,
                short_term_memory=self.stm,
                long_term_memory=self.ltm,
                memory_enabled=True
            )
            logger.info("qTest agent created successfully.")
            return instrument_agent(qtest_agent)
        except Exception as e:
            logger.exception("Failed to create qTest agent.")
            raise

    def create_fs_read_agent(self, file_name, input_dir, output_dir, system_message=None):
        input_path = load_input_path(file_name, input_dir)
        try:
            if system_message is None:
                prompt_template = load_prompt("fs_read_agent", "role_prompts")

                if prompt_template:
                    system_message = prompt_template.format(file_path=str(input_path))
                    logger.info(f"Loaded and formatted prompt template for file: {input_path}")
                else:
                    system_message = (
                        f"You are a file system agent. Your duty is to create, read, modify, delete, and update files "
                        f"based on the user request and specified file path: {input_path}"
                    )
                    logger.warning("Prompt template not found, using fallback message")


            fs_read_agent = MemoryAwareAssistantAgent(
                name="fs_read_agent",
                model_client=self.model_client,
                workbench=self.mcp_config.get_fs_workbench(input_dir, output_dir),
                system_message=system_message,
                short_term_memory=self.stm,
                long_term_memory=self.ltm,
                memory_enabled=True
            )
            logger.info("File System Read agent created successfully.")
            return instrument_agent(fs_read_agent)
        except Exception as e:
            logger.exception("Failed to create File System Read agent.")
            raise

    def create_fs_write_agent(self, input_file_name=None, agent_name="", output_dir="", input_dir="",
                              system_message=None, name=None):
        try:
            output_file_path = get_output_path(agent_name, input_file_name, output_dir)
            if system_message is None:
                prompt_template = load_prompt("fs_write_agent", "role_prompts")

                if prompt_template:
                    system_message = prompt_template.format(file_path=str(output_file_path))
                else:
                    system_message = (
                        f"You are a file system agent. Your duty is to create, read, modify, delete, write, and update files.\n\n"
                        f"The output file you should create/write to is: {str(output_file_path)}\n\n"
                        f"Use the MCP file system tools to write content to this file path."
                    )
            name = name or ("fs_write_agent")

            fs_write_agent = MemoryAwareAssistantAgent(
                name=name,
                model_client=self.model_client,
                workbench=self.mcp_config.get_fs_workbench(input_dir, output_dir),
                system_message=system_message,
                short_term_memory=self.stm,
                long_term_memory=self.ltm,
                memory_enabled=True
            )
            logger.info("File System Write agent created successfully.")
            return instrument_agent(fs_write_agent), output_file_path
        except Exception as e:
            logger.exception("Failed to create File System Write agent.")
            raise

    def create_fs_update_agent(self, system_message=None):
        try:
            system_message = system_message or load_prompt("fs_update_agent") or (
                "You are a file system agent. Your duty is to create, read, modify, delete, write, and update files "
                "based on the request with the provided content."
            )

            fs_update_agent = MemoryAwareAssistantAgent(
                name="fs_update_agent",
                model_client=self.model_client,
                workbench=self.mcp_config.get_fs_workbench(),
                system_message=system_message,
                short_term_memory=self.stm,
                long_term_memory=self.ltm,
                memory_enabled=True
            )
            logger.info("File System Update agent created successfully.")
            return instrument_agent(fs_update_agent)
        except Exception as e:
            logger.exception("Failed to create File System Update agent.")
            raise

    def create_qa_agent(self, system_message=None):
        try:
            system_message = system_message or load_prompt("qa_agent", "role_prompts") or (
            "You are a highly skilled, "
             "tech-savvy Software Quality Engineer with deep expertise in manual testing and a strong understanding "
             "of e-commerce systems. Your role involves thoroughly analyzing story descriptions related to product listings, "
             "shopping cart behavior, payment gateways, user authentication, order management, and promotional logic. "
             "You proactively identify edge cases, usability issues, and integration risks across the customer journey — from "
             "browsing to checkout and post-purchase.You are responsible for designing and executing detailed positive and negative "
             "test scenarios that reflect real-world user behavior, including mobile responsiveness, multi-device compatibility, "
             "and localization. You write clear, step-by-step manual test cases that ensure every feature meets functional, "
             "performance, and security expectations. You collaborate with developers, UX designers, and product managers to "
             "clarify requirements and advocate for quality at every sprint. Your mission is to catch defects early, prevent "
             "revenue-impacting bugs, and ensure a seamless, trustworthy shopping experience for customers."
        )

            qa_agent = MemoryAwareAssistantAgent(
                name="qa_agent",
                model_client=self.model_client,
                workbench=self.mcp_config.get_fs_workbench("", ""),
                system_message=system_message,
                short_term_memory=self.stm,
                long_term_memory=self.ltm,
                memory_enabled=True
            )
            logger.info("QA agent created successfully.")
            return instrument_agent(qa_agent)
        except Exception as e:
            logger.exception("Failed to create QA agent.")
            raise

    def create_qa_reviewer_agent(self, system_message=None):
        try:
            system_message = system_message or load_prompt("qa_reviewer_agent", "role_prompts") or (
            "You are a highly skilled, "
            "tech-savvy Software Quality Engineer with deep expertise in manual testing and a strong understanding "
            "of e-commerce systems. Your role involves thoroughly analyzing story descriptions related to product listings, "
            "shopping cart behavior, payment gateways, user authentication, order management, and promotional logic. "
            "You proactively identify edge cases, usability issues, and integration risks across the customer journey — from "
            "browsing to checkout and post-purchase.You are responsible for designing and executing detailed positive and negative "
            "test scenarios that reflect real-world user behavior, including mobile responsiveness, multi-device compatibility, "
            "and localization. You write clear, step-by-step manual test cases that ensure every feature meets functional, "
            "performance, and security expectations. You collaborate with developers, UX designers, and product managers to "
            "clarify requirements and advocate for quality at every sprint. Your mission is to catch defects early, prevent "
            "revenue-impacting bugs, and ensure a seamless, trustworthy shopping experience for customers."
        )

            qa_reviewer_agent = MemoryAwareAssistantAgent(
                name="qa_reviewer_agent",
                model_client=self.model_client,
                system_message=system_message,
                short_term_memory=self.stm,
                long_term_memory=self.ltm,
                memory_enabled=True
            )
            logger.info("QA Reviewer agent created successfully.")
            return instrument_agent(qa_reviewer_agent)
        except Exception as e:
            logger.exception("Failed to create QA Reviewer agent.")
            raise

    def create_playwright_dev_agent(self, input_file="", output_dir="" , target_dir='', system_message=None):
        try:
            in_abs = load_input_path(input_file, target_dir)
            out_abs = get_output_path("qe_agent", input_file, output_dir)
            system_message = system_message or load_prompt("playwright_developer_agent", "role_prompts") or (
            "You are a seasoned JavaScript automation engineer with deep expertise in Playwright, "
                                                                   "specializing in automating e-commerce applications. Your core responsibility is to "
                                                                   "translate detailed manual test cases into reliable, scalable automation scripts. "
                                                                   "You must design and implement a robust Playwright automation framework using the "
                                                                   "Page Object Model (POM) architecture, strictly adhering to object-oriented programming principles "
                                                                   "and industry-standard design patterns. Your scripts should reflect best practices in maintainability, "
                                                                   "readability, and reusability. Ensure all dynamic or frequently changing values—such as website URLs, "
                                                                   "user credentials, browser types, and environment configurations—are externalized into configurable variables."
                                                                   " Your automation should be capable of handling complex e-commerce flows including login, product search, cart operations, "
                                                                   "checkout, payment, and order confirmation, with a focus on cross-browser compatibility and performance."
        )
            system_message = (
                system_message
                .replace("{auto_repo_path}", str(out_abs))
                .replace("{outputData_path}", str(in_abs))
            )
            playwright_developer_agent = MemoryAwareAssistantAgent(
                name="playwright_developer_agent",
                model_client=self.model_client,
                workbench=self.mcp_config.get_playwright_workbench(),
                system_message=system_message,
                short_term_memory=self.stm,
                long_term_memory=self.ltm,
                memory_enabled=True
            )
            logger.info("Playwright Developer agent created successfully.")
            return instrument_agent(playwright_developer_agent)
        except Exception as e:
            logger.exception("Failed to create Playwright Developer agent.")
            raise

    def create_playwright_reviewer_agent(self, file_path,system_message=None):
        try:
            system_message = system_message or load_prompt("playwright_reviewer_agent", "role_prompts") or (
                                    "You are a meticulous and experienced Playwright Automation Reviewer specializing in "
                                    "JavaScript-based test automation for complex e-commerce applications."
                                    "Your primary responsibility is to **review automation scripts** developed by the Playwright "
                                    "Developer Agent to ensure they meet the highest standards of **quality, maintainability, and "
                                    "alignment with business requirements."
        )
            playwright_reviewer_agent = MemoryAwareAssistantAgent(
                name="playwright_reviewer_agent",
                model_client=self.model_client,
                workbench=self.mcp_config.get_playwright_workbench(),
                system_message=system_message,
                short_term_memory=self.stm,
                long_term_memory=self.ltm,
                memory_enabled=True
            )
            logger.info("Playwright Reviewer agent created successfully.")
            return instrument_agent(playwright_reviewer_agent)
        except Exception as e:
            logger.exception("Failed to create Playwright Reviewer agent.")
            raise

    def create_playwright_execution_agent(self, file_path,system_message=None):
        try:
            system_message = system_message or load_prompt("playwright_execution_agent") or (
                                    " You are an Automation Execution Agent responsible for running"
                                    " Playwright-based test suites locally on a Chrome browser. "
                                    "Your role is to ensure that the automation framework is correctly "
                                    "initialized, dependencies are installed, and tests are executed in a clean,"
                                    " repeatable, and traceable manner."
                                    )
            playwright_execution_agent = MemoryAwareAssistantAgent(
                name="playwright_execution_agent",
                model_client=self.model_client,
                workbench=self.mcp_config.get_playwright_workbench(),
                system_message=system_message,
                short_term_memory=self.stm,
                long_term_memory=self.ltm,
                memory_enabled=True
            )
            logger.info("Playwright execution agent created successfully.")
            return instrument_agent(playwright_execution_agent)
        except Exception as e:
            logger.exception("Failed to create execution Reviewer agent.")
            raise

    def create_db_agent(self, system_message=None):
        try:
            system_message = system_message or load_prompt("db_agent")
            db_agent = MemoryAwareAssistantAgent(
                name="db_agent",
                model_client=self.model_client,
                workbench=self.mcp_config.get_sqlserver_workbench(),
                system_message=system_message,
                short_term_memory=self.stm,
                long_term_memory=self.ltm,
                memory_enabled=True
            )
            logger.info("DB agent created successfully.")
            return instrument_agent(db_agent)
        except Exception as e:
            logger.exception("Failed to create DB agent.")
            raise

    def create_cypress_dev_agent(self, input_path, output_path,system_message=None):
        try:
            print("input_path: ", input_path)
            print("output_path: ", output_path)
            system_message = system_message or load_prompt("cypress_developer_agent", "role_prompts") or (
            "You are a seasoned JavaScript automation engineer with deep expertise in Cypress, "
                                                                   "specializing in automating e-commerce applications. Your core responsibility is to "
                                                                   "translate detailed manual test cases into reliable, scalable automation scripts. "
                                                                   "You must design and implement a robust Playwright automation framework using the "
                                                                   "Page Object Model (POM) architecture, strictly adhering to object-oriented programming principles "
                                                                   "and industry-standard design patterns. Your scripts should reflect best practices in maintainability, "
                                                                   "readability, and reusability. Ensure all dynamic or frequently changing values—such as website URLs, "
                                                                   "user credentials, browser types, and environment configurations—are externalized into configurable variables."
                                                                   " Your automation should be capable of handling complex e-commerce flows including login, product search, cart operations, "
                                                                   "checkout, payment, and order confirmation, with a focus on cross-browser compatibility and performance."
        )
            system_message = system_message.format(
                auto_repo_path=output_path,
                outputData_path=input_path
            )
            print("system_message", system_message)

            cypress_developer_agent = MemoryAwareAssistantAgent(
                name="cypress_developer_agent",
                model_client=self.model_client,
                workbench=self.mcp_config.get_cypress_workbench(),
                system_message=system_message,
                short_term_memory=self.stm,
                long_term_memory=self.ltm,
                memory_enabled=True

            )
            logger.info("Cypress Developer agent created successfully.")
            return instrument_agent(cypress_developer_agent)
        except Exception as e:
            logger.exception("Failed to create Cypress Developer agent.")
            raise

    def create_puppeteer_dev_agent(self, file_path,system_message=None):
        try:
            system_message = system_message or load_prompt("puppeteer_developer_agent") or (
            "You are a seasoned JavaScript automation engineer with deep expertise in Puppeteer, "
                                                                   "specializing in automating e-commerce applications. Your core responsibility is to "
                                                                   "translate detailed manual test cases into reliable, scalable automation scripts. "
                                                                   "You must design and implement a robust automation framework using the "
                                                                   "Page Object Model (POM) architecture, strictly adhering to object-oriented programming principles "
                                                                   "and industry-standard design patterns. Your scripts should reflect best practices in maintainability, "
                                                                   "readability, and reusability. Ensure all dynamic or frequently changing values—such as website URLs, "
                                                                   "user credentials, browser types, and environment configurations—are externalized into configurable variables."
                                                                   " Your automation should be capable of handling complex e-commerce flows including login, product search, cart operations, "
                                                                   "checkout, payment, and order confirmation, with a focus on cross-browser compatibility and performance."
        )
            puppeteer_developer_agent = MemoryAwareAssistantAgent(
                name="puppeteer_developer_agent",
                model_client=self.model_client,
                workbench=self.mcp_config.get_puppeteer_workbench(),
                system_message=system_message,
                short_term_memory=self.stm,
                long_term_memory=self.ltm,
                memory_enabled=True

            )
            logger.info("Puppeteer Developer agent created successfully.")
            return instrument_agent(puppeteer_developer_agent)
        except Exception as e:
            logger.exception("Failed to create Puppeteer Developer agent.")
            raise

    def create_requirement_agent(self):
        return RequirementAgent("requirement_agent", self.model_client, self.stm, self.ltm)

    def create_knowledge_agent(self, system_message=None):
        system_message = system_message or (
            "You are a Knowledge Agent. You need to traverse through the data available in the path specified in - 'storage_path' from config.json "
            " and retrieve the relevent data for the query asked and summarize relevant information and share the details to other agents as required."
        )
        knowledge_agent = MemoryAwareAssistantAgent(
            name="knowledge_agent",
            model_client=self.model_client,
            workbench=self.mcp_config.get_rag_workbench(),
            system_message=system_message,
            short_term_memory=self.stm,
            long_term_memory=self.ltm,
            memory_enabled=True
        )
        return instrument_agent(knowledge_agent)

    def create_domain_agent(self, config_path, system_message=None):
        system_message = (
            "You are a Domain Agent. Crawl through the repositories, analyze code,read the documentation available,code comments map with knowledge base to understand the context and workflows and generate a detailed functional and technical documentation."
        )
        domain_wb = DomainWorkbench(config_path=config_path)
        domain_agent = MemoryAwareAssistantAgent(
            name="domain_agent",
            model_client=self.model_client,
            workbench=domain_wb,
            system_message=system_message,
            short_term_memory=self.stm,
            long_term_memory=self.ltm,
            memory_enabled=True
        )
        return instrument_agent(domain_agent)

    def create_transcript_agent(self, config_values):
        if config_values.get("use_huggingface", True):
            strategy = HuggingFaceSTTStrategy(
                model_name=config_values.get("huggingface_model", "openai/whisper-small"),
                local_mode=config_values.get("huggingface_local_mode", False),
                device="cpu"
            )
        elif config_values.get("use_azure"):
            strategy = AzureSTTStrategy(
                config_values.get("AZURE_SPEECH_KEY"),
                config_values.get("AZURE_SPEECH_REGION")
            )
        else:
            raise ValueError("No STT strategy configured.")

        return TranscriptAgent(
            name="transcript_agent",
            model_client=self.model_client,
            short_term_memory=self.stm,
            long_term_memory=self.ltm,
            stt_strategy=strategy
        )


class SummaryAgent:
    def __init__(self, name="summary_agent"):
        self.name = name
        self.summary_data = []

    def add_task_summary(self, task_id, agent_name, task_name, status, write_to_file, comments):
        self.summary_data.append({
            "Task": task_id,
            "Agent Name": agent_name,
            "Task Name": task_name,
            "Status": status,
            "Write to Files": "Yes" if write_to_file else "No",
            "Comments": comments
        })

    def generate_summary_table(self):
        headers = ["Task", "Agent Name", "Task Name", "Status", "Write to Files", "Comments"]
        table = " | ".join(headers) + "\n" + "-" * 120 + "\n"
        for row in self.summary_data:
            table += f"{row['Task']} | {row['Agent Name']} | {row['Task Name']} | {row['Status']} | {row['Write to Files']} | {row['Comments']}\n"
        return table

    def save_summary_to_file(self, output_path):
        summary_file = Path(output_path) / "agent_summary.json"
        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump(self.summary_data, f, indent=2)
        return summary_file


    def print_summary(self):
        print("\n=== Task Summary ===")
        for summary in self.summary_data:
            print(f"Task: {summary['task_id']} | Agent: {summary['agent_name']} | Status: {summary['status']} | Comments: {summary['comments']}")

    def export_summary(self, file_path="summary.json"):
        import json
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w") as f:
            json.dump(self.summary_data, f, indent=4)
