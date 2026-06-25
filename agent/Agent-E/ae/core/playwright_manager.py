# import json
# import re
# import os
# import time
# import random
# import platform
# import logging
# from playwright.sync_api import sync_playwright, Playwright, BrowserContext, Page, CDPSession
# import threading

# # 设置日志
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
# logger = logging.getLogger("PlaywrightManager")

# class RequestCollector:
#     """请求收集器"""
#     def __init__(self):
#         self.requests = []
    
#     def clear(self):
#         self.requests = []
    
#     def handle_request(self, request):
#         req_data = {
#             "timestamp": time.time(),
#             "url": request.url,
#             "method": request.method,
#             "headers": dict(request.headers),
#             "resource_type": request.resource_type,
#             "post_data": None,
#             "json_data": None
#         }
        
#         if request.resource_type in ["xhr", "fetch"]:
#             raw = request.post_data_buffer
#             if raw:
#                 req_data["raw_post_data"] = raw.hex()
#                 try:
#                     text = raw.decode("utf-8")
#                     req_data["post_data"] = text
#                     try:
#                         req_data["json_data"] = json.loads(text)
#                     except:
#                         pass
#                 except UnicodeDecodeError:
#                     pass
#             self.requests.append(req_data)
    
#     def save_results(self, save_result_path="capture.json"):
#         output = {
#             "capture_time": time.strftime("%Y-%m-%d %H:%M:%S"),
#             "total_requests": len(self.requests),
#             "all_requests": self.requests
#         }
#         with open(save_result_path, "w", encoding="utf-8") as f:
#             json.dump(output, f, indent=4, ensure_ascii=False)
#         return len(self.requests)


# class PlaywrightManager:
#     """
#     基于 Playwright 和 CDP 的浏览器自动化管理器
#     """
#     _instance = None
#     _lock = threading.Lock()  # 确保线程安全

#     def __new__(cls, *args, **kwargs):
#         if not cls._instance:
#             with cls._lock:
#                 if not cls._instance:
#                     cls._instance = super(PlaywrightManager, cls).__new__(cls)
#         return cls._instance

#     def __init__(self, cdp_url: str = None, width: int = 1280, height: int = 720):
#         # 如果已初始化，直接返回
#         if hasattr(self, "_initialized") and self._initialized:
#             if cdp_url and cdp_url != self.cdp_url:
#                 logger.warning(
#                     f"⚠️ 单例已存在 (cdp_url={self.cdp_url})，"
#                     f"忽略新参数 ({cdp_url})"
#                 )
#             return
        
#         # 首次初始化时必须提供 cdp_url
#         if cdp_url is None:
#             raise ValueError(
#                 "❌ 首次初始化必须提供 cdp_url 参数\n"
#                 "正确用法: PlaywrightManager(cdp_url='http://localhost:9222')"
#             )
#             exit()
        
#         self.cdp_url = cdp_url
#         self.window_width = width
#         self.window_height = height
#         self.playwright = None
#         self.browser = None
#         self.context = None
#         self._initialized = True
#         logger.info(f"✅ 初始化完成: {cdp_url}")


#     def start(self):
#         """启动 Playwright 并连接到远程浏览器"""
#         # 检查是否已经启动，避免重复启动
#         if self.playwright is not None:
#             return

#         self.playwright = sync_playwright().start()
#         try:
#             logger.info(f"正在连接 CDP: {self.cdp_url}")
#             self.browser = self.playwright.chromium.connect_over_cdp(self.cdp_url)
            
#             # 获取或创建上下文
#             if self.browser.contexts:
#                 self.context = self.browser.contexts[0]
#             else:
#                 self.context = self.browser.new_context()
                
#         except Exception as e:
#             logger.error(f"初始化连接失败: {e}")
#             self.close()
#             raise e

#     def close(self):
#         """释放资源并重置单例状态"""
#         # 1. 安全关闭资源
#         try:
#             if self.context: self.context.close()
#             if self.browser: self.browser.close()
#             if self.playwright: self.playwright.stop()
#         except Exception as e:
#             logger.error(f"关闭资源时出错: {e}")
#         finally:
#             # 2. 将内部指针置空 (供 start() 判断使用)
#             self.context = None
#             self.browser = None
#             self.playwright = None
#             self.client = None
            
#             # 3. 重置初始化标记 (允许 __init__ 再次运行)
#             if hasattr(self, "_initialized"):
#                 self._initialized = False

#             # 4. 【关键】销毁单例引用 (允许 __new__ 创建新实例)
#             PlaywrightManager._instance = None
            
#             logger.info("PlaywrightManager 已关闭并销毁单例")

#     def _extract_between_keywords(self, text, start_key, end_key):
#         pattern = re.compile(f'{re.escape(start_key)}(.*?){re.escape(end_key)}', re.DOTALL)
#         matches = pattern.findall(text)
#         return [match.strip() for match in matches]

#     def open_page(self, target_url: str, max_retries: int = 3):
#         """打开网页并处理页面清理"""
#         if target_url:
#             target_url = target_url.strip()
#             if not target_url.startswith("http"):
#                 target_url = "https://" + target_url

#         logger.info(f"🌐 打开页面: {target_url}")
        
#         retry_count = 0
#         while retry_count < max_retries:
#             # 1. 清理多余页面
#             try:
#                 if len(self.context.pages) >= 3:
#                     pages_to_close = self.context.pages[:-1]
#                     for old_page in pages_to_close:
#                         try:
#                             old_page.evaluate("() => { window.stop(); }")
#                             old_page.close(run_before_unload=False)
#                         except Exception:
#                             print(f"关闭失败: {e}")
#             except Exception as e:
#                 logger.warning(f"清理页面警告: {e}")

#             # 2. 创建或获取新页面
#             try:
#                 if self.context and len(self.context.pages) > 0:
#                     self.page = self.context.new_page()
#                     break # 成功
                
#                 # 如果失败，尝试重连逻辑
#                 logger.warning(f"页面异常，尝试重连 ({retry_count + 1}/{max_retries})")
#                 self.close()
#                 time.sleep(2)
#                 self.start() # 重新连接
#                 self.page = self.context.new_page()
#                 break
#             except Exception as e:
#                 logger.error(f"创建页面失败: {e}")
#                 retry_count += 1
#                 if retry_count >= max_retries:
#                     raise Exception("无法创建页面，已达最大重试次数")

#         # 3. 建立 CDP Session
#         try:
#             self.client = self.page.context.new_cdp_session(self.page)
#         except Exception as e:
#             logger.error(f"CDP Session 创建失败: {e}")

#         # 4. 设置视口
#         self._setup_viewport()

#         # 5. 禁用缓存 (可选)
#         self.page.route('**/*', self._prevent_cache_route)

