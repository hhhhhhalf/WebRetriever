import os
import re
import gc
import cv2
import json
import math
import time
import fcntl
import shutil
import logging
import traceback
import multiprocessing as mp
import concurrent.futures
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from difflib import SequenceMatcher

import numpy as np
from PIL import Image, ImageDraw, ImageFont

import web_controller
from utils import OpenaiEngine

# SeeAct imports
from data_utils.prompts import generate_prompt
from data_utils.format_prompt_utils import get_index_from_option_name
from demo_utils.format_prompt import postprocess_action_lmm
# from demo_utils.ranking_model import CrossEncoder, find_topk  # lazy import when ranker_path is set


# =========================
# IO / 目录 / 日志
# =========================
def safe_save_results(base_dir, result_data, visual_data, max_retries=3):
    for attempt in range(max_retries):
        try:
            temp_result_path = f"{base_dir}/.result.json.tmp"
            temp_visual_path = f"{base_dir}/.result_visual.json.tmp"
            with open(temp_result_path, "w", encoding="utf-8") as f:
                json.dump(result_data, f, indent=4, ensure_ascii=False)
            with open(temp_visual_path, "w", encoding="utf-8") as f:
                json.dump(visual_data, f, indent=4, ensure_ascii=False)

            with open(temp_result_path, "r", encoding="utf-8") as f:
                json.load(f)
            with open(temp_visual_path, "r", encoding="utf-8") as f:
                json.load(f)

            os.replace(temp_result_path, f"{base_dir}/result.json")
            os.replace(temp_visual_path, f"{base_dir}/result_visual.json")
            return True
        except Exception as e:
            for tmp_file in [temp_result_path, temp_visual_path]:
                try:
                    if os.path.exists(tmp_file):
                        os.remove(tmp_file)
                except Exception:
                    pass
            if attempt == max_retries - 1:
                print(f"Failed to save results after {max_retries} attempts: {e}")
                return False
            time.sleep(0.1 * (2 ** attempt))
    return False


def safe_create_directory(base_dir, result_file="result.json"):
    lock_file = f"{base_dir}.lock"
    os.makedirs(os.path.dirname(lock_file), exist_ok=True)
    lock = None
    try:
        lock = open(lock_file, "w")
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        if os.path.exists(os.path.join(base_dir, result_file)):
            return False
        if os.path.exists(base_dir):
            shutil.rmtree(base_dir)
        os.makedirs(base_dir, exist_ok=True)
        os.makedirs(f"{base_dir}/trajectory", exist_ok=True)
        os.makedirs(f"{base_dir}/trajectory_visual", exist_ok=True)
        return True
    except BlockingIOError:
        return False
    finally:
        try:
            if lock is not None:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
                lock.close()
        except Exception:
            pass


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


def setup_logger(log_dir, worker_id: int):
    current_date = datetime.now().strftime("%Y%m%d")
    log_filename = f"{log_dir}/worker_{worker_id}_{current_date}.log"
    logger_name = f"worker_{worker_id}"
    logger = logging.getLogger(logger_name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - [Worker %(worker_id)s] [PID %(process)d] - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    class WorkerFilter(logging.Filter):
        def __init__(self, wid):
            self.wid = wid

        def filter(self, record):
            record.worker_id = self.wid
            return True

    os.makedirs(log_dir, exist_ok=True)
    file_handler = logging.FileHandler(log_filename, encoding="utf-8")
    file_handler.setFormatter(formatter)
    file_handler.addFilter(WorkerFilter(worker_id))
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.addFilter(WorkerFilter(worker_id))
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger


# =========================
# Debug 画图
# =========================
def _pick_font():
    possible_fonts = [
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/wqy-microhei/wqy-microhei.ttc",
        "/usr/share/fonts/wqy-zenhei/wqy-zenhei.ttc",
        "/usr/share/fonts/truetype/arphic/uming.ttc",
    ]
    for p in possible_fonts:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, 24)
            except Exception:
                pass
    return ImageFont.load_default()


