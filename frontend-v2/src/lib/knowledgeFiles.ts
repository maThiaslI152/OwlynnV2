/** Knowledge panel list helpers — one UI row per indexed source file. */

export interface KnowledgeFileRow {
  name: string
  type: string
  added_at: number
}

export function knowledgeBaseName(name: string): string {
  return name.replace(/#chunk\d+$/, '')
}

export function collapseKnowledgeFiles(files: KnowledgeFileRow[]): KnowledgeFileRow[] {
  const byBase = new Map<string, KnowledgeFileRow>()
  for (const file of files) {
    const base = knowledgeBaseName(file.name)
    const existing = byBase.get(base)
    if (!existing || file.added_at > existing.added_at) {
      byBase.set(base, { ...file, name: base })
    }
  }
  return [...byBase.values()].sort((a, b) => b.added_at - a.added_at)
}