#         # 6. 导航
#         try:
#             self.page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
#             self.page.wait_for_timeout(2000)
#         except Exception:
#             try:
#                 self.page.goto(target_url, wait_until="commit", timeout=30000)
#             except Exception as e:
#                 logger.error(f"导航异常(但可能已加载): {e}")

#         return self.page

#     def _setup_viewport(self):
#         try:
#             size = self.page.evaluate("""() => {
#                 return {
#                     width: window.outerWidth || 1920,
#                     height: window.outerHeight || 1080
#                 }
#             }""")
#             self.window_width = size['width']
#             self.window_height = size['height']
#             self.page.set_viewport_size({"width": self.window_width, "height": self.window_height})
#         except Exception:
#             self.page.set_viewport_size({"width": 1920, "height": 1080})

#     def _prevent_cache_route(self, route):
#         try:
#             headers = route.request.headers.copy()
#             headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
#             route.continue_(headers=headers)
#         except:
#             route.continue_()

#     def save_screenshot(self, save_path, timeout_ms=5000):
#         try:
#             os.makedirs(os.path.dirname(save_path), exist_ok=True)
#             self.page.screenshot(path=save_path, full_page=False, timeout=timeout_ms)
#             logger.info(f"### 截图保存至: {save_path}")
#             return True
#         except Exception as e:
#             logger.error(f"### 截图保存失败: {e}")
#             return False

#     # ================= CDP 动作封装 =================

#     def _cdp_mouse_move(self, end_x, end_y, steps=20):
#         """模拟真实的鼠标移动轨迹"""
#         try:
#             # 尝试获取当前位置
#             pos = self.client.send("Runtime.evaluate", {
#                 "expression": "({x: window.mouseX || 0, y: window.mouseY || 0})",
#                 "returnByValue": True
#             })
#             start_x = pos["result"]["value"]["x"]
#             start_y = pos["result"]["value"]["y"]
#         except:
#             start_x, start_y = 0, 0

#         delta_x = (end_x - start_x) / steps
#         delta_y = (end_y - start_y) / steps

#         for step in range(1, steps + 1):
#             self.client.send("Input.dispatchMouseEvent", {
#                 "type": "mouseMoved", 
#                 "x": start_x + delta_x * step, 
#                 "y": start_y + delta_y * step
#             })
#             time.sleep(0.005) # 极短延迟

#         # 更新 JS 记录的位置
#         self.client.send("Runtime.evaluate", {
#             "expression": f"window.mouseX = {end_x}; window.mouseY = {end_y};"
#         })

#     def _mouse_up_and_down(self, x, y):
#         # 使用 Playwright 的 click 混合 CDP 移动，效果更稳
#         self.page.mouse.click(x, y)

#     def click(self, x, y, time_wait=1000):
#         self._cdp_mouse_move(x, y, steps=15)
#         self._mouse_up_and_down(x, y)
#         self.page.wait_for_timeout(time_wait)

#     def double_click(self, x, y, time_wait=1000):
#         self._cdp_mouse_move(x, y, steps=15)
#         wait_t = random.randint(200, 400)
#         self._mouse_up_and_down(x, y) # Click 1
#         self.page.wait_for_timeout(wait_t)
#         self._mouse_up_and_down(x, y) # Click 2
#         self.page.wait_for_timeout(time_wait)

#     def type_text(self, x, y, content, time_wait=500):
#         """点击并输入（含全选删除逻辑）"""
#         self.click(x, y, time_wait)
#         self.page.wait_for_timeout(random.randint(100, 200))
        
#         # 全选删除
#         modifier = "Meta" if platform.system() == "Darwin" else "Control"
#         self.page.keyboard.press(f"{modifier}+a")
#         self.page.keyboard.press("Backspace")
#         self.page.wait_for_timeout(500)
        
#         # 输入
#         for char in content:
#             self.page.keyboard.type(char, delay=random.randint(10, 50))
        
#         self.page.wait_for_timeout(1000)

#     def hotkey(self, key_value):
#         if "enter" in key_value.lower():
#             self.page.keyboard.press("Enter")
#         else:
#             # 简单处理，可扩展
#             self.page.keyboard.press(key_value)
#         self.page.wait_for_timeout(1000)

#     def scroll(self, delta_x, delta_y):
#         center_x = self.window_width / 2
#         center_y = self.window_height / 2
#         self.client.send("Input.dispatchMouseEvent", {
#             "type": "mouseWheel",
#             "x": center_x, "y": center_y,
#             "deltaX": delta_x,
#             "deltaY": delta_y
#         })

#     def scroll_menu(self, x, y, delta_x, delta_y):
#         self._cdp_mouse_move(x, y)
#         self.client.send("Input.dispatchMouseEvent", {
#             "type": "mouseWheel",
#             "x": x, "y": y,
#             "deltaX": delta_x,
#             "deltaY": delta_y
#         })

#     def drag(self, x1, y1, x2, y2, steps=20):
#         self._cdp_mouse_move(x1, y1, steps)
#         self.page.wait_for_timeout(100)
        
#         # 按下
#         self.client.send("Input.dispatchMouseEvent", {
#             "type": "mousePressed", "x": x1, "y": y1, "button": "left", "clickCount": 1
#         })
        
#         # 拖动
#         delta_x = (x2 - x1) / steps
#         delta_y = (y2 - y1) / steps
#         for step in range(1, steps + 1):
#             self.client.send("Input.dispatchMouseEvent", {
#                 "type": "mouseMoved",
#                 "x": x1 + delta_x * step,
#                 "y": y1 + delta_y * step,
#                 "button": "left", "buttons": 1
#             })
#             time.sleep(0.01)
            
#         # 释放
#         self.client.send("Input.dispatchMouseEvent", {
#             "type": "mouseReleased", "x": x2, "y": y2, "button": "left", "clickCount": 1
#         })
#         self.page.wait_for_timeout(1000)

#     # ================= 业务逻辑解析 =================

#     def parse_action(self, action_str: str):
#         """解析指令字符串"""
#         response = action_str.strip()
#         print(f"解析指令: {response}")
#         action = {"name": "Unknown"}

#         try:
#             if "type(content" in response and "start_box" in response:
#                 click_point = self._extract_between_keywords(response, "start_box='(", ")'")[0]
#                 coords = click_point.split(",")
#                 cx, cy = int(coords[0]), int(coords[-1])
                
#                 type_val = self._extract_between_keywords(response, "content='", "', start_box")
#                 if not type_val:
#                     type_val = self._extract_between_keywords(response, "content='", "”, start_box")
                
#                 action = {"name": "ClickAndType", "coordinate": [cx, cy], "value": type_val[0]}