def save_debug_image(image_path, bbox, point, markdown, action, save_dir):
    show_image = cv2.imread(image_path)
    if show_image is None:
        return

    if bbox is not None:
        try:
            left, top, right, bottom = map(int, bbox)
            cv2.rectangle(show_image, (left, top), (right, bottom), (0, 0, 255), 4)
        except Exception:
            pass

    if point is not None:
        try:
            cx, cy = int(point[0]), int(point[1])
            cv2.circle(show_image, (cx, cy), 4, (0, 0, 255), -1)
        except Exception:
            pass

    pil_img = Image.fromarray(cv2.cvtColor(show_image, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil_img)
    font = _pick_font()

    text_x, text_y = 10, 10
    padding = 5

    md_bbox = draw.textbbox((text_x, text_y), markdown, font=font)
    draw.rectangle(
        [md_bbox[0] - padding, md_bbox[1] - padding, md_bbox[2] + padding, md_bbox[3] + padding],
        fill=(255, 255, 255, 200),
    )
    draw.text((text_x, text_y), markdown, font=font, fill=(0, 128, 0))

    action_y = text_y + 35
    act_bbox = draw.textbbox((text_x, action_y), action, font=font)
    draw.rectangle(
        [act_bbox[0] - padding, act_bbox[1] - padding, act_bbox[2] + padding, act_bbox[3] + padding],
        fill=(255, 255, 255, 200),
    )
    draw.text((text_x, action_y), action, font=font, fill=(0, 0, 255))

    result_img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
    os.makedirs(save_dir, exist_ok=True)
    out_path = os.path.join(save_dir, os.path.basename(image_path))
    cv2.imwrite(out_path, result_img)


# =========================
# KeepAlive（避免 sync + thread greenlet 问题）
# =========================
def call_with_keepalive(executor, fn, keepalive, page, poll_s=0.2):
    fut = executor.submit(fn)
    while True:
        try:
            return fut.result(timeout=poll_s)
        except concurrent.futures.TimeoutError:
            keepalive.tick(page)
            continue


class KeepAliveTicker:
    def __init__(self, interval_s=10, mode="evaluate"):
        self.interval_s = interval_s
        self.mode = mode
        self._last = 0.0

    def tick(self, page):
        now = time.time()
        if (now - self._last) < self.interval_s:
            return
        self._last = now
        try:
            if page is None or page.is_closed():
                return
            if self.mode in ("evaluate", "both"):
                page.evaluate("() => 1")
            if self.mode in ("mouse", "both"):
                try:
                    page.mouse.move(1, 1)
                    page.mouse.move(0, 0)
                except Exception:
                    pass
        except Exception:
            pass


# =========================
# 坐标/页面指标
# =========================
def get_scroll_offsets(page) -> Tuple[int, int]:
    try:
        d = page.evaluate("() => ({x: window.scrollX || 0, y: window.scrollY || 0})")
        return int(d.get("x", 0)), int(d.get("y", 0))
    except Exception:
        return 0, 0


def get_page_metrics(page) -> Tuple[int, int]:
    try:
        vs = getattr(page, "viewport_size", None)
        if isinstance(vs, dict) and "width" in vs:
            total_width = int(vs["width"])
        else:
            total_width = int(page.evaluate("() => window.innerWidth || document.documentElement.clientWidth || 1280"))
    except Exception:
        total_width = 1280

    try:
        total_height = int(
            page.evaluate(
                """() => Math.max(
                    document.documentElement.scrollHeight,
                    document.body.scrollHeight,
                    document.documentElement.clientHeight
                )"""
            )
        )
    except Exception:
        total_height = 2000

    return total_width, total_height


def page_bbox_to_viewport_bbox(bbox_page_xywh: List[float], scroll_x: int, scroll_y: int) -> List[int]:
    x, y, w, h = bbox_page_xywh
    x1 = int(x - scroll_x)
    y1 = int(y - scroll_y)
    x2 = int(x + w - scroll_x)
    y2 = int(y + h - scroll_y)
    return [x1, y1, x2, y2]


def page_point_to_viewport_point(px: int, py: int, scroll_x: int, scroll_y: int) -> Tuple[int, int]:
    return int(px - scroll_x), int(py - scroll_y)


def screenshot_batch_clip(page, save_path: str, y_start: int, y_end: int, pad: int = 200, min_h: int = 1144):
    total_w, total_h = get_page_metrics(page)

    clip_start = min(max(0, total_h - min_h), max(0, y_start - pad))
    clip_end = min(total_h, max(y_end + pad, clip_start + min_h))
    clip_h = max(1, clip_end - clip_start)

    clip = {"x": 0, "y": int(clip_start), "width": int(total_w), "height": int(clip_h)}
    os.makedirs(os.path.dirname(save_path), exist_ok=True)

    try:
        page.screenshot(
            path=save_path,
            clip=clip,
            full_page=True,
            type="jpeg",
            quality=95,
            timeout=20000,
        )
        return True, int(clip_start), int(clip_h), total_w, total_h
    except Exception:
        return False, int(clip_start), int(clip_h), total_w, total_h


# =========================
# SeeAct 源代码对齐：文本清洗/描述/元素抽取（同步版）
# =========================
def remove_extra_eol(text):
    text = (text or "").replace("\n", " ")
    return re.sub(r"\s{2,}", " ", text)


def get_first_line(s):
    first_line = (s or "").split("\n")[0]
    tokens = first_line.split()
    if len(tokens) > 8:
        return " ".join(tokens[:8]) + "..."
    return first_line


def get_element_description_sync(element, tag_name, role_value, type_value):
    """
    与你贴的 async get_element_description 逻辑对齐（同步实现）。
    """
    salient_attributes = [
        "alt",
        "aria-describedby",
        "aria-label",
        "aria-role",
        "input-checked",
        "label",
        "name",
        "option_selected",
        "placeholder",
        "readonly",
        "text-value",
        "title",
        "value",
    ]

    parent_value = "parent_node: "
    try:
        parent_locator = element.locator("xpath=..")
        num_parents = parent_locator.count()
        if num_parents > 0:
            parent_text = (parent_locator.inner_text(timeout=0) or "").strip()
            if parent_text:
                parent_value += parent_text
    except Exception:
        pass

    parent_value = remove_extra_eol(get_first_line(parent_value)).strip()
    if parent_value == "parent_node:":
        parent_value = ""
    else:
        parent_value += " "

    if tag_name == "select":
        text1 = "Selected Options: "
        text2 = ""
        text3 = " - Options: "
        text4 = ""

        try:
            text2 = element.evaluate("select => select.options[select.selectedIndex].textContent", timeout=0)
        except Exception:
            text2 = ""

        if text2:
            try:
                options = element.evaluate(
                    "select => Array.from(select.options).map(option => option.text)",
                    timeout=0,
                )
                text4 = " | ".join(options or [])
            except Exception:
                text4 = ""

            if not text4:
                try:
                    text4 = element.text_content(timeout=0) or ""
                except Exception:
                    text4 = ""
                if not text4:
                    try:
                        text4 = element.inner_text(timeout=0) or ""
                    except Exception:
                        text4 = ""

            return parent_value + text1 + remove_extra_eol(text2.strip()) + text3 + text4

    input_value = ""
    none_input_type = ["submit", "reset", "checkbox", "radio", "button", "file"]

    if tag_name in ("input", "textarea"):
        if role_value not in none_input_type and type_value not in none_input_type:
            try:
                text2 = element.input_value(timeout=0)
            except Exception:
                text2 = ""
            if text2:
                input_value = 'input value="' + text2 + '" '

    try:
        text_content = element.text_content(timeout=0)
    except Exception:
        text_content = ""
    text = (text_content or "").strip()
    if text:
        text = remove_extra_eol(text)
        if len(text) > 80:
            try:
                text_content_in = element.inner_text(timeout=0)
            except Exception:
                text_content_in = ""
            text_in = (text_content_in or "").strip()
            if text_in:
                return input_value + remove_extra_eol(text_in)
        return input_value + text

    text1 = ""
    for attr in salient_attributes:
        try:
            attribute_value = element.get_attribute(attr, timeout=0)
        except Exception:
            attribute_value = None
        if attribute_value:
            text1 += f'{attr}="' + attribute_value.strip() + '" '

    text = (parent_value + text1).strip()
    if text:
        return input_value + remove_extra_eol(text.strip())

    first_child_locator = element.locator("xpath=./child::*[1]")
    try:
        num_childs = first_child_locator.count()
    except Exception:
        num_childs = 0

    if num_childs > 0:
        for attr in salient_attributes:
            try:
                attribute_value = first_child_locator.get_attribute(attr, timeout=0)
            except Exception:
                attribute_value = None
            if attribute_value:
                text1 += f'{attr}="' + attribute_value.strip() + '" '

        text = (parent_value + text1).strip()
        if text:
            return input_value + remove_extra_eol(text.strip())

    return None


def _xpath_for_locator_sync(locator):
    """
    源代码没有 xpath 字段，但你希望用于去重/调试；这里用 evaluate 构造一个近似 xpath。
    注意：这不会影响 SeeAct 的核心提取逻辑，只用于记录。
    """
    try:
        return locator.evaluate(
            """(el) => {
                function xpathFor(el){
                  if (!el || el.nodeType !== 1) return '';
                  if (el.id) return `//*[@id="${el.id}"]`;
                  const parts = [];
                  while (el && el.nodeType === 1) {
                    let nb = 0, idx = 0;
                    const siblings = el.parentNode ? el.parentNode.childNodes : [];
                    for (let i = 0; i < siblings.length; i++) {
                      const sib = siblings[i];
                      if (sib.nodeType === 1 && sib.nodeName === el.nodeName) {
                        nb++;
                        if (sib === el) idx = nb;
                      }
                    }
                    const tag = el.nodeName.toLowerCase();
                    parts.unshift(nb > 1 ? `${tag}[${idx}]` : tag);
                    el = el.parentNode;
                  }
                  return '/' + parts.join('/');
                }
                return xpathFor(el);
            }""",
            timeout=0,
        ) or ""
    except Exception:
        return ""


def get_element_data_sync(element, tag_name, page_scroll_xy: Tuple[int, int]):
    """
    对齐你贴的 async get_element_data 返回信息，同时补齐 page 坐标 bbox（用于 clip）。
    返回一个 dict，字段固定，避免你之前那种“结构错位”：
      {
        "center_view": (cx,cy)                 # viewport center（用于 seen_elements 去重）
        "desc": description                    # 源代码 description
        "tag_head": tag_head                   # 源代码 tag_head（含 role/type）
        "real_tag": real_tag_name              # 源代码 real_tag
        "bbox_view_xyxy": [x1,y1,x2,y2]        # 源代码 box_model（viewport）
        "bbox_page_xywh": [x,y,w,h]            # viewport bbox + scroll 转 page xywh
        "locator": element                     # selector/locator
        "xpath": "..."                         # 仅用于调试
      }
    """
    tag_name_list = ["a", "button", "input", "select", "textarea", "adc-tab"]

    try:
        if element.is_hidden(timeout=0) or element.is_disabled(timeout=0):
            return None
    except Exception:
        pass

    tag_head = ""
    real_tag_name = ""

    if tag_name in tag_name_list:
        tag_head = tag_name
        real_tag_name = tag_name
    else:
        try:
            real_tag_name = element.evaluate("element => element.tagName.toLowerCase()", timeout=0) or ""
        except Exception:
            real_tag_name = ""
        if real_tag_name in tag_name_list:
            return None
        tag_head = real_tag_name

    try:
        role_value = element.get_attribute("role", timeout=0)
    except Exception:
        role_value = None
    try:
        type_value = element.get_attribute("type", timeout=0)
    except Exception:
        type_value = None

    description = get_element_description_sync(element, real_tag_name, role_value, type_value)
    if not description:
        return None

    # 源代码：bounding_box() -> viewport x,y,w,h
    try:
        rect = element.bounding_box() or {"x": 0, "y": 0, "width": 0, "height": 0}
    except Exception:
        rect = {"x": 0, "y": 0, "width": 0, "height": 0}

    if role_value:
        tag_head += ' role="' + role_value + '"'
    if type_value:
        tag_head += ' type="' + type_value + '"'

    x1 = float(rect["x"])
    y1 = float(rect["y"])
    w = float(rect["width"])
    h = float(rect["height"])
    x2 = x1 + w
    y2 = y1 + h

    center_point = ((x1 + x2) / 2.0, (y1 + y2) / 2.0)
    sx, sy = page_scroll_xy
    bbox_page_xywh = [x1 + sx, y1 + sy, w, h]  # page 坐标（关键：clip/排序/box_token）

    return {
        "center_view": center_point,
        "desc": description,
        "tag_head": tag_head,
        "real_tag": real_tag_name,
        "bbox_view_xyxy": [x1, y1, x2, y2],
        "bbox_page_xywh": bbox_page_xywh,
        "locator": element,
        "xpath": _xpath_for_locator_sync(element),
    }


def get_interactive_elements_with_playwright_sync(page):
    """
    与你贴的 async get_interactive_elements_with_playwright 等价（同步实现）。
    核心保持不变：
    - selector 列表一致
    - 遍历 locator.count() / nth(i) 一致
    - get_element_data 逻辑一致
    - seen_elements 使用 center_point 去重一致（viewport center）
    """
    interactive_elements_selectors = [
        "a", "button",
        "input",
        "select", "textarea", "adc-tab",
        "[role=\"button\"]", "[role=\"radio\"]", "[role=\"option\"]", "[role=\"combobox\"]",
        "[role=\"textbox\"]",
        "[role=\"listbox\"]", "[role=\"menu\"]",
        "[type=\"button\"]", "[type=\"radio\"]", "[type=\"combobox\"]", "[type=\"textbox\"]", "[type=\"listbox\"]",
        "[type=\"menu\"]",
        "[tabindex]:not([tabindex=\"-1\"])", "[contenteditable]:not([contenteditable=\"false\"])",
        "[onclick]", "[onfocus]", "[onkeydown]", "[onkeypress]", "[onkeyup]", "[checkbox]",
        "[aria-disabled=\"false\"],[data-link]",
    ]

    # 重要：对齐源代码的“同一时刻”的 scroll，用于把 viewport bbox 转 page bbox
    sx, sy = get_scroll_offsets(page)

    seen_elements = set()
    out = []

    for selector in interactive_elements_selectors:
        locator = page.locator(selector)
        try:
            element_count = locator.count()
        except Exception:
            continue

        for index in range(element_count):
            element = locator.nth(index)
            tag_name = selector.replace(':not([tabindex="-1"])', "")
            tag_name = tag_name.replace(':not([contenteditable="false"])', "")

            data = get_element_data_sync(element, tag_name, page_scroll_xy=(sx, sy))
            if not data:
                continue

            if data["center_view"] in seen_elements:
                continue
            seen_elements.add(data["center_view"])
            out.append(data)

    return out


# =========================
# Select 行为：对齐你贴的 select_option（同步版）
# =========================
def _get_tag_name(loc) -> str:
    try:
        return (loc.evaluate("el => el.tagName.toLowerCase()", timeout=1000) or "").strip()
    except Exception:
        return ""

def select_option_sync(selector_locator, value: str):
    best_option = [-1, "", -1.0]
    opt_loc = selector_locator.locator("option")
    n = 0
    try:
        n = opt_loc.count()
    except Exception:
        n = 0

    for i in range(n):
        try:
            option_text = opt_loc.nth(i).inner_text()
        except Exception:
            option_text = ""
        similarity = SequenceMatcher(None, option_text, value).ratio()
        if similarity > best_option[2]:
            best_option = [i, option_text, similarity]

    selector_locator.select_option(index=best_option[0], timeout=10000)
    return remove_extra_eol(best_option[1]).strip()


# =========================
# 可视化：用 page bbox 映射回 viewport 画框
# =========================
def visualize_all_elements_viewport(image_path, elements, scroll_x: int, scroll_y: int, save_path, max_draw=200):
    img = cv2.imread(image_path)
    if img is None:
        return
    for i, el in enumerate(elements[:max_draw]):
        bbox_page = el["bbox_page_xywh"]  # [x,y,w,h] in page
        x1, y1, x2, y2 = page_bbox_to_viewport_bbox(bbox_page, scroll_x, scroll_y)
        cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 1)
        cv2.putText(img, str(i), (x1, y1 - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1, cv2.LINE_AA)
    cv2.imwrite(save_path, img)


# =========================
# Ranker input + choices
# =========================
def format_ranking_input(elements, task, previous_actions):
    # 这里按你之前的格式保留：用 real_tag 作为 element[-1] 的等价
    converted_elements = []
    for i, e in enumerate(elements):
        tag = e["real_tag"]
        desc = e["desc"] or ""
        if len(desc.split()) >= 20:
            desc = " ".join(desc.split()[:20]) + "..."
        head = f'<{tag} id="{i}">' if tag != "a" else f'<link id="{i}">'
        tail = f"</{tag}>" if tag != "a" else f"</link>"
        converted_elements.append(head + desc + tail)

    query = f"task is: {task}\nPrevious actions: {'; '.join(previous_actions[-3:])}"
    return [[query, doc] for doc in converted_elements]


def _format_choices_like_seeact(elements, candidate_ids, clip_start_y: int):
    """
    choices 的 bbox_in_clip 用 page bbox 映射到 clip 局部坐标（与“full_page+clip”一致）。
    """
    choices = []
    for idx in candidate_ids:
        e = elements[idx]
        t = (e["desc"] or "").strip().replace("\n", " ")
        if len(t) > 120:
            t = t[:120] + "..."
        x, y, w, h = e["bbox_page_xywh"]
        bx = int(x)
        by = int(y - clip_start_y)
        bw = int(w)
        bh = int(h)
        tag = e["real_tag"]
        desc = f"tag={tag}; text={t}; bbox_in_clip=({bx},{by},{bw},{bh})"
        choices.append((str(idx), desc))
    return choices


def _center_page_tuple(e) -> Tuple[int, int]:
    x, y, w, h = e["bbox_page_xywh"]
    return int(x + w / 2), int(y + h / 2)


def _box_token_point(x: int, y: int) -> str:
    return f"'<|box_start|>({x},{y})<|box_end|>'"


# =========================
# Action string（用于记录/执行）：保留 box_token + element_id
# =========================
def _action_from_seeact(target_action: str, target_value: str, el, chosen_idx: int) -> str:
    a = (target_action or "").strip().upper()

    if a == "TERMINATE":
        return "finish()"
    if a == "PRESS ENTER":
        return "hotkey(key='Enter')"

    if a in ["SCROLL", "SCROLL UP", "SCROLL DOWN", "SCROLL LEFT", "SCROLL RIGHT"]:
        if "UP" in a:
            return "scroll(direction='up')"
        if "DOWN" in a:
            return "scroll(direction='down')"
        if "LEFT" in a:
            return "scroll(direction='left')"
        if "RIGHT" in a:
            return "scroll(direction='right')"
        return "scroll(direction='down')"

    if el is None or chosen_idx < 0:
        return "stop(reason='no_target_element')"

    px, py = _center_page_tuple(el)

    if a == "CLICK":
        return f"click(start_box={_box_token_point(px, py)})"
    if a == "TYPE":
        v = (target_value or "").replace("\\", "\\\\").replace("'", "\\'")
        return f"type(content='{v}', start_box={_box_token_point(px, py)})"
    if a == "SELECT":
        v = (target_value or "").replace("\\", "\\\\").replace("'", "\\'")
        # value 可能为空；为空则只点击打开
        return f"select(content='{v}', start_box={_box_token_point(px, py)})"
    if a == "HOVER":
        return f"hover(start_box={_box_token_point(px, py)})"

    return "stop(reason='unknown_target_action')"


# =========================
# Action 解析（用于执行）
# =========================
def _extract_xy_from_start_box(s: str):
    m = re.search(r"start_box\s*=\s*'<?\|box_start\|>\((\-?\d+),(\-?\d+)\)<\|box_end\|>'", s)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r"start_box\s*=\s*'\((\-?\d+),(\-?\d+)\)'", s)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None


