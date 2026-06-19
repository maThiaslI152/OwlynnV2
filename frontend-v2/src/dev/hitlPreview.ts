/**
 * Dev-only HITL preview helpers.
 *
 * Imports fixture JSON payloads and exposes a function to inject synthetic
 * HITL prompts into the frontend without backend interaction.
 *
 * Gated by `import.meta.env.DEV` — production builds omit this module.
 */

import type { InterruptEvent } from '../types/protocol'

type HitlVariant =
  | 'router'
  | 'security'
  | 'plan_review'
  | 'scope_clarify'
  | 'ask_user'

interface DevHitlPreview {
  variant: HitlVariant
  event: InterruptEvent
  label: string
}

const DEV_HITL_PREVIEWS: DevHitlPreview[] = [
  {
    variant: 'router',
    event: {
      type: 'interrupt',
      interrupts: [
        {
          type: 'ask_user',
          question: "I'm not sure which approach fits best — multiple matching skills found\nWhich would help you most?",
          choices: [
            { label: 'Web Development — Build and debug web applications (87%)', route: 'complex-cloud', toolbox: ['file_ops', 'web_search'], skill_name: 'web_development' },
            { label: 'Data Analysis — Analyze and visualize datasets (72%)', route: 'complex-cloud', toolbox: ['data_viz', 'file_ops'], skill_name: 'data_analysis' },
            { label: 'Others (describe what you need)', route: 'complex-cloud', toolbox: ['all'], skill_name: null, allows_user_input: true },
          ],
          clarification_reason: 'Multiple skills matched with similar confidence scores.',
        },
      ],
    },
    label: 'Router — Skill Ambiguity',
  },
  {
    variant: 'security',
    event: {
      type: 'interrupt',
      interrupts: [
        {
          type: 'security_approval_required',
          title: 'Sensitive tool request blocked pending approval',
          reason: 'One or more tool calls are marked sensitive by policy.',
          sensitive_tool_calls: [
            {
              name: 'delete_workspace_file',
              args: { path: '/workspace/important_data.csv' },
              risk_category: 'destructive_action',
              risk_label: 'destructive_action',
              risk_confidence: 0.98,
              risk_rationale: 'Policy detected delete/drop semantics that can irreversibly modify workspace state.',
              remediation_hint: 'Confirm target paths and create a backup/snapshot before execution.',
            },
          ],
          safe_tool_calls: [],
          risk_categories: ['destructive_action'],
          tool_name: 'delete_workspace_file',
          tool_args: '{"path": "/workspace/important_data.csv"}',
          sensitive_count: 1,
          risk_label: 'destructive_action',
          risk_confidence: 0.98,
          risk_rationale: 'Policy detected delete/drop semantics.',
          remediation_hint: 'Confirm target paths and create a backup/snapshot before execution.',
          conversation_snippet: 'User: Can you clean up unused data files?\nOwlynn: I\'ll identify and remove files that are no longer referenced.',
        },
      ],
    },
    label: 'Security — Delete File',
  },
  {
    variant: 'plan_review',
    event: {
      type: 'interrupt',
      interrupts: [
        {
          type: 'plan_review_required',
          title: 'Plan review — sensitive file operations ahead',
          stated_intent: 'Owlynn wants to write a new Python script to the workspace and execute it.',
          conversation_snippet: 'User: Write a script that processes all CSV files.\nOwlynn: I\'ll create a Python script that reads all CSV files.',
          planned_actions: [
            { tool: 'write_workspace_file', summary: 'Create process_csvs.py with data processing logic' },
            { tool: 'shell_run', summary: 'Execute process_csvs.py to generate report' },
          ],
          pitfalls: [
            'The script will read all CSV files including potentially large ones — memory usage may spike.',
            'Writing and executing files in the workspace could overwrite existing scripts.',
          ],
          sensitive_tool_calls: [
            {
              name: 'write_workspace_file',
              args: { path: '/workspace/process_csvs.py', content: '...' },
              risk_category: 'sensitive_tool_execution',
              risk_label: 'sensitive_tool_execution',
              risk_confidence: 0.8,
            },
          ],
        },
      ],
    },
    label: 'Plan Review — Write File',
  },
  {
    variant: 'scope_clarify',
    event: {
      type: 'interrupt',
      interrupts: [
        {
          type: 'scope_clarification_required',
          task_summary: 'Build a calculator application',
          questions: [
            {
              id: 'language',
              question: 'Which language or runtime should I use?',
              choices: [
                { label: 'Python' },
                { label: 'JavaScript / TypeScript' },
                { label: 'Rust' },
                { label: 'No preference — recommend one', allows_user_input: false },
              ],
              allows_user_input: true,
            },
            {
              id: 'ui_surface',
              question: 'What kind of interface should the calculator have?',
              choices: [
                { label: 'Web GUI' },
                { label: 'Desktop GUI' },
                { label: 'CLI (command line)' },
                { label: 'TUI (terminal interface)' },
              ],
              allows_user_input: true,
            },
            {
              id: 'feature_scope',
              question: 'What feature scope do you need?',
              choices: [
                { label: 'Basic (+ - × ÷)' },
                { label: 'Scientific (sin, cos, log, etc.)' },
                { label: 'With history/memory' },
                { label: 'No preference — keep it simple' },
              ],
              allows_user_input: false,
            },
          ],
          pitfalls: [
            'Choosing a GUI framework without knowing desktop vs web wastes a full implementation pass.',
          ],
          conversation_snippet: 'User: Can you build a calculator app?\nOwlynn: I\'ll help you build a calculator application.',
        },
      ],
    },
    label: 'Scope Clarification — Calculator',
  },
  {
    variant: 'ask_user',
    event: {
      type: 'interrupt',
      interrupts: [
        {
          type: 'ask_user',
          question: 'Which format should I use for the output report?',
          choices: [
            { label: 'PDF' },
            { label: 'Word' },
            { label: 'Markdown' },
          ],
          conversation_snippet: 'User: Generate a summary report of the sales data.\nOwlynn: I\'ll analyze the sales data.',
        },
      ],
    },
    label: 'Ask User — Mid-task',
  },
]

export function getDevHitlPreviews(): DevHitlPreview[] {
  return DEV_HITL_PREVIEWS
}

export function getDevHitlPreview(variant: HitlVariant): DevHitlPreview | undefined {
  return DEV_HITL_PREVIEWS.find((p) => p.variant === variant)
}
