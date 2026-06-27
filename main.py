import asyncio
import os
import sys
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core import AgentLoop
from browser import save_auth

async def main():
    load_dotenv()

    #key check
    if not os.getenv("GROQ_API_KEY"):
        print("Error: GROQ_API_KEY environment variable is not set.")
        return

    while True:
        #interactive
        objective = input("\nВведите задачу для агента (или 'exit' для выхода, 'auth' для сохранения сессии): ")
        
        if objective.lower() in ['exit', 'quit']:
            print("Выход...")
            break
            
        if objective.lower() == 'auth':
            await save_auth()
            continue
        
        agent = AgentLoop(objective or "Go to duckduckgo.com and search for 'Playwright python'")
        await agent.run()

if __name__ == "__main__":
    asyncio.run(main())