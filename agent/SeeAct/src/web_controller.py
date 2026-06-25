import json
import uuid
from playwright.sync_api import sync_playwright
import random
import platform
import base64
import json
import re
import os
import time
import asyncio
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from typing import List, Dict, Any

browser_window_size_width = 1280
browser_window_size_height = 720

def extract_between_keywords(text, start_key, end_key):
    pattern = re.compile(f'{re.escape(start_key)}(.*?){re.escape(end_key)}', re.DOTALL)
    matches = pattern.findall(text)
    return [match.strip() for match in matches]

# 初始化Playwright
def init_playwright_context(url):
    p = sync_playwright().start()
    try:
        browser = p.chromium.connect_over_cdp(url)
        # 获取已存在的上下文或创建新的
        context = browser.contexts[0] if browser.contexts else browser.new_context()
    except Exception as e:
        print("init error", e)
        return None, None, None

    return p, browser, context

# 打开网页
def open_page(
    p,
    browser,
    context,
    cdp_url,
    target_url,
    request_collector=None,
    worker_id=None,
    max_retries=3,
):
    # ----------------
    # URL 清洗
    # ----------------
    if target_url:
        target_url = target_url.strip()
    if target_url and not target_url.startswith("http"):
        target_url = "https://" + target_url

    print(f"🌐 打开页面: {target_url}")

    page = None
    retry_count = 0

    # ----------------
    # 路由：禁用缓存（每个 page 都要装）
    # ----------------
    def prevent_cache(route):
        try:
            headers = route.request.headers.copy()
            headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            headers["Pragma"] = "no-cache"
            headers["Expires"] = "0"
            route.continue_(headers=headers)
        except Exception:
            try:
                route.continue_()
            except Exception:
                pass

    # ----------------
    # 给单个 page 绑定：route + request hooks（必须在 goto 前）
    # ----------------
    def _hook_one_page(pg):
        # 1) route（每个新 page 都要装）
        try:
            if not getattr(pg, "_route_hooked", False):
                pg.route("**/*", prevent_cache)
                pg._route_hooked = True
        except Exception as e:
            # 有些情况下（page 已关闭/上下文异常）route 会失败，忽略即可
            print(f"[Worker {worker_id}] ⚠️ page.route 失败: {e}")

        # 2) request 监听（每个新 page 都要装）
        if request_collector is not None:
            try:
                if not getattr(pg, "_req_hooked", False):
                    pg.on("request", request_collector.handle_request)
                    pg.on("requestfailed", lambda r: print(f"[Worker {worker_id}] ❌ requestfailed: {r.url[:120]}"))
                    pg._req_hooked = True
                    print(f"[Worker {worker_id}] 👂 page hooked: page={id(pg)}")
            except Exception as e:
                print(f"[Worker {worker_id}] ❌ 绑定 request 监听失败: {e}")

    # ----------------
    # 主循环：创建 page / 重连
    # ----------------
    while retry_count < max_retries:
        # 1) 尝试清理多余页面
        try:
            if context is not None and len(context.pages) >= 3:
                print(f"页面太多 ({len(context.pages)}个)，关闭旧页面...")
                pages_to_close = context.pages[:-1]
                for old_page in pages_to_close:
                    try:
                        try:
                            old_page.evaluate("() => { window.stop(); }")
                        except Exception:
                            pass
                        old_page.close(run_before_unload=False)
                    except Exception as e:
                        print(f"关闭失败: {e}")
        except Exception as e:
            print(f"清理页面时出错: {e}")

        # 2) 先尝试在现有 context 里 new_page
        try:
            if context is not None:
                try:
                    page = context.new_page()
                except Exception as e:
                    print(f"创建页面失败: {e}")
                    page = None
                    context = None
        except Exception:
            page = None
            context = None

        # 3) 若失败则重连
        if page is None:
            print(f"重新连接到浏览器... (尝试 {retry_count + 1}/{max_retries})")

            try:
                if browser is not None:
                    try:
                        browser.close()
                    except Exception:
                        pass
            except Exception:
                pass

            import time as _time
            _time.sleep(1.5)

            try:
                browser = p.chromium.connect_over_cdp(cdp_url)
                _time.sleep(0.8)

                if browser.contexts:
                    context = browser.contexts[0]
                else:
                    context = browser.new_context()

                page = context.new_page()
            except Exception as e:
                print(f"连接失败: {e}")
                retry_count += 1
                if retry_count >= max_retries:
                    raise Exception(f"无法连接到浏览器，已尝试 {max_retries} 次")
                continue

        # ----------------
        # 到这里：page/context 已有
        # ----------------
        if page is None:
            retry_count += 1
            continue

        # ----------------
        # 关键：context.on('page') 必须在 goto 前注册，避免 popup/new tab 漏绑
        # ----------------
        if request_collector is not None:
            try:
                if not getattr(context, "_page_hooked", False):
                    context.on("page", _hook_one_page)
                    context._page_hooked = True
                    print(f"[Worker {worker_id}] ✅ context.on('page') installed")
            except Exception as e:
                print(f"[Worker {worker_id}] ❌ context.on('page') 设置失败: {e}")

        # 当前 page 也必须在 goto 前 hook
        _hook_one_page(page)

        # ----------------
        # 视口设置（尽量不依赖页面 JS；设置失败就用默认）
        # ----------------
        try:
            browser_window_size = page.evaluate(
                """() => ({
                    availWidth: window.screen.availWidth,
                    availHeight: window.screen.availHeight,
                    width: window.outerWidth || 1920,
                    height: window.outerHeight || 1080
                })"""
            )
            w = int(browser_window_size.get("width", 1920))
            h = int(browser_window_size.get("height", 1080))
            print(f"可用屏幕大小: {browser_window_size.get('availWidth')}x{browser_window_size.get('availHeight')}")
            print(f"浏览器窗口大小: {w}x{h}")
            page.set_viewport_size({"width": w, "height": h})
        except Exception as e:
            print(f"设置视口大小失败: {e}，使用默认值")
            page.set_viewport_size({"width": 1920, "height": 1080})

        # ----------------
        # 导航
        # ----------------
        try:
            page.goto(target_url, wait_until="domcontentloaded", timeout=150000)
            page.wait_for_timeout(1500)
        except Exception as e:
            print(f"导航到页面失败(domcontentloaded): {e}")
            try:
                page.goto(target_url, wait_until="commit", timeout=60000)
                page.wait_for_timeout(1000)
            except Exception as e2:
                print(f"导航到页面失败(commit): {e2}")

        # ----------------
        # 探针：同域请求，验证 request hook 是否生效（不依赖外网）
        # ----------------
        if request_collector is not None:
            try:
                page.evaluate(
                    """() => {
                        try{
                          const u = location.origin + "/favicon.ico?x=" + Date.now();
                          fetch(u, {cache:'no-store'}).catch(()=>{});
                        }catch(e){}
                    }"""
                )
                page.wait_for_timeout(800)
            except Exception:
                pass

        return page

    raise Exception("无法创建页面")


