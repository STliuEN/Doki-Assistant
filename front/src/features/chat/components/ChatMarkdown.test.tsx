import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ChatMarkdown } from './ChatMarkdown'
import { safeChatUrlTransform } from './chatMarkdownSecurity'

describe('ChatMarkdown', () => {
  it('renders normal Markdown while treating raw HTML as text', () => {
    const unsafeHtml = '<img src="x" onerror="window.__xss = true"><iframe src="https://attacker.test"></iframe><script>alert("xss")</script>'
    const { container } = render(
      <ChatMarkdown>{`# Title\n\n**bold**\n\n${unsafeHtml}`}</ChatMarkdown>,
    )

    expect(screen.getByRole('heading', { name: 'Title' })).toBeTruthy()
    expect(screen.getByText('bold')).toBeTruthy()
    expect(container.querySelector('img')).toBeNull()
    expect(container.querySelector('iframe')).toBeNull()
    expect(container.querySelector('script')).toBeNull()
    expect(container.textContent).toContain(unsafeHtml)
  })

  it('rewrites unsafe URL protocols before creating links', () => {
    const { container } = render(
      <ChatMarkdown>[safe](https://example.com) [unsafe](javascript:alert(1))</ChatMarkdown>,
    )

    const links = [...container.querySelectorAll('a')]
    expect(links).toHaveLength(2)
    expect(links[0].getAttribute('href')).toBe('https://example.com')
    expect(links[1].getAttribute('href')).toBe('#')
  })

  it('keeps the same renderer contract for empty streaming content', () => {
    const { container } = render(<ChatMarkdown>{''}</ChatMarkdown>)

    expect(container.textContent).toBe('')
  })
})

describe('safeChatUrlTransform', () => {
  it.each([
    'https://example.com',
    'mailto:test@example.com',
    'tel:+886900000000',
    '/notes/1',
    '#section',
  ])('allows safe URL %s', (url) => {
    expect(safeChatUrlTransform(url)).toBe(url)
  })

  it.each(['javascript:alert(1)', 'data:text/html,<script>alert(1)</script>', 'vbscript:msgbox(1)'])(
    'blocks unsafe URL %s',
    (url) => {
      expect(safeChatUrlTransform(url)).toBe('#')
    },
  )
})