def _extract_content(s: str) -> str:
    m = re.search(r"content\s*=\s*'([^']*)'", s)
    return m.group(1) if m else ""


def parse_action_type_local(action_str: str) -> str:
    a = action_str.strip()
    if a.startswith("click("):
        return "LeftClick"
    if a.startswith("hover("):
        return "Hover"
    if a.startswith("select("):
        return "Select"
    if a.startswith("type("):
        return "Type"
    if a.startswith("hotkey(") or a.startswith("hotkey "):
        return "Hotkey"
    if a.startswith("scroll("):
        if "up" in a:
            return "ScrollUp"
        if "down" in a:
            return "ScrollDown"
        if "left" in a:
            return "ScrollLeft"
        if "right" in a:
            return "ScrollRight"
        return "ScrollDown"
    if a == "finish()":
        return "Finish"
    if a.startswith("stop("):
        return "Stop"
    if a == "wait()":
        return "Wait"
    if a == "call_user()":
        return "CallUser"
    return "Unknown"


def parse_action_local(action_str: str) -> Dict[str, Any]:
    """
    给 web_controller 的最小兼容 dict（仅用于 fallback）。
    """
    s = action_str.strip()
    if s.startswith("type("):
        xy = _extract_xy_from_start_box(s)
        val = _extract_content(s)
        if xy is not None:
            return {"name": "Click And Type", "page_coordinate": [xy[0], xy[1]], "value": val}
        return {"name": "Unkwown"}
    if s.startswith("click("):
        xy = _extract_xy_from_start_box(s)
        if xy is not None:
            return {"name": "LeftClick", "page_coordinate": [xy[0], xy[1]]}
        return {"name": "Unkwown"}
    if s.startswith("hover("):
        xy = _extract_xy_from_start_box(s)
        if xy is not None:
            return {"name": "Hover", "page_coordinate": [xy[0], xy[1]]}
        return {"name": "Unkwown"}
    if s.startswith("select("):
        xy = _extract_xy_from_start_box(s)
        if xy is not None:
            return {"name": "Select", "page_coordinate": [xy[0], xy[1]], "value": _extract_content(s)}
        return {"name": "Unkwown"}
    if s.startswith("scroll("):
        if "up" in s:
            return {"name": "ScrollUp"}
        if "down" in s:
            return {"name": "ScrollDown"}
        if "left" in s:
            return {"name": "ScrollLeft"}
        if "right" in s:
            return {"name": "ScrollRight"}
        return {"name": "ScrollDown"}
    if s.startswith("hotkey(") or s.startswith("hotkey "):
        m = re.search(r"key\s*=\s*['\"]([^'\"]+)['\"]", s)
        return {"name": "HotKey", "value": (m.group(1) if m else "Enter")}
    if s == "finish()":
        return {"name": "Finish"}
    if s.startswith("stop("):
        return {"name": "Stop"}
    if s == "wait()":
        return {"name": "Wait"}
    if s == "call_user()":
        return {"name": "CallUser"}
    return {"name": "Unkwown"}

