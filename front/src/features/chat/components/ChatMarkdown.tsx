import ReactMarkdown from 'react-markdown'
import rehypeHighlight from 'rehype-highlight'
import { safeChatUrlTransform } from './chatMarkdownSecurity'

type ChatMarkdownProps = {
  children: string
}

export function ChatMarkdown({ children }: ChatMarkdownProps) {
  return (
    <ReactMarkdown
      rehypePlugins={[rehypeHighlight]}
      urlTransform={safeChatUrlTransform}
    >
      {children}
    </ReactMarkdown>
  )
}