# 截图保存
def save_screenshot(page, savePath, timeout_ms=5000, max_retries=3):
    """
    保存截图，带重试机制
    """
    # 确保目录存在 (只需执行一次)
    try:
        os.makedirs(os.path.dirname(savePath), exist_ok=True)
    except Exception as e:
        print(f"###创建目录失败: {str(e)}")
        return False

    for i in range(max_retries):
        try:
            # 尝试截图
            # page.screenshot(path=savePath, full_page=True, timeout=timeout_ms)
            page.screenshot(path=savePath, full_page=False, timeout=timeout_ms)
            print(f"###截图保存至: {savePath}")
            return True
        except Exception as e:
            print(f"###截图保存失败 (尝试 {i+1}/{max_retries}): {str(e)}")
            if i < max_retries - 1:
                time.sleep(1)  # 失败后稍作等待再重试
    
    return False

# CDP移动
def cdp_mouse_move(client, end_x, end_y, steps=20):
    """
    使用CDP协议模拟Playwright的page.mouse.move多步移动功能
    
    参数:
    client - CDP会话
    end_x, end_y - 目标坐标
    steps - 移动的步数
    """
    import time
    
    # 首先获取鼠标当前位置（如果无法获取，可以假设一个起始位置）
    try:
        # 注意：CDP没有直接获取鼠标位置的方法，这里通过JavaScript获取
        position = client.send("Runtime.evaluate", {
            "expression": "({x: window.mouseX || 0, y: window.mouseY || 0})",
            "returnByValue": True
        })
        start_x = position["result"]["value"]["x"]
        start_y = position["result"]["value"]["y"]
    except:
        # 如果无法获取，假设起始位置为(0,0)
        start_x, start_y = 0, 0
    
    # 计算移动增量
    delta_x = (end_x - start_x) / steps
    delta_y = (end_y - start_y) / steps
    
    # 执行多步移动
    for step in range(1, steps + 1):
        current_x = start_x + delta_x * step
        current_y = start_y + delta_y * step
        
        # 发送鼠标移动事件
        client.send("Input.dispatchMouseEvent", {
            "type": "mouseMoved", 
            "x": current_x, 
            "y": current_y
        })
        
        # 可选：添加小延迟使移动更自然
        time.sleep(0.01)  # 10毫秒延迟
    
    # 更新全局鼠标位置（可选，方便下次调用）
    client.send("Runtime.evaluate", {
        "expression": f"window.mouseX = {end_x}; window.mouseY = {end_y};"
    })

