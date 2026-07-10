import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist', 'dist-build-check']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      globals: {
        ...globals.browser,
        ...globals.vitest,
      },
    },
  },
  {
    // These existing components synchronize API-backed or editable state in effects.
    // Keep the rule enabled for new files while they are migrated incrementally.
    files: [
      'src/components/common/AuthImage.tsx',
      'src/components/knowledge/DocumentDetailDrawer.tsx',
      'src/components/note/CategoryManageDialog.tsx',
      'src/components/note/RelatedFragments.tsx',
      'src/pages/AIChat.tsx',
      'src/pages/KnowledgeBase.tsx',
      'src/pages/MemoryCenter.tsx',
      'src/pages/ModelSettings.tsx',
      'src/pages/NoteEditor.tsx',
      'src/pages/NoteList.tsx',
      'src/pages/Profile.tsx',
      'src/pages/SkillManager.tsx',
      'src/pages/ToolManager.tsx',
    ],
    rules: {
      'react-hooks/set-state-in-effect': 'off',
    },
  },
  {
    files: ['src/router/index.tsx'],
    rules: {
      'react-refresh/only-export-components': 'off',
    },
  },
])