def to_seeact_elements(elements_dict: List[Dict[str, Any]]):
    """
    把你当前的 dict element 结构，转换成 SeeAct format_prompt.py 期望的 list/tuple 结构。
    只保证 format_choices / format_ranking_input / demo.py 日志里的 element[-2]/[-1] 能跑通。

    SeeAct 用到的索引：
      - element[1] : 文本/描述
      - element[2] : tag（例如 button/select/input...）
      - element[-1]: real_tag（同上，通常等于 element[2]）
      - element[-2]: selector/locator（用于执行；你脚本执行时自己用 dict，不靠这个）
      - element[0] : (center_x, center_y)（用于排序/clip；demo.py 是这么用的）
    """
    out = []
    for e in elements_dict:
        # center: 用 viewport bbox 的中心点（和原版 element_detail[0] 对齐）
        x1, y1, x2, y2 = e["bbox_view_xyxy"]
        center = ((x1 + x2) / 2.0, (y1 + y2) / 2.0)

        desc = e.get("desc", "") or ""
        tag = e.get("real_tag", "") or ""
        locator = e.get("locator", None)

        # 构造一个最小兼容的 list
        # [0]=center, [1]=desc, [2]=tag, [-2]=locator, [-1]=tag
        out.append([center, desc, tag, locator, tag])
    return out

# 获取所有国内任务并排除已经完成的任务
def get_remaining_domestic_tasks(scribe_json_items, inaccessible_urls, completed_tasks, max_tasks=100):
    domestic_tasks = []
    index = 0

    # 遍历所有任务，确保任务没有完成
    for idx, json_item in enumerate(scribe_json_items):
        website = (json_item.get("website", "") or "").strip()
        if not website.startswith("http"):
            website = "https://" + website

        # 判断是否是国内任务
        is_domestic = website not in inaccessible_urls
        task_index_task_id = f"{json_item['task_index']}_{json_item['task_id']}"

        # 如果是国内任务且没有在completed_tasks中，就添加到待处理任务列表
        if is_domestic:
            index += 1
            if task_index_task_id not in completed_tasks:
                domestic_tasks.append(idx)
            
            # 如果已经收集到足够的任务，停止收集
            if index >= max_tasks:
                break

    return domestic_tasks


# 获取已经完成的任务
def get_completed_tasks(base_dir_root):
    """
    获取所有已完成的任务。检查每个任务文件夹下是否存在 `result.json` 文件。
    """
    completed_tasks = set()
    
    # 遍历 base_dir_root 目录，找到每个任务文件夹
    for root, dirs, files in os.walk(base_dir_root):
        for dir_name in dirs:
            task_folder = os.path.join(root, dir_name)
            result_json_path = os.path.join(task_folder, "result.json")
            
            # 如果 `result.json` 文件存在，认为该任务已完成
            if os.path.exists(result_json_path):
                completed_tasks.add(dir_name)  # 使用任务文件夹的名称作为任务 ID
                
    return completed_tasks


