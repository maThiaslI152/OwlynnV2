# Changelog
- **Security:** Hardened anonymization.py with AWS AKIA, IPv6, expanded Unix paths, and trailing punctuation guards.
- **Routing:** Removed obsolete complex-vision and complex-longctx routes; implemented automatic vision fallback guard for cloud tasks.
- **Logic:** Refactored complex_node to accept dynamic max_context depending on route, allowing 1M context bounds for DeepSeek V4.
- **LLM Pool:** Stripped SwapManager complexity from medium pool. Plumbed extra_body configuration for deepseek-v4-flash.
- **Config:** Updated defaults.yaml to support DeepSeek V4 Flash 1M context limits and exposed thinking effort parameters. Removed unused medium variants.
- **Cleanup:** Deleted src/agent/swap_manager.py as it is no longer required for routing.
- **Tests:** Cleaned up outdated test references to swap_manager.py across 10 modules.
