import { visit } from 'unist-util-visit'
import type { Node } from 'unist'

export function remarkDirectiveHtml() {
  return (tree: Node) => {
    visit(tree, (node: any) => {
      if (
        node.type === 'textDirective' ||
        node.type === 'leafDirective' ||
        node.type === 'containerDirective'
      ) {
        const data = node.data || (node.data = {})
        // Render as a custom HTML tag matching the directive name
        // e.g. ::callout will render as <callout>
        data.hName = node.name
        data.hProperties = { ...node.attributes }
      }
    })
  }
}
