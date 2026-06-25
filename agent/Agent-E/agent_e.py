# import asyncio
import json
import os
import time
from ae.core.agents_llm_config import AgentsLLMConfig
# from test.evaluators import evaluator_router
from typing import Any

import ae.core.playwright_manager as browserManager
import nltk  # type: ignore
from ae.config import PROJECT_TEST_ROOT
from ae.core.autogen_wrapper import AutogenWrapper
from ae.core.playwright_manager import PlaywrightManager
from ae.utils.logger import logger
from ae.utils.response_parser import parse_response
from autogen.agentchat.chat import ChatResult  # type: ignore
# from playwright.async_api import Page
from playwright.sync_api import Page
from tabulate import tabulate
from termcolor import colored

"""Implements helper functions to assist evaluation cases where other evaluators are not suitable."""
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from nltk.tokenize import word_tokenize  # type: ignore
from openai import OpenAI
import web_controller
import traceback
import shutil
import json

load_dotenv()

def load_config(config_file: Path | str) -> list[dict[str, Any]]:
    """Load the confiufiguration for the test cases

    Args:
        config_file (Path | str): Path to the config file

    Returns:
        list[dict[str, Any]]: All the test cases in the config file
    """
    with open(config_file, "r") as f:  # noqa: UP015
        configs = json.load(f)
    return configs

def task_config_validator(task_config: dict[str, Any]) -> bool:
    # Access the attributes
    command = task_config.get('intent')

    if not command:
        raise ValueError("Intent is missing in the task config file. Without it the task cannot be run.")

    return True

