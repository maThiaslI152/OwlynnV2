/** Shared attachment helpers for Composer + Knowledge panel drag/drop. */

export const WORKSPACE_REF_DRAG_TYPE = 'application/x-owlynn-workspace-ref'

export interface AttachedFile {
  name: string
  type: string
  data: string
  path?: string
}

export function isWorkspaceRef(file: AttachedFile): boolean {
  return file.type === 'workspace_ref'
}

export function workspaceRefAttachment(filename: string): AttachedFile {
  return {
    name: filename,
    type: 'workspace_ref',
    data: '',
    path: filename,
  }
}

export function toWsFilePayload(file: AttachedFile): Record<string, string> {
  if (isWorkspaceRef(file)) {
    return {
      type: 'workspace_ref',
      name: file.name,
      path: file.path || file.name,
      data: '',
    }
  }
  return {
    name: file.name,
    type: file.type,
    data: file.data,
  }
}
