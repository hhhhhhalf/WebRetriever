import os
import time
import base64
import backoff

from openai import APIConnectionError, APIError, RateLimitError

import os, cv2, time, base64, random, requests
import glob
import base64
import traceback
import re
from pprint import pprint
from openai import OpenAI,APIConnectionError, RateLimitError, APIError 

# API_URL 和 API_KEY 通过参数动态传入，不再硬编码

def resize_read_image_base64(file_path, max_quality=85, max_size=2, min_size = 512):
    """ 基于file_path路径，获得base64，并保证base64的最大值小于 max_size MB
    输入：
        file_path  (dict): 图像路径
        max_quality (int): 最大base64质量
        max_size (float): 最大base64的空间占用，单位为MB，当过大时会循环降低画质以保证图片小于对应要求 
        min_size (int): 最小边长度
    """
    img = cv2.imread(file_path)
    if img is None:
        raise ValueError (f"[resize_read_image_base64]Invalid image for {file_path}")
    
    height, width, _ = img.shape
    if min(width, height) > min_size:  # 如果最短边大于min_size像素，则按比例缩小图像
        scale_factor = min_size / min(width, height)  # 计算缩放比例
        new_width = int(width * scale_factor)   # 计算新的宽度和高度
        new_height = int(height * scale_factor)
        img = cv2.resize(img, (new_width, new_height))

    # 尝试以当前质量压缩并编码图片
    quality = max_quality  # 设置初始质量
    while quality >= 50:  # 循环，直到Base64图片大小小于2MB或质量降到最低限度
        flag, buffer = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
        if flag:
            base64_image = base64.b64encode(buffer).decode()
            
            if len(base64_image) * 3 / 4 < max_size * 1024 * 1024:   # 检查Base64编码后的大小是否小于2MB
                return base64_image
            else:
                # 如果图片大小大于2MB，降低质量再试
                quality -= 5
        else:
            raise ValueError("[resize_read_image_base64] Invalid encoder for image.")
    
    # 如果退出循环，意味着即使最低质量也无法满足大小要求
    print(f"【resize_read_image_base64】多次压缩后图片仍然大于{max_size}MB，返回质量为{quality}")
    return base64_image


def get_response_with_retry(model, messages, api_url, api_key=None, max_tokens=512, top_p=1.0, random_sample=True, retries=3, delay=3, json_output=False, temperature=1.0, frequency_penalty=0.0, presence_penalty=0.0, observation_id=""):
    attempt = 0  # 初始化尝试次数
    while attempt < retries:
        start_time = time.time()  # 记录请求发送前的时间
        try:
            # 发送 POST 请求
            json_data = {"model": model,
                         "messages": messages,
                         "stream": False,
                         "max_tokens": max_tokens,
                         "top_p": top_p,
                         "temperature": temperature,
                         "frequency_penalty": frequency_penalty,
                         "presence_penalty": presence_penalty}
            if not random_sample:
                json_data['do_sample'] = False
            if json_output:
                json_data["response_format"] = {"type": "json_schema"}
            
            response = requests.post(os.path.join(api_url, 'v1/chat/completions'),
                                     json=json_data,
                                     headers={"Content-Type": "application/json",
                                              "observation-id": observation_id,
                                              "Authorization": f"Bearer {api_key}"},
                                     timeout=600,
                                     )

            # 处理响应
            if response.status_code == 200:
                result = response.json()
                if 'choices' not in result:
                    print(f"[get-response] {result} 存在异常")
                    return False, response.text, result
                else:
                    return True, result['choices'][0]['message']['content'], result
            else:
                msg = f"状态码：{response.status_code}。原因：{response.json()}"
                print(f"===>{model}<=== {msg}")
                if attempt < retries - 1:  # 如果不是最后一次尝试，则等待一段时间
                    time.sleep(delay)
                attempt += 1

        except requests.exceptions.Timeout:
            # 在这里处理超时异常
            end_time = time.time()  # 记录请求超时后的时间
            timeout_time = end_time - start_time  # 计算超时的时间
            msg = f"第{attempt+1}次请求失败，请求超时，耗时: {timeout_time:.2f}秒"
            print(f"===>{model}<=== {msg}")
            if attempt < retries - 1:  # 如果不是最后一次尝试，则等待一段时间
                time.sleep(delay)
            attempt += 1

        except requests.exceptions.RequestException as e:
            # 处理其他可能的异常
            msg = f"第{attempt+1}次请求失败，请求发生其他错误：{e}"
            print(f"===>{model}<=== {msg}")
            if attempt < retries - 1:  # 如果不是最后一次尝试，则等待一段时间
                time.sleep(delay)
            attempt += 1
    
    # 所有尝试完成后仍未成功，则返回失败
    return False, "请求失败或超时，已重试多次：" + msg, None


