import json
import os
import asyncio
import base64
import warnings
import time
from groq import Groq
from browser import BrowserEngine
from tools import navigate, click, type_text, finish

warnings.filterwarnings("ignore", category=FutureWarning)

DEBUG_MODE = False

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "navigate",
            "description": "Navigate to a specific URL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The URL to navigate to."}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "click",
            "description": "Click on an element by ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "element_id": {"type": "integer", "description": "The element ID."}
                },
                "required": ["element_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "type_text",
            "description": "Type text into an element.",
            "parameters": {
                "type": "object",
                "properties": {
                    "element_id": {"type": "integer", "description": "The element ID."},
                    "text": {"type": "string", "description": "The text to type."}
                },
                "required": ["element_id", "text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "press_key",
            "description": "Нажимает клавишу на клавиатуре. Используй 'Enter' после ввода текста в поисковую строку, если на странице нет явной кнопки поиска",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "The key to press (e.g., 'Enter', 'Tab', 'Escape')."}
                },
                "required": ["key"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "click_coordinates",
            "description": "Click on specific coordinates (x, y).",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "description": "X coordinate"},
                    "y": {"type": "integer", "description": "Y coordinate"}
                },
                "required": ["x", "y"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "finish",
            "description": "Finish the task. You MUST provide the extracted data.",
            "parameters": {
                "type": "object",
                "properties": {
                    "final_answer": {"type": "string", "description": "The extracted text/data or result of the task."}
                },
                "required": ["final_answer"]
            }
        }
    }
]