#             elif "click(start_box=" in response:
#                 click_point = self._extract_between_keywords(response, "start_box='(", ")'")[0]
#                 coords = click_point.split(",")
#                 cx, cy = int(coords[0]), int(coords[-1])
#                 action = {"name": "LeftClick", "coordinate": [cx, cy]}
            
#             elif "doubleclick(start_box=" in response:
#                 click_point = self._extract_between_keywords(response, "start_box='(", ")'")[0]
#                 coords = click_point.split(",")
#                 cx, cy = int(coords[0]), int(coords[-1])
#                 action = {"name": "DoubleClick", "coordinate": [cx, cy]}
            
#             elif "scrollmenu(" in response:
#                 # 解析 bbox
#                 click_point = self._extract_between_keywords(response, "start_box='(", ")'")[0]
#                 # 假设格式 (x1,y1),(x2,y2) 比较复杂，这里简化处理逻辑
#                 # ...根据实际需求完善坐标提取...
#                 # 此处为示例占位
#                 action = {"name": "ScrollDownMenu", "coordinate": [500, 500], "bbox": [0,0,100,100]}

#             elif "scrollup" in response: action = {"name": "ScrollUp"}
#             elif "scrolldown" in response: action = {"name": "ScrollDown"}
#             elif "scrollleft" in response: action = {"name": "ScrollLeft"}
#             elif "scrollright" in response: action = {"name": "ScrollRight"}
            
#             elif "hotkey" in response:
#                 key = self._extract_between_keywords(response, "key=\"", "\")")
#                 if not key: key = self._extract_between_keywords(response, "\"", "\"")
#                 action = {"name": "HotKey", "value": key[0].replace(".", "")}
            
#             elif "drag" in response:
#                 # 简化提取逻辑，实际需要 parse bbox
#                 action = {"name": "Drag", "bbox": [100, 100, 200, 200]} # 示例
                
#             elif "wait()" in response: action = {"name": "Wait"}
#             elif "finish()" in response: action = {"name": "Finish"}

#         except Exception as e:
#             logger.error(f"解析错误: {e}")
        
#         return action

#     def execute_action(self, action_str: str, get_table_data_flag: bool = False):
#         """执行动作"""
#         # 1. 解析动作
#         action = self.parse_action(action_str)
#         name = action["name"]
        
#         # 记录旧页面集合，用于检测新页面跳转
#         old_pages = set(self.context.pages)

#         # 2. 执行具体操作
#         if name == "ClickAndType":
#             cx, cy = action["coordinate"]
#             self.type_text(cx, cy, action["value"])
#         elif name == "LeftClick":
#             cx, cy = action["coordinate"]
#             self.click(cx, cy)
#         elif name == "DoubleClick":
#             cx, cy = action["coordinate"]
#             self.double_click(cx, cy)
#         elif name == "HotKey":
#             self.hotkey(action["value"])
#         elif name == "ScrollDown":
#             self.scroll(0, self.window_height - 100)
#         elif name == "ScrollUp":
#             self.scroll(0, -(self.window_height - 100))
#         elif name == "Drag":
#             x1, y1, x2, y2 = action["bbox"]
#             self.drag(x1, y1, x2, y2)
#         elif name == "Wait":
#             self.page.wait_for_timeout(3000)

#         # 3. 处理页面跳转
#         current_pages = set(self.context.pages)
#         new_pages = current_pages - old_pages
        
#         if new_pages:
#             new_page = list(new_pages)[0]
#             logger.info("检测到新标签页，切换焦点...")
            
#             # 关闭除新页面和倒数第二个页面之外的旧页面
#             for p in list(old_pages)[:-1]:
#                 try:
#                     p.close(run_before_unload=False)
#                 except: pass
            
#             self.page = new_page
#             self._setup_viewport()
#             try:
#                 self.client = self.page.context.new_cdp_session(self.page)
#             except: pass

#         # 4. 等待渲染
#         self.wait_for_rendering_complete()

#     def wait_for_rendering_complete(self):
#         """等待页面渲染完成"""
#         try:
#             self.page.wait_for_load_state("load", timeout=10000)
#             self.page.wait_for_load_state("domcontentloaded", timeout=5000)
            
#             # 检查 document.readyState
#             state = self.page.evaluate("() => document.readyState")
#             if state != "complete":
#                 logger.warning(f"页面状态为 {state}")
                
#             # 等待高度不再变化 (简单的防抖动)
#             self.page.evaluate("""() => {
#                 return new Promise(resolve => {
#                     let lastHeight = document.body.scrollHeight;
#                     let checkCount = 0;
#                     const interval = setInterval(() => {
#                         const currentHeight = document.body.scrollHeight;
#                         if (currentHeight === lastHeight || checkCount > 5) {
#                             clearInterval(interval);
#                             resolve();
#                         } else {
#                             lastHeight = currentHeight;
#                             checkCount++;
#                         }
#                     }, 100);
#                 });
#             }""")
#         except Exception as e:
#             logger.warning(f"等待渲染时发生非致命错误: {e}")

#     def get_vimc_elements(self):
#         """提取高亮元素信息"""
#         logger.info("🛠️ 执行 highlight_dom_sync...")
#         try:
#             self.page.evaluate("""() => {
#                 window.__highlight_completed__ = false;
#                 Promise.resolve(window.__highlight_dom_sync__?.())
#                   .then(result => {
#                     window.__highlight_result__ = result;
#                     window.__highlight_completed__ = true;
#                   });
#             }""")
            
#             # 等待完成
#             try:
#                 self.page.wait_for_function("() => window.__highlight_completed__ === true", timeout=5000)
#             except:
#                 return []

#             handle = self.page.evaluate_handle("() => window.__highlight_result__")
#             elements = handle.json_value()
            
#             # 清理
#             self.page.evaluate("() => window.__clear_highlight_dom_sync__?.()")
            
#             # 处理数据格式
#             clean_elements = []
#             if isinstance(elements, dict):
#                 for key, val in elements.items():
#                     if "attributes" in val and "id" in val["attributes"]:
#                         val["attributes"]["attributes_id"] = val["attributes"]["id"]
#                         del val["attributes"]["id"]
#                     clean_elements.append(val)
#             return clean_elements
            
#         except Exception as e:
#             logger.error(f"提取元素失败: {e}")
#             return []

#     # ================= 原生方法 =================
#     def set_take_screenshots(self, take_screenshots: bool):
#         self._take_screenshots = take_screenshots

#     def get_take_screenshots(self):
#         return self._take_screenshots

#     def set_screenshots_dir(self, screenshots_dir: str):
#         self._screenshots_dir = screenshots_dir

#     def get_screenshots_dir(self):
#         return self._screenshots_dir

