import asyncio
from src.tools.web_tools import deep_research, web_search


async def main():
    print("Testing standard web_search...")
    query = "Latest news about Crawl4AI Python library"
    try:
        search_results = await web_search.ainvoke({"query": query})
        print("\n--- web_search output ---")
        print(search_results[:500] + "...\n")
    except Exception as e:
        print(f"web_search failed: {e}")

    print("\nTesting deep_research (which includes Web RAG and crawl4ai)...")
    try:
        deep_results = await deep_research.ainvoke({"query": query, "max_urls": 2})
        print("\n--- deep_research output ---")
        print(deep_results[:1500] + "...\n")
    except Exception as e:
        print(f"deep_research failed: {e}")


if __name__ == "__main__":
    asyncio.run(main())