class AgentLoop:
    def __init__(self, objective: str):
        self.objective = objective
        self.browser = BrowserEngine(headless=False)
        self.client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        self.max_steps = 15
        self.messages = []
        self.prev_url = None
        self.prev_tree = None

    def _prune_images(self, keep_last=1):
        """Оставляет только keep_last последних изображений в истории сообщений."""
        count = 0
        for i in range(len(self.messages) - 1, -1, -1):
            msg = self.messages[i]
            
            #role
            if isinstance(msg, dict):
                role = msg.get("role")
                content = msg.get("content")
            else:
                role = getattr(msg, "role", None)
                content = getattr(msg, "content", None)

            if role == "user" and isinstance(content, list):
                has_image = any(p.get("type") == "image_url" for p in content)
                if has_image:
                    count += 1
                    if count > keep_last:
                        msg["content"] = [p for p in content if p.get("type") != "image_url"]
                        msg["content"].append({"type": "text", "text": "Здесь было изображение предыдущего шага"})

    async def run(self):
        if DEBUG_MODE:
            print(f"Starting Agent with objective: {self.objective}")
        else:
            print(f"Цель агента: {self.objective}")
            
        await self.browser.start()

        system_prompt = (
            f"You are an autonomous browser agent. Your goal is: {self.objective}. "
            "You will receive a screenshot and a text accessibility tree of the current page. "
            "Interactive elements are marked with numeric IDs (e.g., [12]). "
            "Use these IDs to interact with the page via tools. "
            "Priority: Extract data from the Accessibility Tree. "
            "If the needed text is visible in the tree, extract it and IMMEDIATELY call 'finish' with the 'final_answer' parameter. "
            "Do not perform unnecessary clicks or navigations if the data is already visible. "
            "ALWAYS respond with a Function Call if an action is needed."
        )
        
        self.messages.append({"role": "system", "content": system_prompt})

        try:
            step = 0
            while step < self.max_steps:
                step += 1
                start_time = time.time()
                if step > 1:
                    await asyncio.sleep(1)

                if DEBUG_MODE:
                    print(f"\n--- Step {step} ---")
                else:
                    print(f"\n--- Шаг {step} ---")

                acc_tree, screenshot_b64 = await self.browser.get_state()
                current_url = await self.browser.get_url()
                current_title = await self.browser.get_title()

                #stagnation
                if step > 1 and current_url == self.prev_url and acc_tree == self.prev_tree:
                    print("⚠️ Stagnation detected! Adding system warning...")
                    self.messages.append({"role": "user", "content": "SYSTEM ALERT: The state (URL and DOM) did not change after the last action. You might be stuck. Try scrolling or using a different element ID."})
                
                self.prev_url = current_url
                self.prev_tree = acc_tree

                #about:blank awaid
                if current_url == "about:blank":
                    print("⚠️ Detected about:blank, forcing navigation to DuckDuckGo...")
                    await self.browser.navigate("https://duckduckgo.com")
                    acc_tree, screenshot_b64 = await self.browser.get_state()
                    current_url = await self.browser.get_url()

                #capcha warning
                if "sorry" in current_url or "captcha" in current_url.lower():
                    print("⚠️ Обнаружена проверка! Пожалуйста, пройди её в окне браузера...")
                    await asyncio.get_running_loop().run_in_executor(None, input, "Нажми Enter в терминале, когда закончишь...")
                    print("🔄 Проверка пройдена, продолжаю выполнение...")
                    acc_tree, screenshot_b64 = await self.browser.get_state()
                    current_url = await self.browser.get_url()
                    current_title = await self.browser.get_title()

                #authorization warning
                if "login" in current_url.lower() or "signin" in current_url.lower():
                    print("Обнаружена страница входа! Пожалуйста, авторизуйтесь вручную...")
                    await asyncio.get_running_loop().run_in_executor(None, input, "Нажми Enter в терминале, когда закончишь...")
                    print("Авторизация завершена, продолжаю выполнение...")
                    acc_tree, screenshot_b64 = await self.browser.get_state()
                    current_url = await self.browser.get_url()
                    current_title = await self.browser.get_title()
                
                if DEBUG_MODE: print(f"URL: {current_url}")
                else: print(f"Активная вкладка: {current_title}")

                #msg for api
                user_content = [
                    {"type": "text", "text": f"Current URL: {current_url}\nAccessibility Tree:\n{acc_tree}"},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{screenshot_b64}"
                        }
                    }
                ]
                self.messages.append({"role": "user", "content": user_content})
                
                #clear old screenshots
                self._prune_images(keep_last=1)

                if DEBUG_MODE: print("Thinking...")
                else: print("Думаю...")

                response_msg = None
                while response_msg is None:
                    try:
                        completion = self.client.chat.completions.create(
                            model="meta-llama/llama-4-scout-17b-16e-instruct",
                            messages=self.messages,
                            tools=TOOLS_SCHEMA,
                            tool_choice="auto",
                            max_tokens=1024
                        )
                        response_msg = completion.choices[0].message
                    except Exception as e:
                        if "too many images" in str(e).lower() or "400" in str(e):
                            print("Лимит изображений! Очищаю историю и повторяю...")
                            self._prune_images(keep_last=1)
                            continue
                        else:
                            raise e
                
                self.messages.append(response_msg)

                if response_msg.tool_calls:
                    for tool_call in response_msg.tool_calls:
                        func_name = tool_call.function.name
                        args = json.loads(tool_call.function.arguments)
                        
                        if DEBUG_MODE: print(f"Tool Call: {func_name} {args}")

                        result = "Error: Unknown tool"
                        
                        if func_name == "navigate":
                            result = await self.browser.navigate(args.get('url'))
                        elif func_name == "click":
                            eid = int(args.get('element_id'))
                            if not DEBUG_MODE: print(f"Нажимаю на элемент: [{eid}]")
                            result = await self.browser.click_element(eid)
                        elif func_name == "type_text":
                            eid = int(args.get('element_id'))
                            text = args.get('text')
                            if not DEBUG_MODE: print(f"⌨Ввожу текст: {text}")
                            result = await self.browser.type_text(eid, text)
                        elif func_name == "press_key":
                            key = args.get('key')
                            if not DEBUG_MODE: print(f"⌨Нажимаю клавишу: {key}")
                            result = await self.browser.press_key(key)
                        elif func_name == "click_coordinates":
                            x = int(args.get('x'))
                            y = int(args.get('y'))
                            if not DEBUG_MODE: print(f"Клик по координатам: {x}, {y}")
                            result = await self.browser.click_coordinates(x, y)
                        elif func_name == "finish":
                            final_answer = args.get('final_answer', 'No answer provided')
                            await self.browser.take_screenshot("final_result.png")
                            if DEBUG_MODE: print(f"Objective Achieved! Answer: {final_answer}")
                            else: print(f"Задача выполнена! Ответ: {final_answer}")
                            return
                        
                        if DEBUG_MODE: print(f"   Result: {result}")
                        
                        self.messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": str(result)
                        })
                else:
                    if DEBUG_MODE: print(f"Message: {response_msg.content}")
                    else: print(f"Агент: {response_msg.content}")
                
                if not DEBUG_MODE:
                    print(f"⏱Время шага: {time.time() - start_time:.2f}s")
                    
        except Exception as e:
            print(f"Критическая ошибка: {e}")
        finally:
            await self.browser.stop()