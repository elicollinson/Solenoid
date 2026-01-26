declare module 'marked-terminal' {
  interface TerminalRendererOptions {
    code?: (code: string, infostring?: string) => string;
    blockquote?: (quote: string) => string;
    html?: (html: string) => string;
    heading?: (text: string, level: number) => string;
    hr?: () => string;
    list?: (body: string, ordered: boolean, start: number) => string;
    listitem?: (text: string, task: boolean, checked: boolean) => string;
    checkbox?: (checked: boolean) => string;
    paragraph?: (text: string) => string;
    table?: (header: string, body: string) => string;
    tablerow?: (content: string) => string;
    tablecell?: (content: string, flags: { header: boolean; align: string | null }) => string;
    strong?: (text: string) => string;
    em?: (text: string) => string;
    codespan?: (text: string) => string;
    br?: () => string;
    del?: (text: string) => string;
    link?: (href: string | null, title: string | null, text: string) => string;
    image?: (href: string | null, title: string | null, text: string) => string;
    text?: (text: string) => string;
    reflowText?: boolean;
    width?: number;
  }

  class TerminalRenderer {
    constructor(options?: TerminalRendererOptions);
  }

  export default TerminalRenderer;
}