#     def take_screenshots(self, name: str, page: Page|None, full_page: bool = True, include_timestamp: bool = True,
#                                load_state: str = 'domcontentloaded', take_snapshot_timeout: int = 5*1000):
#         if not self._take_screenshots:
#             return
#         if page is None:
#             page = self.get_current_page()

#         screenshot_name = name

#         if include_timestamp:
#             screenshot_name = f"{int(time.time_ns())}_{screenshot_name}"
#         screenshot_name += ".png"
#         screenshot_path = f"{self.get_screenshots_dir()}/{screenshot_name}"
#         try:
#             page.wait_for_load_state(state=load_state, timeout=take_snapshot_timeout) # type: ignore
#             page.screenshot(path=screenshot_path, full_page=full_page, timeout=take_snapshot_timeout, caret="initial", scale="device")
#             logger.debug(f"Screen shot saved to: {screenshot_path}")
#         except Exception as e:
#             logger.error(f"Failed to take screenshot and save to \"{screenshot_path}\". Error: {e}")

#     def get_current_page(self):
#         return self.page

#     def get_current_url(self) -> str | None:
#         """
#         Get the current URL of current page

#         Returns:
#             str | None: The current URL if any.
#         """
#         try:
#             current_page: Page =self.get_current_page()
#             return current_page.url
#         except Exception:
#             pass
#         return None

#     def highlight_element(self, selector: str, add_highlight: bool):
#         try:
#             page: Page = self.get_current_page()
#             if add_highlight:
#                 # Add the 'agente-ui-automation-highlight' class to the element. This class is used to apply the fading border.
#                 page.eval_on_selector(selector, '''e => {
#                             let originalBorderStyle = e.style.border;
#                             e.classList.add('agente-ui-automation-highlight');
#                             e.addEventListener('animationend', () => {
#                                 e.classList.remove('agente-ui-automation-highlight')
#                             });}''')
#                 logger.debug(f"Applied pulsating border to element with selector {selector} to indicate text entry operation")
#             else:
#                 # Remove the 'agente-ui-automation-highlight' class from the element.
#                 page.eval_on_selector(selector, "e => e.classList.remove('agente-ui-automation-highlight')")
#                 logger.debug(f"Removed pulsating border from element with selector {selector} after text entry operation")
#         except Exception:
#             # This is not significant enough to fail the operation
#             pass

# # 使用示例
# if __name__ == "__main__":
#     # 需要先启动 Chrome 开启 debugger 端口: 
#     # chrome.exe --remote-debugging-port=9222
    
#     cdp = "http://localhost:9222"
#     manager = PlaywrightManager(cdp)
    
#     try:
#         manager.start()
#         manager.open_page("https://www.google.com")
        
#         # 模拟执行 LLM 返回的动作
#         manager.execute_action("Action: type(content='Playwright Python', start_box='(500, 300)')")
#         manager.execute_action("Action: click(start_box='(600, 400)')")
        
#         manager.save_screenshot("test_result.png")
        
#     except Exception as e:
#         print(f"执行出错: {e}")
#     finally:
#         manager.close()

import os
import tempfile
import time
import threading

from playwright.sync_api import sync_playwright
from playwright.sync_api import BrowserContext
from playwright.sync_api import Page
from playwright.sync_api import Playwright

from ae.core.notification_manager import NotificationManager
from ae.core.ui_manager import UIManager
from ae.utils.dom_mutation_observer import dom_mutation_change_detected
from ae.utils.dom_mutation_observer import handle_navigation_for_mutation_observer
from ae.utils.js_helper import beautify_plan_message
from ae.utils.js_helper import escape_js_message
from ae.utils.logger import logger
from ae.utils.ui_messagetype import MessageType
import json

# Enusres that playwright does not wait for font loading when taking screenshots. Reference: https://github.com/microsoft/playwright/issues/28995
os.environ["PW_TEST_SCREENSHOT_NO_FONTS_READY"] = "1"