# 任务分配：将剩余任务分配给各个 worker
def distribute_tasks_among_workers(domestic_tasks, num_workers):
    # 将剩余任务分配给 workers
    shards = np.array_split(domestic_tasks, num_workers)
    return [shard.tolist() for shard in shards]

# =========================
# 执行动作：pipeline 对齐（优先 locator.scroll_into_view_if_needed）
# =========================
def execute_action_aligned(page, client, action_str: str, elements: Optional[List[Dict[str, Any]]] = None, eid=None):
    action_type = parse_action_type_local(action_str)
    action_dict = parse_action_local(action_str)

    # Scroll / Hotkey：直接 page API
    if action_type in ("ScrollUp", "ScrollDown", "ScrollLeft", "ScrollRight"):
        try:
            if action_type == "ScrollUp":
                page.mouse.wheel(0, -900)
            elif action_type == "ScrollDown":
                page.mouse.wheel(0, 900)
            elif action_type == "ScrollLeft":
                page.mouse.wheel(-900, 0)
            else:
                page.mouse.wheel(900, 0)
            return page, client, action_dict
        except Exception:
            new_page, new_client = web_controller.excute_action(page, client, action_dict, get_table_data_flag=False)
            return new_page, new_client, action_dict

    if action_type == "Hotkey":
        try:
            key = action_dict.get("value", "Enter")
            page.keyboard.press(key)
            return page, client, action_dict
        except Exception:
            new_page, new_client = web_controller.excute_action(page, client, action_dict, get_table_data_flag=False)
            return new_page, new_client, action_dict

    # 元素动作：严格 locator.scroll_into_view_if_needed()
    if action_type in ("LeftClick", "Hover", "Type", "Select"):
        loc = None
        if elements is not None and eid is not None and 0 <= eid < len(elements):
            loc = elements[eid]["locator"]

        if loc is not None:
            try:
                loc.scroll_into_view_if_needed(timeout=3000)

                if action_type == "LeftClick":
                    loc.click(timeout=10000)
                elif action_type == "Hover":
                    loc.hover(timeout=10000)
                elif action_type == "Type":
                    val = action_dict.get("value", "")
                    try:
                        loc.click(timeout=10000)
                    except Exception:
                        pass
                    # 对齐 benchmark 复现更稳定：覆盖式输入
                    loc.fill(val, timeout=10000)
                elif action_type == "Select":
                    val = action_dict.get("value", "")
                    tag = _get_tag_name(loc)

                    # 原生 <select>：用 select_option
                    if tag == "select" and val:
                        _ = select_option_sync(loc, val)
                        return page, client, action_dict

                    # 非原生：把 SELECT fallback 成 click 打开下拉
                    # 这里不做“选项点击”，只负责打开，让下一步模型再选一次
                    try:
                        loc.click(timeout=10000)
                    except Exception:
                        # 如果 click 不行，退回到坐标执行（你原来的兜底）
                        pass

                    # 可选：等一下让 dropdown 稳定出现
                    time.sleep(0.25)

                    # 关键：返回一个“等价于 click 打开”的 action_dict，便于日志/调试
                    action_dict = {"name": "LeftClick"}  # 或者保留原 action_dict 也行
                    return page, client, action_dict
                return page, client, action_dict
            except Exception:
                pass

        # locator 失败：fallback 坐标执行（尽量不改变 pipeline，只做兜底）
        if "page_coordinate" in action_dict:
            px, py = action_dict["page_coordinate"]
            try:
                page.evaluate("(y) => window.scrollTo(0, y)", max(0, int(py) - 200))
                time.sleep(0.12)
            except Exception:
                pass
            sx, sy = get_scroll_offsets(page)
            vx, vy = page_point_to_viewport_point(int(px), int(py), sx, sy)
            action_dict["coordinate"] = [vx, vy]
            del action_dict["page_coordinate"]

        new_page, new_client = web_controller.excute_action(page, client, action_dict, get_table_data_flag=False)
        return new_page, new_client, action_dict

    # 其他：交给 web_controller
    new_page, new_client = web_controller.excute_action(page, client, action_dict, get_table_data_flag=False)
    return new_page, new_client, action_dict

def execute_action_aligned(
    page,
    client,
    action_str: str,
    elements: Optional[List[Dict[str, Any]]] = None,
    eid: Optional[int] = None,
):
    action_type = parse_action_type_local(action_str)
    action_dict = parse_action_local(action_str)

    # 1) Scroll / Hotkey / Finish / Wait / Stop：直接走 controller（你的实现是完备的）
    if action_type in ("ScrollUp", "ScrollDown", "ScrollLeft", "ScrollRight", "Hotkey", "Finish", "Wait", "Stop"):
        try:
            new_page, new_client = web_controller.excute_action(page, client, action_dict, get_table_data_flag=False)
            return new_page, new_client, action_dict
        except Exception:
            return page, client, action_dict

    # 2) 元素类动作：locator 仅用于 scroll_into_view_if_needed；执行优先 controller
    loc = None
    el = None
    if elements is not None and eid is not None and 0 <= eid < len(elements):
        el = elements[eid]
        loc = el.get("locator", None)

    # 2.1 scroll 对齐（不做 click）
    if loc is not None:
        try:
            loc.scroll_into_view_if_needed(timeout=3000)
            time.sleep(0.05)
        except Exception:
            pass

    # 2.2 把 page_coordinate -> viewport coordinate（你的 controller 吃 action["coordinate"]）
    if "page_coordinate" in action_dict:
        px, py = action_dict["page_coordinate"]
        try:
            page.evaluate("(y) => window.scrollTo(0, y)", max(0, int(py) - 200))
            time.sleep(0.08)
        except Exception:
            pass
        sx, sy = get_scroll_offsets(page)
        vx, vy = page_point_to_viewport_point(int(px), int(py), sx, sy)
        action_dict["coordinate"] = [vx, vy]
        del action_dict["page_coordinate"]

    # -------------------------
    # 3) Select：保留 tag 识别
    # -------------------------
    if action_type == "Select":
        val = action_dict.get("value", "")

        # 3.1 原生 <select> 且有 value：优先走 Playwright select_option
        if loc is not None:
            try:
                tag = _get_tag_name(loc)  # 你之前写过
            except Exception:
                tag = ""

            if tag == "select" and val:
                try:
                    _ = select_option_sync(loc, val)
                    # 这里返回一个更贴近 controller 日志的 action_dict（可选）
                    return page, client, {"name": "Select", "value": val}
                except Exception:
                    # select_option 失败就继续 fallback
                    pass

        # 3.2 非原生下拉 / 或 value 为空：降级为 click 打开（controller 执行）
        keep = {}
        if "coordinate" in action_dict:
            keep["coordinate"] = action_dict["coordinate"]
        action_dict = {"name": "LeftClick", **keep}

        try:
            new_page, new_client = web_controller.excute_action(page, client, action_dict, get_table_data_flag=False)
            return new_page, new_client, action_dict
        except Exception:
            # 最后兜底：Playwright click
            if loc is not None:
                try:
                    loc.click(timeout=10000)
                    return page, client, action_dict
                except Exception:
                    pass
            return page, client, action_dict

    # -------------------------
    # 4) Click / Type / Hover：统一 controller 优先
    # -------------------------
    try:
        new_page, new_client = web_controller.excute_action(page, client, action_dict, get_table_data_flag=False)
        return new_page, new_client, action_dict
    except Exception:
        # 可选兜底：Playwright
        if loc is not None:
            try:
                if action_type == "LeftClick":
                    loc.click(timeout=10000)
                elif action_type == "Hover":
                    loc.hover(timeout=10000)
                elif action_type == "Type":
                    v = action_dict.get("value", "")
                    try:
                        loc.click(timeout=10000)
                    except Exception:
                        pass
                    loc.fill(v, timeout=10000)
                return page, client, action_dict
            except Exception:
                pass
        return page, client, action_dict


