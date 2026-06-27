import asyncio
import base64
import random
import os
import io
from PIL import Image
from typing import Tuple, Any
from playwright.async_api import async_playwright, Page, Browser, BrowserContext

class BrowserEngine:
    def __init__(self, headless: bool = False):
        self.headless = headless
        self.playwright = None
        self.browser: Browser = None
        self.context: BrowserContext = None
        self.page: Page = None

    async def start(self):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=self.headless, slow_mo=300)
        self.context = await self.browser.new_context(
            viewport={'width': 1400, 'height': 1000},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        await self.context.add_init_script("""
            window.addEventListener('DOMContentLoaded', () => {
                document.querySelectorAll('a[target="_blank"]').forEach(a => a.setAttribute('target', '_self'));
            });
        """)
        #визуализация курсора мыши (демо)
        await self.context.add_init_script("""
            const installCursor = () => {
                if (document.getElementById('ag-cursor')) return;
                const cursor = document.createElement('div');
                cursor.id = 'ag-cursor';
                cursor.style.cssText = `
                    position: fixed;
                    top: 0;
                    left: 0;
                    width: 20px;
                    height: 20px;
                    background-color: rgba(255, 69, 0, 0.6);
                    border: 2px solid rgba(255, 69, 0, 0.9);
                    border-radius: 50%;
                    pointer-events: none;
                    z-index: 2147483647;
                    transition: transform 0.1s, background-color 0.1s;
                    transform: translate(-50%, -50%);
                `;
                document.body.appendChild(cursor);

                document.addEventListener('mousemove', (e) => {
                    cursor.style.left = e.clientX + 'px';
                    cursor.style.top = e.clientY + 'px';
                });

                document.addEventListener('mousedown', () => {
                    cursor.style.transform = 'translate(-50%, -50%) scale(0.8)';
                    cursor.style.backgroundColor = 'rgba(255, 69, 0, 0.9)';
                });

                document.addEventListener('mouseup', () => {
                    cursor.style.transform = 'translate(-50%, -50%) scale(1)';
                    cursor.style.backgroundColor = 'rgba(255, 69, 0, 0.6)';
                });
            };
            if (document.body) installCursor();
            else window.addEventListener('DOMContentLoaded', installCursor);
        """)
        self.page = await self.context.new_page()

    async def stop(self):
        if self.context: await self.context.close()
        if self.browser: await self.browser.close()
        if self.playwright: await self.playwright.stop()

    async def get_state(self) -> Tuple[str, str]:
        """
        Возвращает (accessibility_tree_text, base64_screenshot).
        """
        if self.context.pages:
            self.page = self.context.pages[-1]
        await self.page.bring_to_front()

        #delete old marks
        await self.page.evaluate("() => { document.querySelectorAll('.ag-marker').forEach(e => e.remove()); }")

        #js inject
        js_script = """
        () => {
            let id_counter = 1;
            const items = [];
            
            // 1. Базовые интерактивные элементы и важные роли для списков/таблиц
            const selectors = [
                'a', 'button', 'input', 'textarea', 'select',
                '[role="button"]', '[role="link"]', '[role="checkbox"]', '[role="menuitem"]', 
                '[role="tab"]', '[role="row"]', '[role="gridcell"]', '[role="option"]', '[role="listitem"]',
                '[onclick]'
            ];
            const elementSet = new Set(document.querySelectorAll(selectors.join(',')));

            // 2. Эвристика: добавляем элементы с cursor: pointer (часто используется в SPA для div/span)
            document.querySelectorAll('div, span, li, tr, td').forEach(el => {
                if (elementSet.has(el)) return;
                const style = window.getComputedStyle(el);
                if (style.cursor === 'pointer') {
                    elementSet.add(el);
                }
            });

            const interactables = Array.from(elementSet);

            interactables.forEach(el => {
                const rect = el.getBoundingClientRect();
                if (rect.width === 0 || rect.height === 0 || rect.top < 0 || rect.top > window.innerHeight) return;
                
                const style = window.getComputedStyle(el);
                if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return;

                // Текстовое описание
                let label = el.innerText || el.getAttribute('aria-label') || el.getAttribute('placeholder') || el.value || '';
                label = label.replace(/\\n/g, ' ').trim();
                
                // СТРОГАЯ ФИЛЬТРАЦИЯ: Игнорируем элементы без текста (экономия токенов)
                if (label.length === 0) return;

                const currentId = id_counter++;
                el.setAttribute('data-ag-id', currentId);

                // Визуальный маркер (создаем только для отфильтрованных элементов)
                const marker = document.createElement('div');
                marker.className = 'ag-marker';
                marker.innerText = currentId;
                Object.assign(marker.style, {
                    position: 'absolute',
                    left: (rect.left + window.scrollX) + 'px',
                    top: (rect.top + window.scrollY) + 'px',
                    backgroundColor: '#ff0',
                    color: '#000',
                    fontSize: '12px',
                    fontWeight: 'bold',
                    padding: '2px',
                    border: '1px solid #000',
                    zIndex: '2147483647',
                    pointerEvents: 'none'
                });
                document.body.appendChild(marker);

                // Сжатие данных: обрезаем до 60 символов
                label = label.substring(0, 60);
                const tagName = el.tagName.toLowerCase();
                const role = el.getAttribute('role') || '';
                const type = el.getAttribute('type') || '';
                
                let extra = '';
                if (role) extra += ` role=${role}`;
                if (type) extra += ` type=${type}`;
                
                items.push(`[${currentId}] <${tagName}${extra}> ${label}`);
            });

            return items.join('\\n');
        }
        """
        acc_tree = await self.page.evaluate(js_script)
        
        #screenshot
        screenshot_bytes = await self.page.screenshot(path="last_action.png")
        
        #resize screenshot
        img = Image.open(io.BytesIO(screenshot_bytes))
        img.thumbnail((1024, 1024))
        buffer = io.BytesIO()
        img.convert("RGB").save(buffer, format="JPEG", quality=70)
        screenshot_b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
        
        return acc_tree, screenshot_b64

    async def navigate(self, url: str):
        if not url.startswith('http'):
            url = 'https://' + url
        try:
            await self.page.goto(url, timeout=60000, wait_until="domcontentloaded")
            #waiting
            try:
                await self.page.wait_for_load_state("networkidle", timeout=5000)
            except:
                pass
            await self.page.wait_for_timeout(2000)
            return f"Navigated to {url}"
        except Exception as e:
            return f"Error navigating to {url}: {str(e)}"

    async def click_element(self, element_id: int):
        selector = f'[data-ag-id="{element_id}"]'
        try:
            locator = self.page.locator(selector).first
            if await locator.count() == 0:
                return f"Error: Element [{element_id}] not found."
            
            #mouse activity
            box = await locator.bounding_box()
            if box:
                x = box['x'] + box['width'] / 2
                y = box['y'] + box['height'] / 2
                await self.page.mouse.move(x, y, steps=15)
                await self.page.mouse.down()
                await self.page.wait_for_timeout(150)
                await self.page.mouse.up()
            else:
                await self.page.click(selector)

            await self.page.wait_for_timeout(1000) # Ждем реакции интерфейса
            return f"Clicked element [{element_id}]"
        except Exception as e:
            return f"Error clicking [{element_id}]: {str(e)}"

    async def type_text(self, element_id: int, text: str):
        selector = f'[data-ag-id="{element_id}"]'
        try:
            delay = random.randint(50, 100)
            await self.page.locator(selector).press_sequentially(text, delay=delay)
            return f"Typed '{text}' into [{element_id}]"
        except Exception as e:
            return f"Error typing into [{element_id}]: {str(e)}"

    async def press_key(self, key: str):
        try:
            await self.page.keyboard.press(key)
            await self.page.wait_for_timeout(500)
            return f"Pressed key '{key}'"
        except Exception as e:
            return f"Error pressing key '{key}': {str(e)}"

    async def scroll(self, direction: str):
        try:
            delta = "window.innerHeight * 0.7" if direction == "down" else "-window.innerHeight * 0.7"
            await self.page.evaluate(f"window.scrollBy(0, {delta})")
            await self.page.wait_for_timeout(500)
            return f"Scrolled {direction}"
        except Exception as e:
            return f"Error scrolling: {str(e)}"

    async def get_url(self):
        return self.page.url

    async def get_title(self):
        return await self.page.title()

    async def take_screenshot(self, path: str):
        await self.page.evaluate("() => { document.querySelectorAll('.ag-marker').forEach(e => e.remove()); }")
        await self.page.screenshot(path=path)

    async def click_coordinates(self, x: int, y: int):
        try:
            await self.page.mouse.click(x, y)
            await self.page.wait_for_timeout(1000)
            return f"Clicked at {x}, {y}"
        except Exception as e:
            return f"Error clicking at {x}, {y}: {str(e)}"

async def save_auth():
    print("Запуск режима сохранения авторизации...")
    engine = BrowserEngine(headless=False)
    await engine.start()
    
    print("Перехожу на Yahoo (страница входа)...")
    try:
        #anyone service
        await engine.page.goto("https://login.yahoo.com")
    except:
        pass
    
    print("Пожалуйста, авторизуйтесь в браузере (включая 2FA).")
    print("Нажмите Enter в этом терминале, когда закончите...")
    
    await asyncio.get_event_loop().run_in_executor(None, input)
    
    await engine.context.storage_state(path="auth.json")
    print("Файл auth.json сохранен!")
    
    await engine.stop()