class PlaywrightManager:
    """
    A singleton class to manage Playwright instances and browsers.

    Attributes:
        browser_type (str): The type of browser to use ('chromium', 'firefox', 'webkit').
        isheadless (bool): Flag to launch the browser in headless mode or not.

    The class ensures only one instance of itself, Playwright, and the browser is created during the application lifecycle.
    """
    _homepage = "https://www.google.com"
    _instance = None
    _playwright = None # type: ignore
    _browser_context = None
    __initialize_done = False
    _take_screenshots = False
    _screenshots_dir = None

    def __new__(cls, *args, **kwargs): # type: ignore
        """
        Ensures that only one instance of PlaywrightManager is created (singleton pattern).
        """
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.__initialized = False
            logger.debug("Playwright instance created..")
        return cls._instance

    def __init__(self, cdp_url: str = "", headless: bool = False, gui_input_mode: bool = False, screenshots_dir: str = "", take_screenshots: bool = False):
        """
        Initializes the PlaywrightManager with the specified browser type and headless mode.
        Initialization occurs only once due to the singleton pattern.

        Args:
            browser_type (str, optional): The type of browser to use. Defaults to "chromium".
            headless (bool, optional): Flag to launch the browser in headless mode or not. Defaults to False (non-headless).
        """
        if self.__initialized:
            return

        self.cdp_url = cdp_url
        self._browser = None
        self._page = None
        self._screenshot_counter = 0
        self._request_collector = RequestCollector()

        self.isheadless = headless
        self.__initialized = True
        self.notification_manager = NotificationManager()
        # self.user_response_event = asyncio.Event()
        self.user_response_event = threading.Event()
        if gui_input_mode:
            self.ui_manager: UIManager = UIManager()
        else:
            self.ui_manager = None

        self.set_take_screenshots(take_screenshots)
        self.set_screenshots_dir(screenshots_dir)

    def initialize(self):
        """
        Asynchronously initialize necessary components and handlers for the browser context.
        """

        if self.__initialize_done:
            return

        # Step 1: Ensure Playwright is started and browser context is created
        self.start_playwright()
        self.ensure_browser_context()

        # Step 2: Deferred setup of handlers
        # self.setup_handlers()

        # Step 3: Navigate to homepage
        # self.go_to_homepage()

        self.__initialize_done = True

    def open_page(self, target_url, max_retries = 3):
        # 去除前后空格
        if target_url:
            target_url = target_url.strip()
        # 自动补全 https
        if target_url and not target_url.startswith("http"):
            target_url = "https://" + target_url

        print(f"🌐 打开页面: {target_url}")

        retry_count = 0
        while retry_count < max_retries:
            try:
                # 清理多余的页面
                if len(self._browser_context.pages) >= 3:
                    print(f"页面太多 ({len(self._browser_context.pages)}个)，关闭旧页面...")
                    pages_to_close = self._browser_context.pages[:-1]
                    for old_page in pages_to_close:
                        try:
                            # 先强制停止页面活动
                            try:
                                old_page.evaluate("() => { window.stop(); }")
                            except:
                                pass
                            
                            # 使用run_before_unload=False跳过确认框
                            old_page.close(run_before_unload=False)

                        except Exception as e:
                            print(f"关闭失败: {e}")
                            # 继续关闭其他页面，不要exit()

            except Exception as e:
                print(f"清理页面时出错: {e}")

            try:
                # 尝试创建新页面
                if self._browser_context and len(self._browser_context.pages) > 0:
                    try:
                        self._page = self._browser_context.new_page()
                        break
                    except Exception as e:
                        print(f"创建页面失败: {e}")
                        self._browser_context = None
                
                # 如果context不存在或创建页面失败，重新连接
                if not self._browser_context or not self._page:
                    print(f"重新连接到浏览器... (尝试 {retry_count + 1}/{max_retries})")
                    
                    # 先尝试断开现有连接
                    try:
                        if self._browser:
                            self._browser.close()
                    except:
                        pass
                    
                    # 等待一下让连接完全关闭
                    import time
                    time.sleep(2)
                    
                    # 重新连接
                    try:
                        self._browser = self._playwright.chromium.connect_over_cdp(cdp_url)
                        # 等待连接稳定
                        time.sleep(1)
                        
                        # 获取或创建context
                        if self._browser.contexts:
                            self._browser_context = self._browser.contexts[0]
                        else:
                            self._browser_context = self._browser.new_context()
                        
                        self._page = self._browser_context.new_page()
                        break
                        
                    except Exception as e:
                        print(f"连接失败: {e}")
                        retry_count += 1
                        if retry_count >= max_retries:
                            raise Exception(f"无法连接到浏览器，已尝试 {max_retries} 次")
                        continue
                        
            except Exception as e:
                print(f"创建页面时出错: {e}")
                retry_count += 1
                if retry_count >= max_retries:
                    raise
        
        if not self._page:
            raise Exception("无法创建页面")
        
        # 设置视口大小
        try:
            # 获取整个浏览器窗口的大小
            browser_window_size = self._page.evaluate("""
                () => {
                    return {
                        availWidth: window.screen.availWidth,
                        availHeight: window.screen.availHeight,
                        width: window.outerWidth || 1920,
                        height: window.outerHeight || 1080
                    }
                }
            """)
            
            print(f"可用屏幕大小: {browser_window_size['availWidth']}x{browser_window_size['availHeight']}")
            print(f"浏览器窗口大小: {browser_window_size['width']}x{browser_window_size['height']}")
            
            browser_window_size_width = browser_window_size['width']
            browser_window_size_height = browser_window_size['height']
            
            self._page.set_viewport_size({"width": browser_window_size_width, "height": browser_window_size_height})
        except Exception as e:
            print(f"设置视口大小失败: {e}，使用默认值")
            browser_window_size_width = 1920
            browser_window_size_height = 1080
            self._page.set_viewport_size({"width": 1920, "height": 1080})
        
        # 为所有页面请求添加无缓存头
        def prevent_cache(route):
            try:
                headers = route.request.headers.copy()
                headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
                headers['Pragma'] = 'no-cache'
                headers['Expires'] = '0'
                route.continue_(headers=headers)
            except:
                route.continue_()
        
        # 只对主文档应用此规则
        try:
            self._page.route('**/*', prevent_cache)
        except Exception as e:
            print(f"设置路由规则失败: {e}")
        
        # 导航到目标URL
        try:
            self._page.goto(target_url, wait_until="domcontentloaded", timeout=150000)
            self._page.wait_for_timeout(3000)
        except Exception as e:
            print(f"导航到页面失败: {e}")
            # 尝试使用更宽松的等待条件
            try:
                self._page.goto(target_url, wait_until="commit", timeout=60000)
            except:
                # 如果还是失败，至少确保页面存在
                pass
        
        return self._page

    def ensure_browser_context(self):
        """
        Ensure that a browser context exists, creating it if necessary.
        """
        if self._browser_context is None:
            self.create_browser_context()

    def setup_handlers(self):
        """
        Setup various handlers after the browser context has been ensured.
        """
        self.set_overlay_state_handler()
        self.set_user_response_handler()
        self.set_navigation_handler()

    def start_playwright(self):
        """
        Starts the Playwright instance if it hasn't been started yet. This method is idempotent.
        """
        if not PlaywrightManager._playwright:
            PlaywrightManager._playwright: Playwright = sync_playwright().start()

    def stop_playwright(self):
        print("被调用关闭浏览器")
        """
        Stops the Playwright instance and resets it to None. This method should be called to clean up resources.
        """
        # Close the browser context if it's initialized
        if PlaywrightManager._browser_context is not None:
            PlaywrightManager._browser_context.close()
            PlaywrightManager._browser_context = None

        if self._browser is not None:  # 👈 新增
            self._browser.close()
            self._browser = None
            logger.debug("已断开浏览器连接")

        # Stop the Playwright instance if it's initialized
        if PlaywrightManager._playwright is not None: # type: ignore
            PlaywrightManager._playwright.stop()
            PlaywrightManager._playwright = None # type: ignore

    def create_browser_context(self):
        # 防止重复创建
        if PlaywrightManager._browser_context is not None:
            logger.debug("浏览器上下文已存在，跳过创建")
            return

        try:
            if not self._playwright:
                self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.connect_over_cdp(self.cdp_url)
            
            # 3️⃣ 获取或创建上下文
            if self._browser:
                PlaywrightManager._browser_context = self._browser.contexts[0]
                logger.info(f"📄 使用现有上下文 (共 {len(self._browser.contexts)} 个上下文)")
            else:
                PlaywrightManager._browser_context = self._browser.new_context(
                    viewport=None,  # 使用浏览器实际视口
                )
                logger.info("📄 创建新的浏览器上下文")
            
            # 4️⃣ 设置默认超时
            PlaywrightManager._browser_context.set_default_timeout(60000)
            PlaywrightManager._browser_context.set_default_navigation_timeout(60000)
            
        except Exception as e:
            # 详细错误处理
            if "ECONNREFUSED" in str(e):
                logger.error(
                    f"❌ 无法连接到 {self.cdp_url}\n"
                    "请确保浏览器已启动并开启远程调试：\n"
                    "  chrome --remote-debugging-port=9222"
                )
            elif "Browser closed" in str(e):
                logger.error("❌ 浏览器已关闭，请重新启动浏览器")
            else:
                logger.error(f"❌ 连接失败: {e}")
            raise

    def get_browser_context(self):
            """
            Returns the existing browser context, or creates a new one if it doesn't exist.
            """
            self.ensure_browser_context()
            return self._browser_context

    def get_current_url(self) -> str | None:
        """
        Get the current URL of current page

        Returns:
            str | None: The current URL if any.
        """
        try:
            current_page: Page =self.get_current_page()
            return current_page.url
        except Exception:
            pass
        return None

    def get_current_page(self) -> Page :
        """
        Get the current page of the browser

        Returns:
            Page: The current page if any.
        """
        # try:
        #     browser: BrowserContext = self.get_browser_context() # type: ignore
        #     # Filter out closed pages
        #     pages: list[Page] = [page for page in browser.pages if not page.is_closed()]
        #     page: Page | None = pages[-1] if pages else None
        #     logger.debug(f"Current page: {page.url if page else None}")
        #     if page is not None:
        #         return page
        #     else:
        #         page:Page = browser.new_page() # type: ignore
        #         return page
        # except Exception:
        #         logger.warn("Browser context was closed. Creating a new one.")
        #         PlaywrightManager._browser_context = None
        #         self._browser = None
        #         _browser:BrowserContext= self.get_browser_context() # type: ignore
        #         page: Page | None = self.get_current_page()
        #         return page
        try:
            browser: BrowserContext = self.get_browser_context() # type: ignore
            # Filter out closed pages
            pages: list[Page] = [page for page in browser.pages if not page.is_closed()]
            current_page: Page | None = pages[-1] if pages else None
            logger.debug(f"Current page: {current_page.url if current_page else None}")

            if current_page is not None:
                # 🆕 判断是否是新页面（不是之前保存的 self._page）
                is_new_page = (self._page is None) or (current_page is not self._page)
                
                if is_new_page:
                    # 为新页面添加请求监听器
                    self._page = current_page
                    self._page.on("request", self._request_collector.handle_request)

                return self._page

            else:
                # 没有可用页面，创建新页面
                logger.debug("📄 创建新页面")
                self._page: Page = browser.new_page() # type: ignore
                self._page.on("request", self._request_collector.handle_request)

                return self._page


        except Exception:
                logger.warn("Browser context was closed. Creating a new one.")
                PlaywrightManager._browser_context = None
                self._browser = None
                _browser:BrowserContext= self.get_browser_context() # type: ignore
                self._page: Page | None = self.get_current_page()
                return self._page

    def close_all_tabs(self, keep_first_tab: bool = True):
            """
            Closes all tabs in the browser context, except for the first tab if `keep_first_tab` is set to True.

            Args:
                keep_first_tab (bool, optional): Whether to keep the first tab open. Defaults to True.
            """
            browser_context = self.get_browser_context()
            pages: list[Page] = browser_context.pages #type: ignore
            pages_to_close: list[Page] = pages[1:] if keep_first_tab else pages # type: ignore
            for page in pages_to_close: # type: ignore
                page.close() # type: ignore

    def close_except_specified_tab(self, page_to_keep: Page):
        """
        Closes all tabs in the browser context, except for the specified tab.

        Args:
            page_to_keep (Page): The Playwright page object representing the tab that should remain open.
        """
        browser_context = self.get_browser_context()
        closed_pages = browser_context.pages[:-1]
        for page in closed_pages: # type: ignore
            if page != page_to_keep:  # Check if the current page is not the one to keep
                page.close() # type: ignore

    def go_to_homepage(self):
        page:Page = PlaywrightManager.get_current_page(self)
        page.goto(self._homepage)

    def set_navigation_handler(self):
        page:Page = PlaywrightManager.get_current_page(self)
        page.on("domcontentloaded", self.ui_manager.handle_navigation) # type: ignore
        page.on("domcontentloaded", handle_navigation_for_mutation_observer) # type: ignore
        page.expose_function("dom_mutation_change_detected", dom_mutation_change_detected) # type: ignore

    def set_overlay_state_handler(self):
        logger.debug("Setting overlay state handler")
        context = self.get_browser_context()
        context.expose_function('overlay_state_changed', self.overlay_state_handler) # type: ignore
        context.expose_function('show_steps_state_changed',self.show_steps_state_handler) # type: ignore

    def overlay_state_handler(self, is_collapsed: bool):
        page = self.get_current_page()
        self.ui_manager.update_overlay_state(is_collapsed)
        if not is_collapsed:
            self.ui_manager.update_overlay_chat_history(page)

    def show_steps_state_handler(self, show_details: bool):
        page = self.get_current_page()
        self.ui_manager.update_overlay_show_details(show_details, page)

    def set_user_response_handler(self):
        context = self.get_browser_context()
        context.expose_function('user_response', self.receive_user_response) # type: ignore

    def notify_user(self, message: str, message_type: MessageType = MessageType.STEP):
        # """
        # Notify the user with a message.

        # Args:
        #     message (str): The message to notify the user with.
        #     message_type (enum, optional): Values can be 'PLAN', 'QUESTION', 'ANSWER', 'INFO', 'STEP'. Defaults to 'STEP'.
        #     To Do: Convert to Enum.
        # """

        # if message.startswith(":"):
        #     message = message[1:]

        # if message.endswith(","):
        #     message = message[:-1]

        # if message_type == MessageType.PLAN:
        #     message = beautify_plan_message(message)
        #     message = "Plan:\n" + message
        # elif message_type == MessageType.STEP:
        #     if "confirm" in message.lower():
        #         message = "Verify: " + message
        #     else:
        #         message = "Next step: " + message
        # elif message_type == MessageType.QUESTION:
        #     message = "Question: " + message
        # elif message_type == MessageType.ANSWER:
        #     message = "Response: " + message

        # safe_message = escape_js_message(message)

        # if self.ui_manager:
        #     self.ui_manager.new_system_message(safe_message, message_type)

        #     if self.ui_manager.overlay_show_details == False:  # noqa: E712
        #         if message_type not in (MessageType.PLAN, MessageType.QUESTION, MessageType.ANSWER, MessageType.INFO):
        #             return

        #     if self.ui_manager.overlay_show_details == True:  # noqa: E712
        #         if message_type not in (MessageType.PLAN,  MessageType.QUESTION , MessageType.ANSWER,  MessageType.INFO, MessageType.STEP):
        #             return

        # safe_message_type = escape_js_message(message_type.value)
        # try:
        #     js_code = f"addSystemMessage({safe_message}, is_awaiting_user_response=false, message_type={safe_message_type});"
        #     page = self.get_current_page()
        #     page.evaluate(js_code)
        # except Exception as e:
        #     logger.error(f"Failed to notify user with message \"{message}\". However, most likey this will work itself out after the page loads: {e}")

        # self.notification_manager.notify(message, message_type.value)
        pass

    def highlight_element(self, selector: str, add_highlight: bool):
        try:
            page: Page = self.get_current_page()
            if add_highlight:
                # Add the 'agente-ui-automation-highlight' class to the element. This class is used to apply the fading border.
                page.eval_on_selector(selector, '''e => {
                            let originalBorderStyle = e.style.border;
                            e.classList.add('agente-ui-automation-highlight');
                            e.addEventListener('animationend', () => {
                                e.classList.remove('agente-ui-automation-highlight')
                            });}''')
                logger.debug(f"Applied pulsating border to element with selector {selector} to indicate text entry operation")
            else:
                # Remove the 'agente-ui-automation-highlight' class from the element.
                page.eval_on_selector(selector, "e => e.classList.remove('agente-ui-automation-highlight')")
                logger.debug(f"Removed pulsating border from element with selector {selector} after text entry operation")
        except Exception:
            # This is not significant enough to fail the operation
            pass

    def receive_user_response(self, response: str):
        self.user_response = response  # Store the response for later use.
        logger.debug(f"Received user response to system prompt: {response}")
        # Notify event loop that the user's response has been received.
        self.user_response_event.set()

    def prompt_user(self, message: str) -> str:
        """
        Prompt the user with a message and wait for a response.

        Args:
            message (str): The message to prompt the user with.

        Returns:
            str: The user's response.
        """
        logger.debug(f"Prompting user with message: \"{message}\"")
        #self.ui_manager.new_system_message(message)

        page = self.get_current_page()

        self.ui_manager.show_overlay(page)
        self.log_system_message(message, MessageType.QUESTION) # add the message to history after the overlay is opened to avoid double adding it. add_system_message below will add it

        safe_message = escape_js_message(message)

        js_code = f"addSystemMessage({safe_message}, is_awaiting_user_response=true, message_type='question');"
        page.evaluate(js_code)

        self.user_response_event.wait()
        result = self.user_response
        logger.info(f"User prompt reponse to \"{message}\": {result}")
        self.user_response_event.clear()
        self.user_response = ""
        self.ui_manager.new_user_message(result)
        return result

    def set_take_screenshots(self, take_screenshots: bool):
        self._take_screenshots = take_screenshots

    def get_take_screenshots(self):
        return self._take_screenshots

    def set_screenshots_dir(self, screenshots_dir: str):
        self._screenshots_dir = screenshots_dir

    def get_screenshots_dir(self):
        return self._screenshots_dir

    def take_screenshots(self, name: str, page: Page|None, full_page: bool = True, include_timestamp: bool = True,
                               load_state: str = 'domcontentloaded', take_snapshot_timeout: int = 10*1000):
        print("开始截图")

        if not self._take_screenshots:
            return
        
        if page is None:
            page = self.get_current_page()

        screenshot_name = name

        # if include_timestamp:
            # screenshot_name = f"{int(time.time_ns())}_{screenshot_name}"
        if "_end" in screenshot_name:
            return

        self._screenshot_counter += 1
        screenshot_name = f"{self._screenshot_counter:02d}_{screenshot_name}"

        screenshot_name += ".png"
        screenshot_path = f"{self.get_screenshots_dir()}/{screenshot_name}"
        try:
            page.wait_for_load_state(state=load_state, timeout=take_snapshot_timeout) # type: ignore
            page.screenshot(
                path=screenshot_path, 
                full_page=full_page, 
                timeout=take_snapshot_timeout, 
                caret="initial", 
                scale="device"
            )
            logger.debug(f"Screen shot saved to: {screenshot_path}")
            # exit()
        except Exception as e:
            logger.error(f"Failed to take screenshot and save to \"{screenshot_path}\". Error: {e}")

    def log_user_message(self, message: str):
        """
        Log the user's message.

        Args:
            message (str): The user's message to log.
        """
        self.ui_manager.new_user_message(message)

    def log_system_message(self, message: str, type: MessageType = MessageType.STEP):
        """
        Log a system message.

        Args:
            message (str): The system message to log.
        """
        self.ui_manager.new_system_message(message, type)

    def update_processing_state(self, processing_state: str):
        """
        Update the processing state of the overlay.

        Args:
            is_processing (str): "init", "processing", "done"
        """
        page = self.get_current_page()

        self.ui_manager.update_processing_state(processing_state, page)

    def command_completed(self, command: str, elapsed_time: float | None = None):
        """
        Notify the overlay that the command has been completed.
        """
        logger.debug(f"Command \"{command}\" has been completed. Focusing on the overlay input if it is open.")
        page = self.get_current_page()
        self.ui_manager.command_completed(page, command, elapsed_time)




    # ================= Coordinate-based Action Methods =================

    def _get_cdp_session(self):
        """Get or create a CDP session for the current page. Recreates if page changed."""
        page = self.get_current_page()
        if (not hasattr(self, '_cdp_client') or self._cdp_client is None
                or not hasattr(self, '_cdp_bound_page') or self._cdp_bound_page != page):
            # Page changed or no session yet — create new CDP session
            try:
                if hasattr(self, '_cdp_client') and self._cdp_client is not None:
                    self._cdp_client.detach()
            except:
                pass
            self._cdp_client = page.context.new_cdp_session(page)
            self._cdp_bound_page = page
        return self._cdp_client

    def _cdp_mouse_move(self, end_x, end_y, steps=20):
        """Move mouse to (end_x, end_y) via CDP with intermediate steps."""
        import random
        client = self._get_cdp_session()
        page = self.get_current_page()
        
        # Get current mouse position (default to center)
        if not hasattr(self, '_mouse_x'):
            viewport = page.viewport_size or {"width": 1280, "height": 720}
            self._mouse_x = viewport["width"] // 2
            self._mouse_y = viewport["height"] // 2

        start_x, start_y = self._mouse_x, self._mouse_y
        delta_x = (end_x - start_x) / steps
        delta_y = (end_y - start_y) / steps

        for step in range(1, steps + 1):
            x = start_x + delta_x * step
            y = start_y + delta_y * step
            client.send("Input.dispatchMouseEvent", {
                "type": "mouseMoved",
                "x": int(x), "y": int(y),
                "button": "none"
            })
            import time
            time.sleep(random.uniform(0.005, 0.015))

        self._mouse_x = int(end_x)
        self._mouse_y = int(end_y)

    def _mouse_up_and_down(self, x, y):
        """Press and release mouse at (x, y) via CDP."""
        client = self._get_cdp_session()
        client.send("Input.dispatchMouseEvent", {
            "type": "mousePressed", "x": int(x), "y": int(y),
            "button": "left", "clickCount": 1
        })
        client.send("Input.dispatchMouseEvent", {
            "type": "mouseReleased", "x": int(x), "y": int(y),
            "button": "left", "clickCount": 1
        })

    def click(self, x, y, time_wait=1000):
        """Click at coordinates (x, y) using CDP mouse events."""
        self._cdp_mouse_move(x, y, steps=15)
        self._mouse_up_and_down(x, y)
        self.get_current_page().wait_for_timeout(time_wait)

    def double_click(self, x, y, time_wait=1000):
        """Double-click at coordinates (x, y) using CDP mouse events."""
        import random
        self._cdp_mouse_move(x, y, steps=15)
        wait_t = random.randint(200, 400)
        self._mouse_up_and_down(x, y)
        self.get_current_page().wait_for_timeout(wait_t)
        self._mouse_up_and_down(x, y)
        self.get_current_page().wait_for_timeout(time_wait)

    def right_click(self, x, y, time_wait=1000):
        """Right-click at coordinates (x, y) using CDP mouse events."""
        client = self._get_cdp_session()
        self._cdp_mouse_move(x, y, steps=15)
        client.send("Input.dispatchMouseEvent", {
            "type": "mousePressed", "x": int(x), "y": int(y),
            "button": "right", "clickCount": 1
        })
        client.send("Input.dispatchMouseEvent", {
            "type": "mouseReleased", "x": int(x), "y": int(y),
            "button": "right", "clickCount": 1
        })
        self.get_current_page().wait_for_timeout(time_wait)

    def hover(self, x, y):
        """Move mouse to (x, y) without clicking."""
        self._cdp_mouse_move(x, y, steps=15)

    def type_text(self, x, y, content, time_wait=500):
        """Click at (x, y), clear field, then type content character by character."""
        import random, platform
        self.click(x, y, time_wait)
        page = self.get_current_page()
        page.wait_for_timeout(random.randint(100, 200))

        # Select all and delete
        modifier = "Meta" if platform.system() == "Darwin" else "Control"
        page.keyboard.press(f"{modifier}+a")
        page.keyboard.press("Backspace")
        page.wait_for_timeout(500)

        # Type character by character
        for char in content:
            page.keyboard.type(char, delay=random.randint(10, 50))
        page.wait_for_timeout(1000)

    def type_without_click(self, content):
        """Type content without clicking first (assumes field is already focused)."""
        page = self.get_current_page()
        page.keyboard.type(content)

    def hotkey(self, key_value):
        """Press a keyboard shortcut."""
        page = self.get_current_page()
        if "enter" in key_value.lower():
            page.keyboard.press("Enter")
        else:
            page.keyboard.press(key_value)
        page.wait_for_timeout(1000)

    def scroll(self, delta_x, delta_y):
        """Scroll at the center of the viewport."""
        page = self.get_current_page()
        viewport = page.viewport_size or {"width": 1280, "height": 720}
        center_x = viewport["width"] // 2
        center_y = viewport["height"] // 2
        client = self._get_cdp_session()
        client.send("Input.dispatchMouseEvent", {
            "type": "mouseWheel",
            "x": center_x, "y": center_y,
            "deltaX": int(delta_x), "deltaY": int(delta_y)
        })
        page.wait_for_timeout(500)

    def scroll_at(self, x, y, delta_x, delta_y):
        """Scroll at specific coordinates."""
        client = self._get_cdp_session()
        self._cdp_mouse_move(x, y)
        client.send("Input.dispatchMouseEvent", {
            "type": "mouseWheel",
            "x": int(x), "y": int(y),
            "deltaX": int(delta_x), "deltaY": int(delta_y)
        })
        self.get_current_page().wait_for_timeout(500)

    def drag(self, x1, y1, x2, y2, steps=20):
        """Drag from (x1,y1) to (x2,y2) using CDP mouse events."""
        import time as _time
        client = self._get_cdp_session()
        self._cdp_mouse_move(x1, y1, steps)
        self.get_current_page().wait_for_timeout(100)

        # Press
        client.send("Input.dispatchMouseEvent", {
            "type": "mousePressed", "x": int(x1), "y": int(y1),
            "button": "left", "clickCount": 1
        })

        # Move
        delta_x = (x2 - x1) / steps
        delta_y = (y2 - y1) / steps
        for step in range(1, steps + 1):
            client.send("Input.dispatchMouseEvent", {
                "type": "mouseMoved",
                "x": int(x1 + delta_x * step),
                "y": int(y1 + delta_y * step),
                "button": "left", "buttons": 1
            })
            _time.sleep(0.01)

        # Release
        client.send("Input.dispatchMouseEvent", {
            "type": "mouseReleased", "x": int(x2), "y": int(y2),
            "button": "left", "clickCount": 1
        })
        self.get_current_page().wait_for_timeout(1000)