def _call_reason_model(client, model, messages, max_tokens):
    max_retries = 3
    retry_delay = 5
    for attempt in range(max_retries):
        try:
            if model == "claude-3-7-sonnet":
                print("reasoning_effort: high")
                chat_response = client.chat.completions.create(
                    model=model,
                    #messages=[{"role": "user", "content": text}],
                    messages=messages,
                    temperature=0.1,
                    # messages=[{"content": text}],
                    max_tokens=max_tokens,
                    reasoning_effort="high",
                    stream=True  # 此处流式返回，防止deepseek超时
                )
            else:
                # print("xxxxxxxx", messages)
                chat_response = client.chat.completions.create(
                    model=model,
                    #messages=[{"role": "user", "content": text}],
                    messages=messages,
                    temperature=0.1,
                    # messages=[{"content": text}],
                    max_tokens=max_tokens,
                    stream=True  # 此处流式返回，防止deepseek超时
                )

    
            usage_dict = {}
            ans_str, reason_str = "", ""
            #vis_text = text[:20].replace('# 视频客观内容描述\n',' ')
            print(f"[call_reason_model] 请求数据，流式返回，请耐心等待...")
            # 逐步接收数据
            for chunk in chat_response:
                # print(1111, chunk)
                if getattr(chunk.choices[0].delta, 'reasoning_content', None):
                    print(2222)
                    reason_str += chunk.choices[0].delta.reasoning_content
                elif chunk.choices[0].delta.content:
                    print(3333)
                    ans_str += chunk.choices[0].delta.content
                elif chunk.usage:   # 目前阿里云无法返回这部分数据
                    print(4444)
                    usage_dict = chunk.usage.to_dict()
            print("[call_reason_model] end")
    
            if len(reason_str) == 0:   # 匹配reason_str中的内容
                match = re.search(r'<think>(.*?)<think>', ans_str)
                if match:
                    reason_str = match.group(1)
    
            return ans_str, usage_dict, reason_str
    
        except (APIConnectionError, RateLimitError, APIError) as e:
            if attempt < max_retries - 1:
                print(f"API调用失败，第{attempt+1}次重试... 错误：{e}")
                time.sleep(retry_delay)
            else:
                print(f"API调用失败，已达到最大重试次数: {e}")
                #raise
                return None, None, None
        except Exception as e:
            traceback.print_exc()
            print(f"发生未预期错误: {e}")
            #raise
            return None, None, None


def get_withoutimage(call_model_type, prompt, api_url=None, api_key=None):
    message = []
    max_tokens = 16384
    top_p = 0.1
    temperature = 0.1
    frequency_penalty = 0.0
    presence_penalty = 0.0
    json_output = False
    observation_id = "1111"

    message.append({'role': 'user',
                                'content': [{'type':'text', 'text':prompt}  ]})

    status_flag, ans_text, result = get_response_with_retry(call_model_type,
                                                                message,
                                                                api_url,
                                                                api_key,
                                                                max_tokens = max_tokens,
                                                                top_p = top_p,
                                                                temperature=temperature,
                                                                frequency_penalty=frequency_penalty,
                                                                presence_penalty=presence_penalty,
                                                                json_output = json_output,
                                                                observation_id = observation_id)

    #if status_flag == True: 
    content = result["choices"][0]["message"]["content"]
    #print(image_path)
    return content


def get_withimage(call_model_type, image_path, prompt, api_url=None, api_key=None):
    message = []
    max_tokens = 16384
    top_p = 0.1
    temperature = 0.1
    frequency_penalty = 0.0
    presence_penalty = 0.0
    json_output = False
    observation_id = "1111"

    base64_image = resize_read_image_base64(image_path, max_quality=85, max_size=2, min_size=1440)
    
    image_item = {'type':'image_url', 
           'image_url':{'url':f'data:image/jpeg;base64,{base64_image}', 'detail': 'high'} }
    
    message.append({'role': 'user',
                                'content': [{'type':'text', 'text':prompt}  ]})

    total_image_list = []
    total_image_list.append({'type':'image_url', 
                             'image_url':{'url':f'data:image/jpeg;base64,{base64_image}',
                                                              'detail': "high"} })
    message[-1]['content'] = total_image_list + message[-1]['content']

    status_flag, ans_text, result = get_response_with_retry(call_model_type,
                                                                message,
                                                                api_url,
                                                                api_key,
                                                                max_tokens = max_tokens,
                                                                top_p = top_p,
                                                                temperature=temperature,
                                                                frequency_penalty=frequency_penalty,
                                                                presence_penalty=presence_penalty,
                                                                json_output = json_output,
                                                                observation_id = observation_id)

    #if status_flag == True: 
    content = result["choices"][0]["message"]["content"]
    #print(image_path)
    return content