# =========================
# Worker 主循环（对齐 pipeline）
# =========================
def run_worker(
    worker_id: int,
    worker_indices: List[int],
    scribe_json_items: List[Dict[str, Any]],
    base_dir_root: str,
    log_dir: str,
    base_url: str,
    port_list: List[int],
    ranker_path: Optional[str] = None,
    top_k: int = 80,
    fixed_choice_batch_size: int = 30,
    max_continuous_no_op: int = 10,
    max_op: int = 50,
    api_url: str = None,
    api_key: str = None,
    model_name: str = "gpt-4o",
):
    logger = setup_logger(log_dir, worker_id)
    logger.info("进程启动")

    url = f"{base_url}:{port_list[worker_id]}"
    logger.info(f"[W{worker_id}] 浏览器端口 {url}")

    generation_model = OpenaiEngine(model=model_name, api_url=api_url, api_key=api_key)

    ranking_model = None
    if ranker_path:
        from demo_utils.ranking_model import CrossEncoder, find_topk
        try:
            import torch
            ranking_model = CrossEncoder(ranker_path, device=torch.device("cpu"), num_labels=1, max_length=512)
            logger.info(f"[Ranker] enabled (CPU): {ranker_path}")
        except Exception as e:
            logger.warning(f"[Ranker] load failed: {e}")
            ranking_model = None

    llm_pool = concurrent.futures.ThreadPoolExecutor(max_workers=2)

    # 创建该进程专用的请求收集器
    request_collector = web_controller.RequestCollector(worker_id=worker_id)

    try:
        p, browser, context = web_controller.init_playwright_context(url)
        if browser is None:
            logger.error(f"[W{worker_id}] 浏览器初始化失败")
            try:
                llm_pool.shutdown(wait=False, cancel_futures=True)
            except Exception:
                pass
            return
    except Exception:
        traceback.print_exc()
        logger.error(f"[W{worker_id}] init_playwright_context 异常")
        try:
            llm_pool.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass
        return

    for json_item_i in worker_indices:
        page = None
        client = None

        try:
            json_item = scribe_json_items[json_item_i]
            task_id = json_item["task_id"]
            task = json_item["confirmed_task"]
            keytra = (json_item.get("keytra", "") or "").strip()
            task_idx = json_item["task_index"]

            if keytra:
                task_for_model = (
                    f"{task}\n"
                    f"[关键路径参考 keytra]\n{keytra}\n"
                    f"[使用规则]\n"
                    f"- keytra 仅为高层参考路径/思路，不是必须严格照做的固定步骤；以页面当前可见的 choices 为准。\n"
                    f"- 如果 keytra 中提到的入口/路径在当前 choices 里找不到，说明该路径此刻不可用："
                    f"请改走其它可用路径（等价入口/相近功能入口/更通用的导航入口）来实现与 keytra“差不多的效果”，"
                    f"而不是执着于 keytra 的原文字或原路径。\n"
                    f"- “其它可用路径”的优先级：语义等价按钮/同类入口 > 菜单/更多/导航栏/分类页 > 搜索框/站内搜索 > 适当滚动后再找。\n"
                    f"- 只有在确认任务目标已达成时才结束，否则持续尝试替代路径。\n"
                )
            else:
                task_for_model = task

            website = (json_item.get("website", "") or "").strip()
            if not website.startswith("http"):
                website = "https://" + website

            folder_name = f"{task_idx}_{task_id}"
            base_dir = os.path.join(base_dir_root, folder_name)
            save_traj_dir = f"{base_dir}/trajectory"
            save_vis_dir = f"{base_dir}/trajectory_visual"

            result_json_path = f"{base_dir}/result.json"
            result_vis_json_path = f"{base_dir}/result_visual.json"
            if os.path.exists(result_json_path) and os.path.exists(result_vis_json_path):
                logger.info(f"[SKIP] exists: {folder_name}")
                continue
            else:
                safe_remove_task_dir(base_dir)

            if not safe_create_directory(base_dir, result_file="result.json"):
                logger.info(f"[SKIP] lock or exists: {folder_name}")
                continue

            try:
                request_collector.clear()
                page = web_controller.open_page(
                    p, browser, context, url, website,
                    request_collector=request_collector,
                    worker_id=worker_id
                )

                print(f"[Worker {worker_id}] 👂 监听器已设置: page.on('request', ...)")
                client = page.context.new_cdp_session(page)
                keepalive_tick = KeepAliveTicker(interval_s=10, mode="both")
                print(f"[Worker {worker_id}] ✅ 页面初始化完成")
            except Exception as e:
                print(f"[Worker {worker_id}] ❌ 页面初始化失败: {e}")
                logger.error(f"任务 {task_id} 页面初始化失败: {e}")
                safe_remove_task_dir(base_dir)
                continue

            reference_length = int(json_item.get("reference_length", 25))
            total_steps = int(math.ceil(reference_length * 2))

            taken_actions: List[str] = []
            thoughts: List[str] = []
            action_desps: List[str] = []
            actions_out: List[str] = []
            history_resps: List[str] = []
            image_path_list: List[str] = []
            urls: List[str] = []

            status = ""
            curr_step = 0
            no_op_count = 0
            op_count = 0

            allowed_actions = {
                "CLICK", "SELECT", "TYPE", "PRESS ENTER", "HOVER", "TERMINATE",
                "SCROLL", "SCROLL UP", "SCROLL DOWN", "SCROLL LEFT", "SCROLL RIGHT",
            }

            while curr_step < total_steps:
                # 1) viewport screenshot（对齐你现有保存方式）
                image_path = f"{save_traj_dir}/{int(curr_step)}.png"
                urls.append(page.url)

                screenshot_success = web_controller.save_screenshot(page, savePath=image_path, timeout_ms=50000)
                if not screenshot_success:
                    status = "FAIL_SAVE_SCREENSHOT_ERROR"
                    break
                image_path_list.append(image_path)
                keepalive_tick.tick(page)

                sx0, sy0 = get_scroll_offsets(page)

                # 2) elements：严格按源代码 selector+bounding_box 提取（无全页扫描增强）
                try:
                    elements = get_interactive_elements_with_playwright_sync(page)
                except Exception as e:
                    elements = []
                    logger.warning(f"get_interactive_elements_with_playwright_sync 异常: {e}")

                visualize_all_elements_viewport(
                    image_path,
                    elements,
                    scroll_x=sx0,
                    scroll_y=sy0,
                    save_path=f"{save_vis_dir}/elements_{curr_step}.png",
                )

                logger.info(f"Time step: {curr_step}  #elements={len(elements)} url={page.url}")

                if len(elements) == 0:
                    status = "FAIL_NO_ELEMENTS"
                    break

                # 3) ranking（可选）
                ranked_ids = list(range(len(elements)))
                if ranking_model is not None and len(elements) > top_k:
                    ranking_input = format_ranking_input(elements, task_for_model, taken_actions)
                    pred_scores = call_with_keepalive(
                        llm_pool,
                        lambda: ranking_model.predict(
                            ranking_input,
                            convert_to_numpy=True,
                            show_progress_bar=False,
                            batch_size=100,
                        ),
                        keepalive_tick,
                        page,
                        poll_s=0.2,
                    )
                    _, topk_indices = find_topk(pred_scores, k=min(top_k, len(elements)))
                    ranked_ids = list(topk_indices)

                # 4) y,x 排序：使用 page bbox（用于 batch clip 与 ground）
                ranked_ids_with_loc = []
                for i in ranked_ids:
                    x, y, w, h = elements[i]["bbox_page_xywh"]
                    ranked_ids_with_loc.append((i, int(y), int(x)))
                ranked_ids_with_loc.sort(key=lambda t: (t[1], t[2]))
                ranked_ids = [t[0] for t in ranked_ids_with_loc]

                num_choices = len(ranked_ids)
                step_length = min(num_choices, fixed_choice_batch_size)

                got_one_answer = False
                target_el = None
                target_action = "CLICK"
                target_value = ""
                chosen_idx = -1
                step_resp = ""

                # 5) 多选 batch：按 page-y 范围做 clip（pipeline 对齐点）
                for multichoice_i in range(0, num_choices, step_length):
                    candidate_ids = ranked_ids[multichoice_i : multichoice_i + step_length]

                    y_start = int(elements[candidate_ids[0]]["bbox_page_xywh"][1])
                    y_end = int(elements[candidate_ids[-1]]["bbox_page_xywh"][1])

                    crop_path = os.path.join(save_traj_dir, f"{int(curr_step)}_{multichoice_i // step_length}_crop.jpg")

                    ok_crop, clip_start_y, _, _, _ = screenshot_batch_clip(
                        page, crop_path, y_start=y_start, y_end=y_end, pad=200, min_h=1144
                    )
                    if not ok_crop or (not os.path.exists(crop_path)):
                        input_image_path = image_path
                        clip_start_y = sy0
                    else:
                        input_image_path = crop_path

                    # 1) 转换 element 结构
                    elements_sa = to_seeact_elements(elements)

                    # 2) 直接用 SeeAct 的 format_choices
                    from demo_utils.format_prompt import format_choices as seeact_format_choices
                    choices = seeact_format_choices(elements_sa, candidate_ids, task_for_model, taken_actions)

                    # 3) prompt 保持不变
                    prompt = generate_prompt(task=task_for_model, previous=taken_actions, choices=choices, experiment_split="SeeAct")

                    output0 = call_with_keepalive(
                        llm_pool,
                        lambda: generation_model.generate(prompt=prompt, image_path=input_image_path, turn_number=0),
                        keepalive_tick,
                        page,
                        poll_s=0.2,
                    )
                    output1 = call_with_keepalive(
                        llm_pool,
                        lambda: generation_model.generate(
                            prompt=prompt, image_path=input_image_path, turn_number=1, ouput__0=output0
                        ),
                        keepalive_tick,
                        page,
                        poll_s=0.2,
                    )

                    candidate_resp = f"[turn0]\n{output0}\n\n[turn1]\n{output1}"

                    # print("-"*120)
                    # print(candidate_resp)
                    # print("-"*120)

                    pred_element, pred_action, pred_value = postprocess_action_lmm(output1)
                    pred_action_u = (pred_action or "").strip().upper()
                    pe = (pred_element or "").strip()

                    if pred_action_u not in allowed_actions:
                        continue

                    # 无需元素动作
                    if pred_action_u in {"PRESS ENTER", "TERMINATE", "SCROLL", "SCROLL UP", "SCROLL DOWN", "SCROLL LEFT", "SCROLL RIGHT"}:
                        target_el = None
                        chosen_idx = -1
                        target_action = pred_action
                        target_value = pred_value
                        step_resp = candidate_resp
                        got_one_answer = True
                        break

                    # 元素动作：支持全局 idx 或 A/B/C
                    global_idx = None
                    if pe.isdigit():
                        gi = int(pe)
                        if gi in candidate_ids:
                            global_idx = gi

                    cand_pos = None
                    if global_idx is None and len(pe) in [1, 2]:
                        try:
                            cand_pos = get_index_from_option_name(pe)
                        except Exception:
                            cand_pos = None

                    if global_idx is not None:
                        chosen_idx = global_idx
                        target_el = elements[chosen_idx]
                        target_action = pred_action
                        target_value = pred_value
                        step_resp = candidate_resp
                        got_one_answer = True
                        break

                    if cand_pos is not None and 0 <= cand_pos < len(candidate_ids):
                        chosen_idx = candidate_ids[cand_pos]
                        target_el = elements[chosen_idx]
                        target_action = pred_action
                        target_value = pred_value
                        step_resp = candidate_resp
                        got_one_answer = True
                        break

                if not got_one_answer:
                    no_op_count += 1
                    taken_actions.append("No Operation")
                    action_desps.append("No Operation")
                    actions_out.append("stop(reason='no_valid_prediction')")
                    thoughts.append("")
                    history_resps.append("")
                    save_debug_image(
                        image_path,
                        bbox=None,
                        point=None,
                        markdown="No Operation",
                        action="stop(reason='no_valid_prediction')",
                        save_dir=save_vis_dir,
                    )
                    if no_op_count >= max_continuous_no_op:
                        status = "FAIL_CONTINUOUS_NO_OP"
                        break
                    curr_step += 1
                    continue

                history_resps.append(step_resp or "")

                # 生成动作串（box_token 用 page center；执行用 element_id -> locator）
                action_str = _action_from_seeact(target_action, target_value, target_el, chosen_idx)
                actions_out.append(action_str)

                # action 描述
                if target_el is not None:
                    t = (target_el["desc"] or "").strip().replace("\n", " ")
                    if len(t) > 80:
                        t = t[:80] + "..."
                    desc = f"[{chosen_idx}] tag={target_el['real_tag']} text={t}"
                else:
                    desc = (target_action or "").strip()

                new_action_text = f"{desc} -> {target_action}"
                if (target_action or "").strip().upper() in ["TYPE", "SELECT"] and target_value:
                    new_action_text += f": {target_value}"

                taken_actions.append(new_action_text)
                action_desps.append(new_action_text)
                thoughts.append("")

                # debug 画框：用 page bbox 映射回 viewport
                draw_bbox = None
                draw_point = None
                if target_el is not None:
                    bbox_page = target_el["bbox_page_xywh"]
                    draw_bbox = page_bbox_to_viewport_bbox(bbox_page, sx0, sy0)
                    px, py = _center_page_tuple(target_el)
                    vx, vy = page_point_to_viewport_point(px, py, sx0, sy0)
                    draw_point = [vx, vy]

                save_debug_image(
                    image_path,
                    bbox=draw_bbox,
                    point=draw_point,
                    markdown=new_action_text,
                    action=action_str,
                    save_dir=save_vis_dir,
                )

                # 终止/特殊动作
                action_type = parse_action_type_local(action_str)
                if action_type == "Finish":
                    status = "SUCCESS"
                    break
                if action_type == "Wait":
                    time.sleep(5)
                    curr_step += 1
                    continue
                if action_type == "CallUser":
                    status = "FAIL_CALL_USER"
                    break
                if action_type == "Stop":
                    no_op_count += 1
                    if no_op_count >= max_continuous_no_op:
                        status = "FAIL_CONTINUOUS_NO_OP"
                        break
                    curr_step += 1
                    continue

                # 6) 执行动作：locator.scroll_into_view_if_needed（对齐点）
                try:
                    new_page, new_client, _ = execute_action_aligned(page, client, action_str, elements=elements, eid=chosen_idx)

                    if new_page != page:
                        page = new_page
                        client = page.context.new_cdp_session(page)

                    op_count += 1
                    no_op_count = 0
                except Exception as e:
                    logger.warning(f"execute_action_aligned failed: {e}")
                    no_op_count += 1
                    if no_op_count >= max_continuous_no_op:
                        status = "FAIL_CONTINUOUS_NO_OP"
                        break

                if op_count >= max_op:
                    status = "FAIL_MAX_OP"
                    break

                curr_step += 1

            if status == "":
                status = "FAIL_UNKNOWN"

            result_item = {
                "task_id": task_id,
                "task": task,
                "key_points": json_item.get("keytra", ""),
                "website": website,
                "task_index": task_idx,
                "status": status,
                "reference_length": reference_length,
                "predict_length": len(actions_out),
                "final_result_response": thoughts[-1] if thoughts else "",
                "actions": actions_out,
                "action_desps": action_desps,
                "thoughts": thoughts,
                "history_resps": history_resps,
                "image_path_list": image_path_list,
                "urls": urls,
            }

            visual_item = {
                "task_id": task_id,
                "task": task,
                "key_points": json_item.get("keytra", ""),
                "website": website,
                "reference_length": reference_length,
                "predict_length": len(actions_out),
                "action_list": [],
            }
            # 保存请求捕获结果
            save_result_path = f"{base_dir}/capture.json"
            request_count = request_collector.save_results(save_result_path)
            logger.info(f"保存了 {request_count} 个请求到 {save_result_path}")

            n = min(len(image_path_list), len(actions_out), len(action_desps), len(thoughts), len(history_resps))
            for idx in range(n):
                visual_item["action_list"].append(
                    {
                        "action_id": f"{task_id}_{idx:02d}",
                        "thought": thoughts[idx],
                        "markdown": action_desps[idx],
                        "action": actions_out[idx],
                        "image_path": image_path_list[idx],
                        "response": history_resps[idx],
                    }
                )

            ok = safe_save_results(base_dir, result_item, visual_item)
            if ok:
                logger.info(f"[DONE] {folder_name} status={status}")
            else:
                logger.error(f"保存结果失败: {base_dir}")

            gc.collect()

        except Exception as e:
            logger.error(f"处理任务 {json_item_i} 异常: {str(e)}", exc_info=True)
            continue
        finally:
            try:
                if page is not None and (not page.is_closed()):
                    page.close()
            except Exception:
                pass

    try:
        context.close()
        p.stop()
        logger.info(f"Worker {worker_id} 资源清理完成")
    except Exception as e:
        logger.error(f"Worker {worker_id} 资源清理失败: {str(e)}")

    try:
        llm_pool.shutdown(wait=False, cancel_futures=True)
    except Exception:
        pass