def get_formatted_current_timestamp(format: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Get the current timestamp in the specified format.

    Args:
        format (str, optional): The format of the timestamp. Defaults to "%Y-%m-%d %H:%M:%S".

    Returns:
        str: The current timestamp in the specified format.
    """
    # Get the current time
    current_time = datetime.now()

    # Format the timestamp as a human-readable string
    timestamp_str = current_time.strftime(format)
    return timestamp_str


# nltk.download('punkt') # type: ignore

TEST_TASKS = os.path.join(PROJECT_TEST_ROOT, 'tasks')
TEST_LOGS = os.path.join(PROJECT_TEST_ROOT, 'logs')
TEST_RESULTS = os.path.join(PROJECT_TEST_ROOT, 'results')

last_agent_response = ""

def check_top_level_test_folders():
    if not os.path.exists(TEST_LOGS):
        os.makedirs(TEST_LOGS)
        logger.info(f"Created log folder at: {TEST_LOGS}")

    if not os.path.exists(TEST_RESULTS):
        os.makedirs(TEST_RESULTS)
        logger.info(f"Created scores folder at: {TEST_RESULTS}")

def create_test_results_id(test_results_id: str|None, test_file: str) -> str:
    prefix = "test_results_for_"
    if test_results_id:
        return f"{prefix}{test_results_id}"
    test_file_base = os.path.basename(test_file)
    test_file_name = os.path.splitext(test_file_base)[0]

    return f"{prefix}{test_file_name}"

# def create_task_log_folders(task_id: str, test_results_id: str):
#     task_log_dir = os.path.join(TEST_LOGS, f"{test_results_id}", f'logs_for_task_{task_id}')
#     task_screenshots_dir = os.path.join(task_log_dir, 'snapshots')
#     if not os.path.exists(task_log_dir):
#         os.makedirs(task_log_dir)
#         logger.info(f"Created log dir for task {task_id} at: {task_log_dir}")
#     if not os.path.exists(task_screenshots_dir):
#         os.makedirs(task_screenshots_dir)
#         logger.info(f"Created screenshots dir for task {task_id} at: {task_screenshots_dir}")

#     return {"task_log_folder": task_log_dir, "task_screenshots_folder": task_screenshots_dir}

def create_task_log_folders(base_dir, task_id: str):
    task_dir = os.path.join(base_dir, f'{task_id}')
    task_log_dir = os.path.join(task_dir, 'log')
    task_screenshots_dir = os.path.join(task_dir, 'trajectory')
    if not os.path.exists(task_dir):
        os.makedirs(task_dir)
        logger.info(f"Created log dir for task {task_id} at: {task_dir}")
    if not os.path.exists(task_screenshots_dir):
        os.makedirs(task_screenshots_dir)
        logger.info(f"Created screenshots dir for task {task_id} at: {task_screenshots_dir}")
    if not os.path.exists(task_log_dir):
        os.makedirs(task_log_dir)

    return {"task_folder": task_dir, "task_screenshots_folder": task_screenshots_dir, "task_log_folder": task_log_dir}

def create_results_dir(test_file: str, test_results_id: str|None) -> str:
    results_dir = ""
    if test_results_id:
        results_dir = os.path.join(TEST_RESULTS, f"results_for_{test_results_id}")
    else:
        test_file_base = os.path.basename(test_file)
        test_file_name = os.path.splitext(test_file_base)[0]
        results_dir = os.path.join(TEST_RESULTS, f"results_for_test_file_{test_file_name}")

    if not os.path.exists(results_dir):
        os.makedirs(results_dir)
        logger.info(f"Created results directory: {results_dir}")

    return results_dir


def dump_log(task_id: str, messages_str_keys: dict[str, str], logs_dir: str):
    file_name = os.path.join(logs_dir, f'execution_logs_{task_id}.json')
    with open(file_name, 'w',  encoding='utf-8') as f:
            json.dump(messages_str_keys, f, ensure_ascii=False, indent=4)


def save_test_results(test_results: list[dict[str, str | int | float | None]], test_results_id: str):
    file_name = os.path.join(TEST_RESULTS, f'test_results_{test_results_id}.json')
    with open(file_name, 'w',  encoding='utf-8') as f:
        json.dump(test_results, f, ensure_ascii=False, indent=4)
    logger.info(f"Test results dumped to: {file_name}")


def save_individual_test_result(test_result: dict[str, str | int | float | None], results_dir: str):
    task_id = test_result["task_id"]
    # file_name = os.path.join(results_dir, f'test_result_{task_id}.json')
    file_name = os.path.join(results_dir, f'result.json')
    with open(file_name, 'w',  encoding='utf-8') as f:
        json.dump(test_result, f, ensure_ascii=False, indent=4)
    logger.info(f"Test result for task {task_id} dumped to: {file_name}")


def extract_last_response(messages: list[dict[str, Any]]) -> str:
    """Extract the last response message from chat history."""
    try:
        # Iterate over the messages in reverse order
        for message in reversed(messages):
            if message and 'content' in message:
                content=message.get('content', "")
                content_json = parse_response(content)
                final_answer = content_json.get('final_response', None)
                if final_answer:
                    return final_answer
        return ""
    except:
        logger.error("Error extracting last response from chat history.")
        return ""


def print_progress_bar(current: int, total: int, bar_length: int = 50) -> None:
    """
    Prints a progress bar to the console.

    Parameters:
    - current (int): The current progress of the task.
    - total (int): The total number of tasks to complete.
    - bar_length (int): The character length of the progress bar (default is 50).

    This function dynamically updates a single line in the console to reflect current progress.

    """
    percent = float(current) * 100 / total
    arrow = '-' * int(percent/100 * bar_length - 1) + '>'
    spaces = ' ' * (bar_length - len(arrow))

    print(f'\rProgress: [{arrow}{spaces}] {current}/{total} ({percent:.2f}%)', end='')

def determine_status_and_color(score: float) -> tuple[str, str]:
    """
    Determines the status and color for a test result based on the score.

    Parameters:
    - score (float): The score of the test task, indicating success (1), failure (0), or skip (-0.1).

    Returns:
    - tuple[str, str]: A tuple containing the status ('Pass', 'Fail', or 'Skip') and the corresponding color ('green', 'red', or 'yellow').

    """
    if score == 1:
        return 'Pass', 'green'
    elif score < 0:
        return 'Skip', 'yellow'
    else:
        return 'Fail', 'red'


def print_test_result(task_result: dict[str, str | int | float | None], index: int, total: int) -> None:
    """
    Prints the result of a single test task in a tabulated format.

    Parameters:
    - task_result (dict): A dictionary containing the task's evaluation results, including task ID, intent, score, and total command time.
    - index (int): The current index of the test in the sequence of all tests being run.
    - total (int): The total number of tests to be run.

    The function determines the test status (Pass/Fail) based on the 'score' key in task_result and prints the result with colored status.

    """
    status, color = determine_status_and_color(task_result['score']) # type: ignore

    cost = task_result.get("compute_cost", None)
    total_cost = None if cost is None else round(cost.get("cost", -1), 4)  # type: ignore
    total_tokens = None if cost is None else cost.get("total_tokens", -1)  # type: ignore
    result_table = [  # type: ignore
        ['Test Index', 'Task ID', 'Intent', 'Status', 'Time Taken (s)', 'Total Tokens', 'Total Cost ($)'],
        [index, task_result['task_id'], task_result['intent'], colored(status, color), round(task_result['tct'], 2), total_tokens, total_cost]  # type: ignore
    ]
    print('\n' + tabulate(result_table, headers='firstrow', tablefmt='grid')) # type: ignore


def get_command_exec_cost(command_exec_result: ChatResult):
    output: dict[str, Any] = {}
    try:
        cost = command_exec_result.cost # type: ignore
        usage: dict[str, Any] = None
        if "usage_including_cached_inference" in cost:
            usage: dict[str, Any] = cost["usage_including_cached_inference"]
        elif "usage_excluding_cached_inference" in cost:
            usage: dict[str, Any] = cost["usage_excluding_cached_inference"]
        else:
            raise ValueError("Cost not found in the command execution result.")
        print("Usage: ", usage)

        for key in usage.keys():
            if isinstance(usage[key], dict) and "prompt_tokens" in usage[key]:
                output["cost"] = usage[key]["cost"]
                output["prompt_tokens"] = usage[key]["prompt_tokens"]
                output["completion_tokens"] = usage[key]["completion_tokens"]
                output["total_tokens"] = usage[key]["total_tokens"]
    except Exception as e:
        logger.debug(f"Error getting command execution cost: {e}")
    return output

# def execute_single_task(task_config: dict[str, Any], browser_manager: PlaywrightManager, ag: AutogenWrapper, page: Page, logs_dir: str) -> dict[str, Any]:
def execute_single_task(json_item: dict[str, Any], browser_manager: PlaywrightManager, ag: AutogenWrapper, task_dir: str, task_log_dir: str) -> dict[str, Any]:
    """
    Executes a single test task based on a specified task configuration and evaluates its performance.

    Parameters:
    - task_config (dict): The task configuration dictionary containing all necessary parameters for the task.
    - browser_manager (PlaywrightManager): The manager handling browser interactions, responsible for page navigation and control.
    - ag (AutogenWrapper): The automation generator wrapper that processes commands and interacts with the web page.
    - page (Page): The Playwright page object representing the browser tab where the task is executed.

    Returns:
    - dict: A dictionary containing the task's evaluation results, including task ID, intent, score, total command time (tct),
            the last statement from the chat agent, and the last URL accessed during the task.
    """
    command = ""
    start_url = None
    task_id = None

    start_ts = get_formatted_current_timestamp()

    # task_config_validator(task_config)
    # command: str = task_config.get('intent', "")
    # task_id = task_config.get('task_id')
    # task_index = task_config.get('task_index')
    # start_url = task_config.get('start_url')
    command: str = json_item.get('confirmed_task', "")
    task_id = json_item.get('task_id', "")
    task_index = json_item.get('task_index', "")
    start_url = json_item.get('website', "")
    logger.info(f"Intent: {command}, Task ID: {task_id}")

    # if start_url:
    #     page.goto(start_url, wait_until='load', timeout=30000)
    browser_manager.open_page(start_url)
    
    # 开始监听
    browser_manager._request_collector.clear()
    len_request = len(browser_manager._request_collector.requests)
    print(f"request个数：{len_request}")
    if len_request != 0:
        exit()

    browser_manager._page.on("request", browser_manager._request_collector.handle_request)

    # 处理任务
    start_time = time.time()
    current_url = browser_manager.get_current_url()
    command_exec_result = ag.process_command(command, current_url)
    end_time = time.time()

    # 保存请求捕获结果
    save_result_path = f"{task_dir}/capture.json"
    request_count = browser_manager._request_collector.save_results(save_result_path)
    logger.info(f"保存了 {request_count} 个请求到 {save_result_path}")

    evaluator_result: dict[str, float | str] = {}
    last_agent_response: str = ""
    command_cost: dict[str, Any] = {}
    single_task_result: dict[str, Any] = {}
    try:
        # single_task_result = {
        #     "task_id": task_id,
        #     "task_index": task_index,
        #     "start_url": start_url,
        #     "intent": str(command),
        #     # "last_url": page.url,
        #     "last_url": browser_manager.get_current_url(),
        #     "tct": end_time - start_time,
        #     "start_ts": start_ts,
        #     "completion_ts": get_formatted_current_timestamp()
        # }
        single_task_result = {
            "task_id": task_id,
            "task": command,
            "key_points": json_item.get('keytra', ""),
            "website": start_url,
            "task_index": task_index,
            "status": "SUCCESS",
            "reference_length": json_item.get('reference_length'),
            "urls": json_item.get('urls', [])
        }

        agent_name: str = "planner_agent" if ag.agents_map is not None and "planner_agent" in ag.agents_map else "browser_nav_agent"

        # command_cost = get_command_exec_cost(command_exec_result) # type: ignore
        # print(f"Command cost: {command_cost}")
        # single_task_result["compute_cost"] = command_cost

        logger.info(f"Command \"{command}\" took: {round(end_time - start_time, 2)} seconds.")
        logger.info(f"Task {task_id} completed.")

        messages = ag.agents_map[agent_name].chat_messages # type: ignore
        messages_str_keys = {str(key): value for key, value in messages.items()} # type: ignore
        agent_key = list(messages.keys())[0] # type: ignore
        last_agent_response = extract_last_response(messages[agent_key]) # type: ignore

        # dump_log(str(task_id), messages_str_keys, logs_dir)
        dump_log(str(task_id), messages_str_keys, task_log_dir)

        single_task_result["last_statement"] = last_agent_response

        # evaluator = evaluator_router(task_config)
        # cdp_session = page.context.new_cdp_session(page)
        # evaluator_result = evaluator(
        #     task_config=task_config,
        #     page=page,
        #     client=cdp_session,
        #     answer=last_agent_response,
        # )

        # single_task_result["score"] = evaluator_result["score"]
        # single_task_result["reason"] = evaluator_result["reason"]

    except Exception as e:
        logger.error(f"Error getting command cost: {e}")
        command_cost = {"cost": -1, "total_tokens": -1}
        single_task_result["compute_cost"] = command_cost
        single_task_result["error"] = str(e)

    return single_task_result


def safe_remove_task_dir(task_dir):
    lock_file = f"{task_dir}.lock"
    if os.path.exists(task_dir):
        try:
            shutil.rmtree(task_dir)
        except Exception as e:
            print(f"Error removing task directory {task_dir}: {e}")
    if os.path.exists(lock_file):
        try:
            os.remove(lock_file)
        except Exception as e:
            print(f"Warning: Failed to remove lock file {lock_file}: {e}")


import os
import json
import time
import logging
import multiprocessing as mp
from multiprocessing import Manager
import numpy as np
from typing import List, Dict, Any
import shutil

def run_tests_multiprocess(args) -> list[dict[str, Any]]:
    """多进程版本的测试运行函数"""
    
    # ==================== 从 args 读取配置 ====================
    scribe_json_path = args.task_file
    file_path = args.llm_config
    
    BASE_DIR = args.output_dir
    os.makedirs(BASE_DIR, exist_ok=True)
    
    LOG_DIR = f"{BASE_DIR}_logs"
    os.makedirs(LOG_DIR, exist_ok=True)
    
    PORT_LIST = args.ports
    WORKERS = len(PORT_LIST)
    
    use_keypoints = args.use_keypoints
    take_screenshots = args.take_screenshots
    wait_time_non_headless = args.wait_time

    BASE_URL = args.base_url

    # 加载配置
    with open(scribe_json_path, 'r', encoding='utf-8') as f:
        scribe_json_items = json.load(f)
    
    with open(file_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    # 如果指定了 llm-config-key，从 JSON 中提取对应子配置
    if args.llm_config_key:
        if args.llm_config_key not in config:
            raise KeyError(f"Key '{args.llm_config_key}' not found in {file_path}. Available keys: {list(config.keys())}")
        config = config[args.llm_config_key]

    # ==================== 筛选任务（✅ 修改这里）====================
    task_indices = []
    for json_item_i, json_item in enumerate(scribe_json_items):
        # 只处理指定数量的任务
        if args.max_tasks > 0 and json_item_i >= args.max_tasks:
            break

        task_id = json_item["task_id"]
        task_idx = json_item["task_index"]
        website = json_item.get("website", "").strip()
        
        if not website.startswith("http"):
            website = "https://" + website

        dir_name = f"{task_idx}_{task_id}"
        
        # ✅ 只构建路径，不调用 create_task_log_folders
        task_dir = os.path.join(BASE_DIR, dir_name)
        result_json_path = os.path.join(task_dir, "result.json")
        capture_json_path = os.path.join(task_dir, "capture.json")
        
        # 跳过已完成的任务
        if os.path.exists(result_json_path) and os.path.exists(capture_json_path):
            image_name_list = os.listdir(f'{task_dir}/trajectory')
            image_file_count = len(image_name_list)
            # print(image_name_list)
            # exit()
            if "_final" in image_name_list[-1]:
                print(f"跳过已完成任务: {dir_name}")  # ✅ 可选：打印跳过信息
                continue

            print(f"清理不完整任务: {dir_name}")  # ✅ 可选：打印清理信息
            safe_remove_task_dir(task_dir)
        
        # 清理不完整的任务目录
        if os.path.exists(task_dir):
            print(f"清理不完整任务: {dir_name}")  # ✅ 可选：打印清理信息
            safe_remove_task_dir(task_dir)
        
        task_indices.append(json_item_i)
    
    total_tasks = len(task_indices)
    print(f"总任务数: {total_tasks}, 使用 {WORKERS} 个进程")
    print(f"已跳过: {len(scribe_json_items) - len(task_indices)} 个已完成任务")  # ✅ 打印统计
    
    if total_tasks == 0:
        print("没有需要执行的任务！")
        return []
    
    # 将任务分片
    shards = np.array_split(task_indices, WORKERS)
    shards = [shard.tolist() for shard in shards]
    
    # 使用 Manager 创建共享对象
    manager = mp.Manager()
    results_queue = manager.Queue()
    processing_tasks = manager.dict()
    completed_tasks = manager.dict()
    
    # ==================== Worker 函数 ====================
    def worker(
        worker_id: int, 
        worker_indices: List[int], 
        config_dict: dict,
        json_items: list,          # ✅ 传入数据
        base_url: str,             # ✅ 传入 BASE_URL
        port_list: list,           # ✅ 传入 PORT_LIST
        base_dir: str,             # ✅ 传入 BASE_DIR
        log_dir: str,              # ✅ 传入 LOG_DIR
        total: int                 # ✅ 传入 total_tasks
    ):
        """每个进程的工作函数"""
        
        # ✅ 设置日志（目录已在主进程创建）
        logger = logging.getLogger(f"worker_{worker_id}")
        logger.handlers.clear()  # 清除已有的 handler
        handler = logging.FileHandler(
            os.path.join(log_dir, f"worker_{worker_id}.log"), 
            encoding='utf-8'
        )
        handler.setFormatter(logging.Formatter(
            f"%(asctime)s - %(levelname)s - [Worker-{worker_id}] - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        ))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.info(f"进程启动，PID: {os.getpid()}")
        
        # ✅ 从参数获取端口
        cdp_port = port_list[worker_id]
        cdp_url = f"{base_url}:{cdp_port}"
        
        browser_manager = None
        ag = None
        
        try:
            # ✅ 在子进程中导入（避免序列化问题）
            import ae.core.playwright_manager as browserManager
            from ae.core.autogen_wrapper import AutogenWrapper
            from ae.core.agents_llm_config import AgentsLLMConfig
            
            # 创建 LLM 配置
            llm_config = AgentsLLMConfig(llm_config=config_dict)
            
            # 创建浏览器管理器
            browser_manager = browserManager.PlaywrightManager(
                cdp_url=cdp_url,
                headless=False,
                take_screenshots=take_screenshots
            )
            browser_manager.initialize()
            logger.info(f"浏览器管理器初始化完成，端口: {cdp_port}")
            
            # 创建 AutogenWrapper
            ag = AutogenWrapper.create(
                llm_config.get_planner_agent_config(), 
                llm_config.get_browser_nav_agent_config(),
                use_keypoints=use_keypoints
            )
            logger.info("AutogenWrapper 创建完成")
            
            # 获取起始页
            page = browser_manager.get_current_page()
            
            completed_count = 0
            
            # ✅ 使用传入的数据
            for json_item_i in worker_indices:
                try:
                    json_item = json_items[json_item_i]  # ✅ 使用参数中的数据
                    task_id = json_item["task_id"]
                    task_idx = json_item["task_index"]
                    website = json_item.get("website", "")
                    key_points = json_item.get("keytra", "")
                    
                    # 检查是否已被其他进程处理
                    if task_id in completed_tasks or task_id in processing_tasks:
                        logger.info(f"任务 {task_id} 已被处理，跳过")
                        continue
                    
                    # 标记为处理中
                    processing_tasks[task_id] = worker_id
                    
                    dir_name = f"{task_idx}_{task_id}"
                    log_folders = create_task_log_folders(base_dir, dir_name)
                    task_dir = log_folders["task_folder"]
                    save_traj_dir = log_folders["task_screenshots_folder"]
                    task_log_dir = log_folders["task_log_folder"]
                    
                    # 创建目录
                    os.makedirs(task_dir, exist_ok=True)
                    os.makedirs(save_traj_dir, exist_ok=True)
                    os.makedirs(task_log_dir, exist_ok=True)
                    
                    # 设置日志目录
                    ag.set_chat_logs_dir(task_log_dir)
                    
                    # 重置截图计数器
                    browser_manager._screenshot_counter = 0
                    browser_manager.set_take_screenshots(take_screenshots)
                    if take_screenshots:
                        browser_manager.set_screenshots_dir(save_traj_dir)
                    
                    # 重置关键路径
                    if use_keypoints:
                        ag.keypoints = key_points
                        if ag.keypoints != key_points:
                            print("关键路径重置失败")
                            exit()

                    logger.info(f"开始执行任务 {json_item_i + 1}/{total}: {task_id}")  # ✅ 使用参数中的 total
                    print(f"[Worker {worker_id}] 处理任务 {json_item_i + 1}/{total}: {task_id}")
                    
                    # 执行任务
                    task_result = execute_single_task(
                        json_item, 
                        browser_manager, 
                        ag, 
                        task_dir, 
                        task_log_dir
                    )
                    
                    # 保存结果
                    save_individual_test_result(task_result, task_dir)
                    
                    # 将结果放入队列
                    results_queue.put(task_result)
                    
                    # 截图
                    browser_manager.take_screenshots("final", None)
                    
                    # 清理页面
                    browser_manager.close_except_specified_tab(page)
                    
                    # 标记为已完成
                    completed_tasks[task_id] = worker_id
                    processing_tasks.pop(task_id, None)
                    
                    completed_count += 1
                    logger.info(f"任务 {task_id} 完成 ({completed_count}/{len(worker_indices)})")
                    
                    # 等待（非headless模式）
                    if not browser_manager.isheadless:
                        time.sleep(wait_time_non_headless)
                
                except Exception as e:
                    logger.error(f"执行任务时出错: {e}", exc_info=True)
                    if 'task_id' in locals():
                        processing_tasks.pop(task_id, None)
                    continue
            
            logger.info(f"进程 {worker_id} 完成所有任务，共完成 {completed_count} 个")
        
        except Exception as e:
            logger.error(f"进程 {worker_id} 发生严重错误: {e}", exc_info=True)
        
        finally:
            try:
                if browser_manager:
                    browser_manager.stop_playwright()
                logger.info(f"进程 {worker_id} 资源清理完成")
            except Exception as e:
                logger.error(f"进程 {worker_id} 清理失败: {e}")
    
    # ==================== 启动多进程 ====================
    processes = []
    for worker_id in range(WORKERS):
        if not shards[worker_id]:
            print(f"Worker {worker_id} 没有分配到任务，跳过")
            continue
        
        # ✅ 将所有需要的数据作为参数传入
        proc = mp.Process(
            target=worker,
            args=(
                worker_id, 
                shards[worker_id], 
                config,
                scribe_json_items,    # ✅ 传入数据
                BASE_URL,             # ✅ 传入 BASE_URL
                PORT_LIST,            # ✅ 传入 PORT_LIST
                BASE_DIR,             # ✅ 传入 BASE_DIR
                LOG_DIR,              # ✅ 传入 LOG_DIR
                total_tasks           # ✅ 传入 total_tasks
            )
        )
        proc.start()
        processes.append(proc)
        print(f"Worker {worker_id} 已启动，PID: {proc.pid}, 分配任务数: {len(shards[worker_id])}")
        time.sleep(3)
    
    # ==================== 监控进程状态 ====================
    print("\n开始监控进程状态...")
    try:
        while any(p.is_alive() for p in processes):
            time.sleep(5)
            alive_count = sum(1 for p in processes if p.is_alive())
            completed_count = len(completed_tasks)
            processing_count = len(processing_tasks)
            print(f"[状态] 活跃进程: {alive_count}/{len(processes)}, "
                  f"已完成: {completed_count}/{total_tasks}, "
                  f"处理中: {processing_count}")
    
    except KeyboardInterrupt:
        print("\n接收到中断信号，正在终止所有进程...")
        for proc in processes:
            proc.terminate()
        for proc in processes:
            proc.join(timeout=5)
            if proc.is_alive():
                proc.kill()
    
    # 等待所有进程结束
    for proc in processes:
        proc.join()
    
    print(f"\n所有进程已完成。共完成任务: {len(completed_tasks)}/{total_tasks}")
    
    # ==================== 收集结果 ====================
    test_results = []
    while not results_queue.empty():
        try:
            result = results_queue.get_nowait()
            test_results.append(result)
        except:
            break
    
    print(f"收集到 {len(test_results)} 个结果")
    
    # 保存汇总报告
    summary = {
        "total_tasks": total_tasks,
        "completed_tasks": len(completed_tasks),
        "completion_rate": f"{len(completed_tasks)/total_tasks*100:.2f}%" if total_tasks > 0 else "0%",
        "completed_task_ids": list(completed_tasks.keys()),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    summary_file = f"{BASE_DIR}/summary.json"
    with open(summary_file, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=4, ensure_ascii=False)
    print(f"汇总报告已保存到: {summary_file}")
    
    return test_results


def parse_args():
    import argparse
    parser = argparse.ArgumentParser(description="Agent-E Web Agent 多进程评测")

    # 必需参数
    parser.add_argument("--task-file", required=True,
                        help="任务 JSON 文件路径")
    parser.add_argument("--output-dir", required=True,
                        help="结果输出目录")
    parser.add_argument("--base-url", required=True,
                        help="浏览器服务基础 URL")
    parser.add_argument("--llm-config", required=True,
                        help="LLM 配置 JSON 文件路径 (agents_llm_config.json)")
    parser.add_argument("--llm-config-key", default=None,
                        help="LLM 配置 JSON 中的顶层 key (如 openai_gpt, mistral-large-agente)")

    # 浏览器端口
    parser.add_argument("--ports", type=int, nargs="+",
                        default=[9223, 9225, 9227, 9229, 9231, 9233, 9235, 9237,
                                 9239, 9241, 9243, 9245, 9247, 9249, 9251, 9253],
                        help="浏览器端口列表，worker 数量等于端口数量")

    # 任务控制
    parser.add_argument("--max-tasks", type=int, default=0,
                        help="最大任务数，0 表示不限制 (默认: 0)")
    parser.add_argument("--use-keypoints", action="store_true",
                        help="是否使用关键路径提示")
    parser.add_argument("--take-screenshots", action="store_true", default=True,
                        help="是否保存截图 (默认: True)")
    parser.add_argument("--no-screenshots", dest="take_screenshots", action="store_false",
                        help="不保存截图")
    parser.add_argument("--wait-time", type=int, default=5,
                        help="非 headless 模式下每个任务间的等待时间 (默认: 5)")

    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    
    results = run_tests_multiprocess(args)
    
    print(f"\n测试完成，共 {len(results)} 个结果")