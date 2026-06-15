import { ChatInteractiveChart } from '../../components/ChatInteractiveChart'
import { ChatImageViewer } from '../../components/ChatImageViewer'
import {
  isInteractiveChartUrl,
  isWorkspaceImageUrl,
  resolveWorkspaceFileUrl,
} from '../workspaceImageUrl'
import type { EmbedPayload } from './types'

interface Props {
  payload: EmbedPayload
  projectId: string
}

export function InteractiveEmbed({ payload, projectId }: Props) {
  const resolved = resolveWorkspaceFileUrl(payload.url, projectId) ?? payload.url
  const title = payload.title ?? 'Embedded content'

  if (payload.type === 'chart' || isInteractiveChartUrl(resolved)) {
    return <ChatInteractiveChart src={resolved} title={title} />
  }
  if (payload.type === 'image' || isWorkspaceImageUrl(resolved)) {
    return <ChatImageViewer src={resolved} alt={title} />
  }
  return <ChatInteractiveChart src={resolved} title={title} />
}