# 监听请求类
class RequestCollector:
    """每个进程独立的请求收集器"""
    def __init__(self):
        self.requests = []
    
    def clear(self):
        """清空请求列表"""
        self.requests = []
    
    def handle_request(self, request):
        """处理每个请求"""
        req_data = {
            "timestamp": time.time(),
            "url": request.url,
            "method": request.method,
            "headers": dict(request.headers),
            "resource_type": request.resource_type,
            "post_data": None,
            "post_text": None,
            "json_data": None
        }
        
        if request.resource_type not in ["xhr", "fetch"]:
            return
        
        raw = request.post_data_buffer
        if raw:
            req_data["raw_post_data"] = raw.hex()
            try:
                text = raw.decode("utf-8")
                req_data["post_data"] = text
                try:
                    req_data["json_data"] = json.loads(text)
                except:
                    pass
                if req_data["post_data"] is None:
                    return
            except UnicodeDecodeError:
                pass
        
        self.requests.append(req_data)
    
    # def save_results(self, save_result_path="capture.json"):
    #     """保存捕获的结果"""
    #     output = {
    #         "capture_time": time.strftime("%Y-%m-%d %H:%M:%S"),
    #         "total_requests": len(self.requests),
    #         "all_requests": self.requests
    #     }
        
    #     with open(save_result_path, "w", encoding="utf-8") as f:
    #         json.dump(output, f, indent=4, ensure_ascii=False)
        
    #     print("结果已保存到 capture.json")
    #     return len(self.requests)

    def save_results(self, save_result_path="capture.json", max_retries=3):
        """带重试的保存方法"""
        for attempt in range(max_retries):
            try:
                output = {
                    "capture_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "total_requests": len(self.requests),
                    "all_requests": self.requests
                }
                
                # 原子写入
                temp_path = f"{save_result_path}.tmp"
                with open(temp_path, "w", encoding="utf-8") as f:
                    json.dump(output, f, indent=4, ensure_ascii=False)
                
                os.replace(temp_path, save_result_path)  # 原子替换
                return len(self.requests)
            
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                time.sleep(0.1 * (2 ** attempt))  # 指数退避

