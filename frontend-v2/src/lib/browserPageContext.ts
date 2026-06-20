/** User-pushed browser tab context from Owlynn Browser Bridge. */

export interface BrowserPageContext {
  url: string
  title: string
  text: string
  selection: string
  intent?: string
}

export interface BrowserPageContextEvent {
  type: 'browser.page_context'
  url: string
  title: string
  text: string
  selection: string
  intent?: string
}

const COMPOSER_EXCERPT_MAX = 3000

/** Build composer prefill text — does not auto-send. */
export function buildPageContextDraft(ctx: BrowserPageContext): string {
  const title = ctx.title?.trim() || 'Untitled page'
  const url = ctx.url?.trim() || ''
  
  let intentPrefix = "Help me with this page:"
  if (ctx.intent === "summarize") intentPrefix = "Please summarize the key points of this page:"
  else if (ctx.intent === "automate") intentPrefix = "Please automate interaction for this page:"
  
  let draft = `${intentPrefix} ${title}${url ? ` (${url})` : ''}`

  const selection = ctx.selection?.trim()
  const text = ctx.text?.trim()

  if (ctx.intent === "automate") {
    draft += `\n\n[SYSTEM NOTE: This context was sent directly from the active browser tab via the Owlynn Browser Extension. You MUST use the \`active_browser_action\` tool to interact with it. To analyze the page structure, use {"action": "get_html", "selector": "body"} to read the non-human DOM directly. Do NOT use show_hints or Playwright.]`
  } else {
    if (selection) {
      draft += `\n\nSelected text:\n${selection}`
    } else if (text) {
      const excerpt =
        text.length > COMPOSER_EXCERPT_MAX
          ? `${text.slice(0, COMPOSER_EXCERPT_MAX)}\n… [truncated in composer]`
          : text
      draft += `\n\nPage excerpt:\n${excerpt}`
    }
    draft += `\n\n[SYSTEM NOTE: This context was sent directly from the active browser tab via the Owlynn Browser Extension. You MUST use the \`active_browser_action\` tool to interact with it. Do NOT use Playwright.]`
  }

  return draft
}
