export type InteractiveBlockLang =
  | 'owlynn-quiz'
  | 'owlynn-steps'
  | 'owlynn-callout'
  | 'owlynn-embed'
  | 'owlynn-cell'
  | 'owlynn-template'
  | 'mermaid'

export interface ParsedMarkdownSegment {
  type: 'markdown'
  content: string
}

export interface ParsedBlockSegment {
  type: 'block'
  lang: InteractiveBlockLang
  body: string
  complete: boolean
}

export type ContentSegment = ParsedMarkdownSegment | ParsedBlockSegment

export interface QuizPayload {
  question: string
  options: string[]
  correctIndex: number
  explanation?: string
}

export interface StepItem {
  heading: string
  body: string
}

export interface StepsPayload {
  title?: string
  steps: StepItem[]
}

export interface CalloutPayload {
  variant?: 'tip' | 'warning' | 'note'
  title?: string
  body: string
}

export interface EmbedPayload {
  type: 'chart' | 'image'
  url: string
  title?: string
}

export interface CellPayload {
  language?: string
  code: string
  output?: string | null
  runnable?: boolean
}