def _encode_image_b64(image_path: str) -> str:
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

class OpenaiEngine:
    def __init__(
        self,
        api_key=None,
        base_url=None,
        api_url=None,
        stop=["\n\n"],
        rate_limit=-1,
        model=None,            # 你的模型名，如 "gpt-4o" / 你们网关的模型名
        temperature=0.0,
        top_p=0.1,
        max_tokens=4096,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        json_output=False,
        **kwargs,
    ) -> None:
        self.stop = stop
        self.temperature = temperature
        self.top_p = top_p
        self.model = model
        self.max_tokens = max_tokens
        self.frequency_penalty = frequency_penalty
        self.presence_penalty = presence_penalty
        self.json_output = json_output
        self.api_url = api_url
        self.api_key = api_key

        # rate limit：保持和原版结构类似（如果你不需要可忽略）
        self.request_interval = 0 if rate_limit == -1 else 60.0 / rate_limit
        self.next_avil_time = 0

    def _sleep_if_needed(self):
        if self.request_interval <= 0:
            return
        now = time.time()
        if now < self.next_avil_time:
            time.sleep(self.next_avil_time - now)

    @backoff.on_exception(
        backoff.expo,
        (APIError, RateLimitError, APIConnectionError),
        max_tries=3,
    )
    def generate(
        self,
        prompt: list = None,
        max_new_tokens=4096,
        temperature=None,
        model=None,
        image_path=None,
        ouput__0=None,
        turn_number=0,
        **kwargs
    ):
        """
        和原版 OpenaiEngine.generate 保持同签名/同语义：
          - prompt 是长度=3 的 list: [prompt0, prompt1, prompt2]
          - turn_number==0 做 Action Generation
          - turn_number==1 做 Grounding，并把 ouput__0 以 assistant 消息注入
          - 返回 str（原版 turn0 返回 str，turn1 返回 str）
        """
        self._sleep_if_needed()

        model_name = model if model else self.model
        temp = temperature if temperature is not None else self.temperature
        max_tok = max_new_tokens if max_new_tokens is not None else self.max_tokens

        if prompt is None or len(prompt) < 3:
            raise ValueError("prompt 必须是长度>=3 的 list: [prompt0, prompt1, prompt2]")

        prompt0, prompt1, prompt2 = prompt[0], prompt[1], prompt[2]

        if image_path is None:
            raise ValueError("image_path 不能为空（SeeAct 需要截图 crop 作为输入）")

        base64_image = _encode_image_b64(image_path)

        if turn_number == 0:
            prompt1_input = [
                {"role": "system", "content": [{"type": "text", "text": prompt0}]},
                {"role": "user",
                 "content": [
                     {"type": "text", "text": prompt1},
                     {"type": "image_url",
                      "image_url": {"url": f"data:image/jpeg;base64,{base64_image}",
                                    "detail": "high"}}
                 ]},
            ]
            messages = prompt1_input

        elif turn_number == 1:
            prompt2_input = [
                {"role": "system", "content": [{"type": "text", "text": prompt0}]},
                {"role": "user",
                 "content": [
                     {"type": "text", "text": prompt1},
                     {"type": "image_url",
                      "image_url": {"url": f"data:image/jpeg;base64,{base64_image}",
                                    "detail": "high"}}
                 ]},
                {"role": "assistant", "content": [{"type": "text", "text": f"\n\n{ouput__0}"}]},
                {"role": "user", "content": [{"type": "text", "text": prompt2}]},
            ]
            messages = prompt2_input
        else:
            raise ValueError(f"turn_number 只能是 0 或 1，当前: {turn_number}")

        # --- 发请求 ---
        observation_id = "1111"
        status_flag, ans_text, result = get_response_with_retry(
            model_name,
            messages,
            self.api_url,
            self.api_key,
            max_tokens=max_tok,
            top_p=self.top_p,
            temperature=temp,
            frequency_penalty=self.frequency_penalty,
            presence_penalty=self.presence_penalty,
            json_output=self.json_output,
            observation_id=observation_id
        )

        if self.request_interval > 0:
            start_time = time.time()
            self.next_avil_time = max(start_time, self.next_avil_time) + self.request_interval

        try:
            return result["choices"][0]["message"]["content"]
        except Exception:
            return ans_text if isinstance(ans_text, str) else str(ans_text)