# =========================
# 入口
# =========================
def parse_args():
    import argparse
    parser = argparse.ArgumentParser(description="SeeAct Web Agent 自动评测")

    # 必需参数
    parser.add_argument("--task-file", required=True,
                        help="任务 JSON 文件路径")
    parser.add_argument("--output-dir", required=True,
                        help="结果输出目录")
    parser.add_argument("--base-url", required=True,
                        help="浏览器服务基础 URL")

    # 浏览器端口
    parser.add_argument("--ports", type=int, nargs="+",
                        default=[9223, 9225, 9227, 9229, 9231, 9233, 9235, 9237],
                        help="浏览器端口列表，worker 数量等于端口数量 (默认: 9223 9225 9227 9229 9231 9233 9235 9237)")

    # 任务控制
    parser.add_argument("--max-tasks", type=int, default=100,
                        help="最大任务数 (默认: 100)")
    parser.add_argument("--max-op", type=int, default=50,
                        help="单任务最大操作步数 (默认: 50)")
    parser.add_argument("--max-continuous-no-op", type=int, default=10,
                        help="连续无效操作终止阈值 (默认: 10)")

    # Ranker
    parser.add_argument("--ranker-path", default=None,
                        help="Ranking 模型路径 (默认: 不使用)")
    parser.add_argument("--top-k", type=int, default=80,
                        help="Ranker 筛选 top-k 元素数 (默认: 80)")

    # 推理参数
    parser.add_argument("--choice-batch-size", type=int, default=30,
                        help="每批候选元素数量 (默认: 30)")

    # LLM API 配置
    parser.add_argument("--api-url", required=True,
                        help="LLM API 基础 URL")
    parser.add_argument("--api-key", required=True,
                        help="LLM API Key")
    parser.add_argument("--model-name", default="gpt-4o",
                        help="模型名称 (默认: gpt-4o)")

    return parser.parse_args()


