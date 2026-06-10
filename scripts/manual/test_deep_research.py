import asyncio
from src.tools.web_tools import deep_research


async def main():
    print("Testing deep_research...")
    result = await deep_research.ainvoke({"query": "What is Crawl4AI?", "max_urls": 1})
    print(result[:1000])


if __name__ == "__main__":
    asyncio.run(main())