# CDP点击
def mouse_up_and_down(page, client, x, y, time_wait=500):
    # client.send("Input.dispatchMouseEvent", {
    #     "type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1
    # })
    # page.wait_for_timeout(time_wait)  # 保持按下
    # client.send("Input.dispatchMouseEvent", {
    #     "type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1
    # })
    page.mouse.click(x, y)

# 点击
def click(page, client, x, y, time_wait=500):
    cdp_mouse_move(client, x, y, steps=20)
    #page.wait_for_timeout(500)

    # 执行CDP点击操作
    mouse_up_and_down(page, client, x, y, time_wait)
    page.wait_for_timeout(3000)

    return page, client

# 双击
def doubleclick(page, client, x, y, time_wait=500):
    # 执行点击操作
    cdp_mouse_move(client, x, y, steps=20)
 
    time_wait = random.randint(time_wait // 2, time_wait)
    mouse_up_and_down(page, client, x, y, time_wait)
    
    time_wait = random.randint(time_wait // 2, time_wait)
    mouse_up_and_down(page, client, x, y, time_wait)

    page.wait_for_timeout(3000)
    
    return page, client

# 按压快捷键
def hotkey(page, client, hot_key_value, time_wait=500):
    if "enter" in hot_key_value:
        # 模拟按下回车键
        client.send("Input.dispatchKeyEvent", {
            "type": "keyDown",
            "windowsVirtualKeyCode": 13,  # Enter 键的虚拟键码
            "code": "Enter",
            "key": "Enter",
            "text": "\r"  # 回车的文本表示
        })
        page.wait_for_timeout(2000)

    return page, client

# 键入
def click_type(page, client, x, y, content, time_wait=500):
    # 1. 使用CDP执行点击
    page, client = click(page, client, x, y, time_wait) 
    
    page.wait_for_timeout(random.randint(100, 200))
    
    # # 2. 全选 (Ctrl+A 或 Command+A)
    # modifier = 2
    
    # # 按下修饰键
    # client.send("Input.dispatchKeyEvent", {
    #     "type": "keyDown",
    #     "modifiers": modifier,
    #     "code": "ControlLeft",
    #     "key": "Control",
    #     "windowsVirtualKeyCode": 17
    # })
    
    # # 按下A键
    # client.send("Input.dispatchKeyEvent", {
    #     "type": "keyDown",
    #     "modifiers": modifier,
    #     "code": "KeyA",
    #     "key": "a",
    #     "windowsVirtualKeyCode": 65
    # })
    
    # # 释放A键
    # client.send("Input.dispatchKeyEvent", {
    #     "type": "keyUp",
    #     "modifiers": modifier,
    #     "code": "KeyA",
    #     "key": "a",
    #     "windowsVirtualKeyCode": 65
    # })
    
    # # 释放修饰键
    # client.send("Input.dispatchKeyEvent", {
    #     "type": "keyUp",
    #     "code": "ControlLeft",
    #     "key": "Control",
    #     "windowsVirtualKeyCode": 17
    # })
    
    # # 3. 按下Backspace删除选中内容
    # client.send("Input.dispatchKeyEvent", {
    #     "type": "keyDown",
    #     "code": "Backspace",
    #     "key": "Backspace",
    #     "windowsVirtualKeyCode": 8
    # })
    
    # client.send("Input.dispatchKeyEvent", {
    #     "type": "keyUp",
    #     "code": "Backspace",
    #     "key": "Backspace",
    #     "windowsVirtualKeyCode": 8
    # })
    
    # # 等待随机时间
    # page.wait_for_timeout(random.randint(100, 200))
    
    # # 4. 逐字符输入内容
    # for char in content:
    #     ## 按下键
    #     #client.send("Input.dispatchKeyEvent", {
    #     #    "type": "keyDown",
    #     #    "text": char
    #     #})
        
    #     # 字符输入
    #     client.send("Input.dispatchKeyEvent", {
    #         "type": "char",
    #         "text": char
    #     })
        
    #     ## 释放键
    #     #client.send("Input.dispatchKeyEvent", {
    #     #    "type": "keyUp",
    #     #    "text": char
    #     #})
        
    #     # 每个字符之间的随机延迟
    #     page.wait_for_timeout(random.randint(10, 50))
    system = platform.system()
    
    if system == "Darwin":  # macOS
        # 在 macOS 上使用 Command+A (Meta+A)
        page.keyboard.press("Meta+a")
    else:  # Windows 和 Linux/Ubuntu
        # 在 Windows 和 Linux 上使用 Control+A
        page.keyboard.press("Control+a")
    page.keyboard.press('Backspace')
    page.wait_for_timeout(2500)

    for char in content:
        page.keyboard.type(char, delay=random.randint(10, 50))

    # 执行完后暂停2秒
    page.wait_for_timeout(2000)

    return page, client

# 滑动
def scroll(page, client, delta_x, delta_y):
    viewport_size = page.viewport_size
    center_x = viewport_size["width"] / 2
    center_y = viewport_size["height"] / 2
    client.send("Input.dispatchMouseEvent", {
        "type": "mouseWheel",
        "x": center_x,
        "y": center_y,
        "deltaX": delta_x, # 正值向下滚动，负值向上滚动
        "deltaY": delta_y  # 正值向下滚动，负值向上滚动
    })
    return page, client

# 滑动(固定区域)
def scroll_menu(page, client, x, y, delta_x, delta_y):
    print("x,y,delta_y:", x, y, delta_y)
    cdp_mouse_move(client, x, y, steps=20)
    client.send("Input.dispatchMouseEvent", {
        "type": "mouseWheel",
        "x": x,
        "y": y,
        "deltaX": delta_x,
        "deltaY": delta_y  # 正值向下滚动，负值向上滚动
    })
    return page, client

# 拉拽
def drag(page, client, x1, y1, x2, y2, steps=20):
    """
    page - Playwright页面对象
    client - CDP会话
    x1, y1 - 起始坐标
    x2, y2 - 目标坐标
    steps - 拖拽过程的步数
    """
    import time
    
    # 1. 移动鼠标到起始位置
    cdp_mouse_move(client, x1, y1, steps=steps)
    page.wait_for_timeout(100)
    
    # 2. 按下鼠标左键
    client.send("Input.dispatchMouseEvent", {
        "type": "mousePressed",
        "x": x1,
        "y": y1,
        "button": "left",
        "clickCount": 1
    })
    page.wait_for_timeout(100)
    
    # 3. 分步移动到目标位置
    delta_x = (x2 - x1) / steps
    delta_y = (y2 - y1) / steps
    
    for step in range(1, steps + 1):
        current_x = x1 + delta_x * step
        current_y = y1 + delta_y * step
        
        client.send("Input.dispatchMouseEvent", {
            "type": "mouseMoved",
            "x": current_x,
            "y": current_y,
            "button": "left",  # 拖拽时保持按下状态
            "buttons": 1       # 表示左键被按下
        })
        
        # 添加小延迟使拖拽更自然
        time.sleep(0.01)  # 10毫秒延迟
    
    # 4. 在目标位置释放鼠标
    client.send("Input.dispatchMouseEvent", {
        "type": "mouseReleased",
        "x": x2,
        "y": y2,
        "button": "left",
        "clickCount": 1
    })
    
    page.wait_for_timeout(2000)  # 等待拖拽效果完成
    return page, client

# 等待
def wait(page, client, time):
    page.wait_for_timeout(time)  # 等待拖拽效果完成
    return page, client

# 解析动作类型
def parse_action_type(action_str):
    action_str = action_str.strip()
    if action_str.startswith('click('):
        return 'LeftClick'
    elif action_str.startswith('doubleclick('):
        return 'DoubleClick'
    elif action_str.startswith('hover('):
        return 'Hover'
    elif action_str.startswith('select('):
        return 'Select'
    elif action_str.startswith('drag('):
        return 'Drag'
    elif action_str.startswith('hotkey(') or action_str.startswith('hotkey '):
        return 'Hotkey'
    elif action_str.startswith('type('):
        return 'Type'
    elif action_str.startswith('stop('):
        return 'Stop'
    elif action_str.startswith('scroll'):
        # 新的动作空间
        if "scroll(" in action_str: 
            if "up" in action_str:
                return 'ScrollUp'
            if "down" in action_str:
                return 'ScrollDown'
            elif "left" in action_str:
                return 'ScrollLeft'
            elif "right" in action_str:
                return 'ScrollRight'
            else:
                print("scroll parse error !")
                exit()
        elif "scrollmenu(" in action_str:
            if "up" in action_str:
                return 'ScrollUpMenu'
            if "down" in action_str:
                return 'ScrollDownMenu'
            else:
                print("scroll parse error !")
                exit()
        else:
            print("scroll parse error !")
            exit()
    elif action_str == 'finish()':
        return 'Finish'
    elif action_str == 'wait()':
        return 'Wait'
    elif action_str == 'call_user()':
        return 'CallUser'
    else:
        return 'Unknown'

def _normalize_start_box_tokens(s: str) -> str:
    # 把 start_box='<|box_start|>(910,330)<|box_end|>' 变成 start_box='(910,330)'
    return re.sub(
        r"start_box\s*=\s*'(<\|box_start\|>)?\((\d+)\s*,\s*(\d+)\)(<\|box_end\|>)?'",
        r"start_box='(\2,\3)'",
        s
    )

# 解析动作
def parse_action(action_str):
    response = action_str.strip()
    response = _normalize_start_box_tokens(response)
    print(response)
    try:
        if "type(content" in response and "start_box" in response:
            ### "Action: type(content='2544', start_box='(523,501)')"
            click_point = extract_between_keywords(response, "start_box='(", ")'")[0]
            coords = click_point.split(",")
            if len(coords) == 2:
                cx, cy = coords
            else:
                cx, _, __, cy = coords
            cx = int(cx)
            cy = int(cy)
            type_value = extract_between_keywords(response,"content='", "', start_box")
            if len(type_value) == 0:
                type_value = extract_between_keywords(response,"content='", "”, start_box")
            action = {"name": "Click And Type", "coordinate": [cx, cy], "value": type_value[0]}

        elif "click(start_box=" in response:
            #Action: click(start_box='(189,501)')
            click_point = extract_between_keywords(response, "start_box='(", ")'")[0]
            coords = click_point.split(",")
            if len(coords) == 2:
                cx, cy = coords
            else:
                cx, _, __, cy = coords
            cx = int(cx)
            cy = int(cy)
            # print("click coordinate:", cx, cy)
            action = {"name": "LeftClick", "coordinate": [cx, cy]}

        elif "doubleclick(start_box=" in response:
            click_point = extract_between_keywords(response, "start_box='(", ")'")
            cx, cy = click_point[0].split(",")
            cx = int(cx)
            cy = int(cy)
            action = {"name": "DoubleClick", "coordinate": [cx, cy]}

        elif "hover(start_box=" in response:
            click_point = extract_between_keywords(response, "start_box='(", ")'")[0]
            coords = click_point.split(",")
            if len(coords) == 2:
                cx, cy = coords
            else:
                cx, _, __, cy = coords
            cx = int(cx)
            cy = int(cy)
            # print("click coordinate:", cx, cy)
            action = {"name": "Hover", "coordinate": [cx, cy]}

        elif "scrollmenu(" in response:
            # 正则匹配：同时提取4个坐标数字 和 direction的值
            # 模式匹配：(数字,数字),(数字,数字) ... direction='up或down'
            pattern = r"\((\d+),(\d+)\),\((\d+),(\d+)\).*?direction='(up|down)'"
            match = re.search(pattern, response)
            if match:
                # 1. 提取坐标并转为整数
                x1, y1, x2, y2 = map(int, match.group(1, 2, 3, 4))
                # 2. 提取方向
                direction = match.group(5)
                # 3. 计算中心点
                cx = int((int(x1) + int(x2)) / 2) 
                cy = int((int(y1) + int(y2)) / 2) 
                # 4. 根据方向生成 Action
                action_name = "ScrollUpMenu" if direction == "up" else "ScrollDownMenu"
                action = {"name": action_name, "coordinate": [cx, cy], "bbox": [x1, y1, x2, y2]}
            else:
                print("scrollmenu parse error !")
                exit()

        elif "scroll(" in response:
            if "up" in response:
                action = {"name": "ScrollUp"}
            elif "down" in response:
                action = {"name": "ScrollDown"}
            elif "left" in response:
                action = {"name": "ScrollLeft"}
            elif "right" in response:
                action = {"name": "ScrollRight"}
            else:
                print("scroll parse error !")
                exit()

        elif "hotkey" in response:
            hotkey_value = extract_between_keywords(response, "key=\"", "\")")
            if hotkey_value is not None and len(hotkey_value) > 0:
                hotkey_value = hotkey_value[0].replace(".", "")
            else:
                hotkey_value = extract_between_keywords(response, "\"", "\"")[0].replace(".", "")
            print(f"hotkey_value:{hotkey_value}")
            action = {"name": "HotKey", "value": hotkey_value}

        elif "drag" in response:
            click_point = extract_between_keywords(response, "start_box='(", ")'")
            c1, c2 = click_point[0].split("),(")
            x1, y1 = c1.split(",")
            x2, y2 = c2.split(",")
            x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
            action = {"name": "Drag", "bbox":[x1, y1, x2, y2]}

        elif "finish()" in response:
            action = {"name": "Finish"}

        elif "call_user()" in response:
            action = {"name": "CallUser"}

        elif "wait()" in response:
            action = {"name": "Wait"}

        elif "table_get_data()" in response:
            action = {"name": "TableGetData"}

        elif "table_get_data_finish" in response:
            action = {"name": "TableGetDataFinish"}

        else:
            action = {"name": "Unkwown"}

    except:
        print("parse error")
        action = {"name": "Unkwown"}

    return action

# 执行动作
def excute_action(page, client, action, get_table_data_flag):
    name = action["name"]

    # 记录动作执行前的所有页面
    old_pages = set(page.context.pages)

    viewport_size = page.viewport_size
    page_height = viewport_size["height"] // 3
    if get_table_data_flag == True:
        page_height = page.evaluate("() => document.documentElement.scrollHeight")
        page_height = page_height // 3

    if name == "Click And Type":
        content = action["value"]
        cx,cy = action["coordinate"]
        page, client = click_type(page, client, cx, cy, content, time_wait=1000)

    elif name == "LeftClick":
        cx,cy = action["coordinate"]
        page, client = click(page, client, cx, cy, time_wait=1000)

    elif name == "DoubleClick":
        cx,cy = action["coordinate"]
        page, client = doubleclick(page, client, cx, cy, time_wait=1000)

    elif name == "Hover":
        cx,cy = action["coordinate"]
        cdp_mouse_move(client, cx, cy, steps=20)

    elif name == "HotKey":
        hot_key_value = action["value"]
        page, client = hotkey(page, client, hot_key_value)

    elif "Scroll" in name:
        if name in ["ScrollUp", "ScrollDown", "ScrollLeft", "ScrollRight"]:
            if name == "ScrollUp":
                delta_x = 0
                delta_y = -(viewport_size["height"] - 100)
            elif name == "ScrollDown":
                delta_x = 0
                delta_y = viewport_size["height"] - 100
            elif name == "ScrollLeft":
                delta_x = -(viewport_size["width"] - 100)
                delta_y = 0
            elif name == "ScrollRight":
                delta_x = viewport_size["width"] - 100
                delta_y = 0
            # scorll_screen_down(page, client, viewport_size["height"])
            page, client = scroll(page, client, delta_x, delta_y)  

        elif name in ["ScrollUpMenu", "ScrollDownMenu"]:
            if name == "ScrollUpMenu":
                cx,cy = action["coordinate"]
                x1, y1, x2, y2 = action["bbox"]
                height = y2 - y1
                delta_x = 0
                delta_y = -(height * 0.9)
            elif name == "ScrollDownMenu":
                cx,cy = action["coordinate"]
                x1, y1, x2, y2 = action["bbox"]
                height = y2 - y1
                delta_x = 0
                delta_y = height * 0.9
            page, client = scroll_menu(page, client, cx, cy, delta_x, delta_y)

        else:
            print(f"parse error: {name}")
            exit()

    elif name == "Drag":
        x1, y1, x2, y2 = action["bbox"]
        page, client = drag(page, client, x1, y1, x2, y2, steps=20)

    elif name == "Wait":
        page, client = wait(page, client, time=3000)

    elif name == "TableGetData":
        print("TableGetData")

    elif name == "TableGetDataFinish":
        print("TableGetDataFinish")
   
    # 统一检测页面跳转并清理旧页面
    # 计算新增的页面
    current_pages = set(page.context.pages)
    new_pages = current_pages - old_pages
    print("len new pages:", len(list(new_pages)))

    final_page = page
    final_client = client

    # 如果有新页面，返回它；否则返回原页面
    if new_pages:
        new_page = list(new_pages)[0]
        new_page.set_viewport_size({"width": browser_window_size_width, "height": browser_window_size_height})
        new_client = page.context.new_cdp_session(new_page)
        print(f"检测到新页面，正在关闭 {len(old_pages)} 个旧页面...")
        
        # closed_pages = old_pages
        # 最后一页保留，防止新页面打不开导致浏览器关闭
        closed_pages = list(old_pages)[:-1]
        
        for p in closed_pages: 
            try:
                # run_before_unload=False 强制关闭，忽略"是否离开"弹窗
                p.close(run_before_unload=False)
            except Exception as e:
                print(f"关闭旧页面失败: {e}")

        final_page = new_page
        final_client = new_client

    wait_for_rendering_complete(final_page)

    return final_page, final_client

# 等待页面渲染
def wait_for_rendering_complete(page):
    try:
        # 等待页面加载和网络空闲
        page.wait_for_load_state("load", timeout=30000)
        #page.wait_for_load_state("networkidle", timeout=30000)
        page.wait_for_load_state("domcontentloaded", timeout=10000)

        # 简单检查页面状态，如果这个调用成功，页面很可能是稳定的
        is_ready = page.evaluate("() => document.readyState")
        if is_ready != "complete":
            print(f"Warning: document.readyState is {is_ready}, not 'complete'")

        # 然后再尝试执行更复杂的评估
        page.evaluate("""() => {
            return new Promise(resolve => {
                let lastHeight = document.body.scrollHeight;
                let checkCount = 0;
                const interval = setInterval(() => {
                    const currentHeight = document.body.scrollHeight;
                    if (currentHeight === lastHeight || checkCount > 10) {
                        clearInterval(interval);
                        resolve();
                    } else {
                        lastHeight = currentHeight;
                        checkCount++;
                    }
                }, 100);
            });
        }""")

        # 确保有实际内容
        page.wait_for_function("""() => {
            const content = document.body.innerText.trim();
            return content.length > 0;
        }""", timeout=5000)

    except Exception as e:
        print(f"Warning: wait_for_rendering_complete encountered an error: {e}")
        # 如果发生错误，再次尝试等待页面加载
        try:
            page.wait_for_load_state("load", timeout=5000)
        except Exception:
            pass  # 忽略二次等待的错误

# 获取vimc解析元素信息
def get_vimc_elements(page):
    # ② 提取 highlight 元素
    print("🛠️ 执行 highlight_dom_sync 方法...")
    # page.wait_for_timeout(1000)
    # result_handle = page.evaluate_handle("""() => window.__highlight_dom_sync__?.()""")
    # page.wait_for_timeout(10000)
    page.evaluate("""() => {
    window.__highlight_completed__ = false;
    Promise.resolve(window.__highlight_dom_sync__?.())
      .then(result => {
        window.__highlight_result__ = result;
        window.__highlight_completed__ = true;
      });
    }""")
    page.wait_for_timeout(2000)
    try:
        page.wait_for_function("""() => window.__highlight_completed__ === true""", timeout=30000)
        result_handle = page.evaluate_handle("""() => window.__highlight_result__""")
        element_handles = result_handle.get_properties()
        print(f"✨ Highlight 元素数量: {len(element_handles)}")

        highlighted_elements = []
        for idx, handle in element_handles.items():
            try:
                obj = handle.json_value()
                if "attributes" in obj:
                    if "id" in obj["attributes"]:
                        obj["attributes"]["attributes_id"] = obj["attributes"]["id"]
                        del obj["attributes"]["id"]
                highlighted_elements.append(obj)
            except Exception as e:
                print(f"⚠️ 提取第 {idx} 个元素失败：{e}")

        page.evaluate("""() => window.__clear_highlight_dom_sync__?.()""")
        page.wait_for_timeout(1000)
    except Exception as e:
        return []
    return highlighted_elements

def get_url(scribe_path):
    #scribe_path_raw = scribe_path.replace("document_details_parse_", "document_details_").replace("_addthink_fix_aug", "").replace("_addthink_aug", "").replace("_aug_list.json",".json")
    scribe_path_raw = scribe_path.replace("document_details_parse_", "document_details_").replace("_addthink_fix", "").replace("_addthink", "")
    print(scribe_path_raw)
    scribe_items = json.load(open(scribe_path_raw))
    title = scribe_items["title"]
    action_list = scribe_items["actions"]
    #print(action_list[0]["description"])
    if "Navigate to" not in action_list[0]["description"]:
        return None, title
    matchs = extract_between_keywords(action_list[0]["description"], "(", ")")
    if len(matchs) == 0:
        matchs = extract_between_keywords(action_list[0]["description"], "<", ">")
    url = matchs[0].split("?")[0]
    print(url, title)    
    return url, title

def check_url_accessible(cdp_url, url, timeout=5000):
    """检查 URL 是否可访问"""
    with sync_playwright() as p:
        p, browser, context = init_playwright_context(cdp_url)
        page = browser.new_page()
        
        try:
            # response = page.goto(url, timeout=timeout, wait_until='domcontentloaded')
            response = page.goto(url, timeout=timeout, wait_until='commit')
            # 检查响应状态码
            if response and response.status < 400:
                browser.close()
                return True, response.status
            else:
                browser.close()
                return False, response.status if response else None

        except Exception as e:
            browser.close()
            return False, str(e)

class RequestCollector:
    def __init__(self, worker_id=None):
        self.requests = []
        self.worker_id = worker_id
        print(f"[Worker {worker_id}] 🚀 RequestCollector 初始化")
    
    def handle_request(self, request):
        """处理每个请求"""
        # print(f"[Worker {self.worker_id}] 📡 捕获请求: {request.url[:80]}")
        
        try:
            req_data = {
                "timestamp": time.time(),
                "url": request.url,
                "method": request.method,
                "headers": dict(request.headers),
                "resource_type": request.resource_type,
                "post_data": None,
                "raw_post_data": None,
                "json_data": None
            }
            
            # 过滤非 XHR/Fetch 请求
            if request.resource_type not in ["xhr", "fetch"]:
                # print(f"[Worker {self.worker_id}] ⏭️  跳过 {request.resource_type}: {request.url[:60]}")
                return
            
            print(f"[Worker {self.worker_id}] ✅ {request.resource_type.upper()} {request.method}: {request.url[:60]}")
            
            # 处理 POST 数据
            raw = request.post_data_buffer
            if raw:
                req_data["raw_post_data"] = raw.hex()
                print(f"[Worker {self.worker_id}] 📦 POST 数据: {len(raw)} 字节")
                try:
                    text = raw.decode("utf-8")
                    req_data["post_data"] = text
                    print(f"[Worker {self.worker_id}] 📝 POST 文本: {text[:100]}")
                    if text:
                        try:
                            req_data["json_data"] = json.loads(text)
                            print(f"[Worker {self.worker_id}] 🔍 JSON 解析成功")
                        except json.JSONDecodeError as e:
                            print(f"[Worker {self.worker_id}] ⚠️  JSON 解析失败: {e}")
                except UnicodeDecodeError as e:
                    print(f"[Worker {self.worker_id}] ⚠️  UTF-8 解码失败: {e}")
            else:
                print(f"[Worker {self.worker_id}] 📭 无 POST 数据")
            
            # 添加到列表
            self.requests.append(req_data)
            print(f"[Worker {self.worker_id}] ✅ 请求已添加 (总数: {len(self.requests)})")
            
        except Exception as e:
            print(f"[Worker {self.worker_id}] ❌ handle_request 异常: {e}")
            import traceback
            traceback.print_exc()
    
    def save_results(self, save_result_path="capture.json"):
        """保存捕获的结果"""
        output = {
            "capture_time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total_requests": len(self.requests),
            "all_requests": self.requests
        }
        
        with open(save_result_path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=4, ensure_ascii=False)
        
        print("结果已保存到 capture.json")
        return len(self.requests)
    
    def clear(self):
        """清空请求列表"""
        prev_count = len(self.requests)
        self.requests = []
        print(f"[Worker {self.worker_id}] 🧹 清空请求列表 (之前有 {prev_count} 个)")