def main():
    try:
        mp.set_start_method("spawn", force=True)
    except Exception:
        pass

    args = parse_args()

    PORT_LIST = args.ports
    WORKERS = len(PORT_LIST)

    BASE_DIR = args.output_dir
    os.makedirs(BASE_DIR, exist_ok=True)
    LOG_DIR = f"{BASE_DIR}_logs"
    os.makedirs(LOG_DIR, exist_ok=True)

    # 加载任务数据
    with open(args.task_file, "r", encoding="utf-8") as f:
        scribe_json_items = json.load(f)

    # 加载不可访问 URLs
    inaccessible_urls = set()
    if args.inaccessible_urls and os.path.exists(args.inaccessible_urls):
        with open(args.inaccessible_urls, "r", encoding="utf-8") as f:
            inaccessible_urls = set(json.load(f))

    # 获取已经完成的任务
    completed_tasks = get_completed_tasks(BASE_DIR)

    # 获取剩余任务
    domestic_tasks = get_remaining_domestic_tasks(
        scribe_json_items, inaccessible_urls, completed_tasks,
        max_tasks=args.max_tasks,
    )
    print(f"剩余待处理任务: {len(domestic_tasks)}")

    # 分配任务
    shards = distribute_tasks_among_workers(domestic_tasks, WORKERS)
    for idx, shard in enumerate(shards):
        print(f"Worker {idx} 将处理任务: {shard}")

    # 启动 workers
    procs = []
    for wid in range(WORKERS):
        if not shards[wid]:
            print(f"Worker {wid} 没任务，跳过")
            continue

        proc = mp.Process(
            target=run_worker,
            args=(
                wid,
                shards[wid],
                scribe_json_items,
                BASE_DIR,
                LOG_DIR,
                args.base_url,
                PORT_LIST
            ),
            kwargs={
                "ranker_path": args.ranker_path,
                "top_k": args.top_k,
                "fixed_choice_batch_size": args.choice_batch_size,
                "max_continuous_no_op": args.max_continuous_no_op,
                "max_op": args.max_op,
                "api_url": args.api_url,
                "api_key": args.api_key,
                "model_name": args.model_name,
            },
        )
        proc.start()
        procs.append(proc)
        print(f"Worker {wid} 已启动")
        time.sleep(2)

    # 监听进程状态
    try:
        while any(p.is_alive() for p in procs):
            time.sleep(5)
            alive_count = sum(1 for p in procs if p.is_alive())
            print(f"[状态] 活跃进程: {alive_count}")
    except KeyboardInterrupt:
        print("接收到中断信号，终止所有进程...")
        for proc in procs:
            proc.terminate()
        for proc in procs:
            proc.join(timeout=5)
            if proc.is_alive():
                proc.kill()

    for proc in procs:
        proc.join()

    print("全部进程结束")


if __name__ == "__main__":
    main()
