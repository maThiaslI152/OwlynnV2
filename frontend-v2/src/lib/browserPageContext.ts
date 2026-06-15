/** User-pushed browser tab context from Owlynn Browser Bridge. */

export interface BrowserPageContext {
  url: string
  title: string
  text: string
  selection: string
}

export interface BrowserPageContextEvent {
  type: 'browser.page_context'
  url: string
  title: string
  text: string
  selection: string
}

const COMPOSER_EXCERPT_MAX = 3000

/** Build composer prefill text — does not auto-send. */
export function buildPageContextDraft(ctx: BrowserPageContext): string {
  const title = ctx.title?.trim() || 'Untitled page'
  const url = ctx.url?.trim() || ''
  let draft = `Help me with this page: ${title}${url ? ` (${url})` : ''}`

  const selection = ctx.selection?.trim()
  const text = ctx.text?.trim()

  if (selection) {
    draft += `\n\nSelected text:\n${selection}`
  } else if (text) {
    const excerpt =
      text.length > COMPOSER_EXCERPT_MAX
        ? `${text.slice(0, COMPOSER_EXCERPT_MAX)}\n… [truncated in composer]`
        : text
    draft += `\n\nPage excerpt:\n${excerpt}`
  }

  return draft
}
