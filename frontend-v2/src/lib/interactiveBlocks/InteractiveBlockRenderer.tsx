import ReactMarkdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeRaw from 'rehype-raw'
import rehypeSanitize from 'rehype-sanitize'
import type { Options } from 'rehype-sanitize'
import { InteractiveQuiz } from './InteractiveQuiz'
import { InteractiveSteps } from './InteractiveSteps'
import { InteractiveCallout } from './InteractiveCallout'
import { InteractiveMermaid } from './InteractiveMermaid'
import { InteractiveEmbed } from './InteractiveEmbed'
import { InteractiveCell } from './InteractiveCell'
import type {
  CalloutPayload,
  CellPayload,
  EmbedPayload,
  QuizPayload,
  StepsPayload,
} from './types'
import type { ParsedBlockSegment } from './types'

interface Props {
  segment: ParsedBlockSegment
  projectId: string
  threadId: string
}

function parseJson<T>(body: string): T | null {
  try {
    return JSON.parse(body) as T
  } catch {
    return null
  }
}

function IncompleteBlock({ lang }: { lang: string }) {
  return (
    <div className="owlynn-block owlynn-block-pending">
      Loading {lang}…
    </div>
  )
}

function ErrorBlock({ message }: { message: string }) {
  return <div className="owlynn-block owlynn-block-error">{message}</div>
}

export function InteractiveBlockRenderer({ segment, projectId, threadId }: Props) {
  if (!segment.complete) {
    return <IncompleteBlock lang={segment.lang} />
  }

  switch (segment.lang) {
    case 'owlynn-quiz': {
      const payload = parseJson<QuizPayload>(segment.body)
      if (!payload?.question || !Array.isArray(payload.options)) {
        return <ErrorBlock message="Invalid quiz block" />
      }
      return <InteractiveQuiz payload={payload} />
    }
    case 'owlynn-steps': {
      const payload = parseJson<StepsPayload>(segment.body)
      if (!payload?.steps?.length) {
        return <ErrorBlock message="Invalid steps block" />
      }
      return <InteractiveSteps payload={payload} />
    }
    case 'owlynn-callout': {
      const payload = parseJson<CalloutPayload>(segment.body)
      if (!payload?.body) {
        return <ErrorBlock message="Invalid callout block" />
      }
      return <InteractiveCallout payload={payload} />
    }
    case 'owlynn-embed': {
      const payload = parseJson<EmbedPayload>(segment.body)
      if (!payload?.url) {
        return <ErrorBlock message="Invalid embed block" />
      }
      return <InteractiveEmbed payload={payload} projectId={projectId} />
    }
    case 'owlynn-cell': {
      const payload = parseJson<CellPayload>(segment.body)
      if (!payload?.code) {
        return <ErrorBlock message="Invalid cell block" />
      }
      return <InteractiveCell payload={payload} projectId={projectId} threadId={threadId} />
    }
    case 'mermaid':
      return <InteractiveMermaid source={segment.body} />
    default:
      return null
  }
}

export interface MarkdownRenderProps {
  content: string
  projectId: string
  markdownSchema: Options
  markdownComponents: Components
}

export function renderMarkdownSegment(
  content: string,
  schema: Options,
  components: MarkdownRenderProps['markdownComponents'],
) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      rehypePlugins={[rehypeRaw, [rehypeSanitize, schema]]}
      components={components}
    >
      {content}
    </ReactMarkdown>
  )
}
