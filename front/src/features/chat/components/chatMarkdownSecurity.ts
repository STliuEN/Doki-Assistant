const SAFE_URL = /^(?:https?:|mailto:|tel:|\/|#)/i

/** Keep Markdown links usable while preventing script/data/javascript URL navigation. */
export function safeChatUrlTransform(url: string): string {
  return SAFE_URL.test(url.trim()) ? url : '#'
}
