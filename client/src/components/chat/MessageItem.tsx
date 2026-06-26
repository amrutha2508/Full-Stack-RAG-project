import { ThumbsUp, ThumbsDown, User, Bot } from "lucide-react";
import { useMemo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface Citation {
  filename: string;
  page: number;
}

interface Message {
  id: string;
  content: string;
  role: "user" | "assistant";
  created_at: string;
  chat_id: string;
  clerk_id: string;
  citations?: Citation[];
}

interface MessageItemProps {
  message: Message;
  onFeedback?: (messageId: string, type: "like" | "dislike") => void;
}

type MarkdownBlock = {
  type: "markdown";
  content: string;
};

type TableBlock = {
  type: "table";
  title?: string;
  columns: string[];
  rows: Record<string, any>[];
};

type ImageBlock = {
  type: "image";
  title?: string;
  format?: string;
  encoding?: "base64";
  data: string;
};

type ResponseBlock = MarkdownBlock | TableBlock | ImageBlock;

interface ParsedLLMContent {
  // answer: string;
  blocks: ResponseBlock[];
  citations?: Citation[];
}

export function MessageItem({ message, onFeedback }: MessageItemProps) {
  const isUser = message.role === "user";
  // console.log("Message:", message);

  const time = new Date(message.created_at).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });

  const parsedData = useMemo(() => {
    if (isUser) {
      return {
        isStructured: false,
        textContent: message.content,
        blocks: [] as ResponseBlock[],
        citations: [] as Citation[],
      };
    }

    try {
      const parsed: ParsedLLMContent = JSON.parse(message.content);

      return {
        isStructured: true,
        textContent: "",
        blocks: parsed.blocks || [],
        citations: [...(parsed.citations || []), ...(message.citations || [])],
      };
    } catch {
      return {
        isStructured: false,
        textContent: message.content,
        blocks: [] as ResponseBlock[],
        citations: message.citations || [],
      };
    }
  }, [message.content, message.citations, isUser]);
  console.log("parsedData:", parsedData);

  const renderBlock = (block: ResponseBlock, index: number) => {
    if (block.type === "markdown") {
      return (
        <ReactMarkdown
          key={index}
          remarkPlugins={[remarkGfm]}
          components={{
            p: ({ children }) => (
              <p className="mb-2 last:mb-0 whitespace-pre-wrap leading-relaxed text-sm text-gray-200">
                {children}
              </p>
            ),
            strong: ({ children }) => (
              <strong className="font-semibold text-white">{children}</strong>
            ),
            ul: ({ children }) => (
              <ul className="my-2 ml-5 list-disc space-y-1 text-sm text-gray-200">
                {children}
              </ul>
            ),
            ol: ({ children }) => (
              <ol className="my-2 ml-5 list-decimal space-y-1 text-sm text-gray-200">
                {children}
              </ol>
            ),
            li: ({ children }) => (
              <li className="leading-relaxed">{children}</li>
            ),
            code: ({ children }) => (
              <code className="rounded bg-[#2a2a2a] px-1 py-0.5 text-xs text-gray-100">
                {children}
              </code>
            ),
            h1: ({ children }) => (
              <h1 className="mt-3 mb-2 text-lg font-semibold text-white">
                {children}
              </h1>
            ),
            h2: ({ children }) => (
              <h2 className="mt-3 mb-2 text-base font-semibold text-white">
                {children}
              </h2>
            ),
            h3: ({ children }) => (
              <h3 className="mt-3 mb-2 text-sm font-semibold text-white">
                {children}
              </h3>
            ),
            table: ({ children }) => (
              <div className="my-3 overflow-x-auto rounded-lg border border-gray-700">
                <table className="min-w-full border-collapse text-sm">
                  {children}
                </table>
              </div>
            ),
            thead: ({ children }) => (
              <thead className="bg-[#2a2a2a] text-gray-200">
                {children}
              </thead>
            ),
            th: ({ children }) => (
              <th className="border-b border-gray-700 px-3 py-2 text-left font-semibold whitespace-nowrap">
                {children}
              </th>
            ),
            td: ({ children }) => (
              <td className="border-b border-gray-800 px-3 py-2 text-gray-300 whitespace-nowrap">
                {children}
              </td>
            ),
          }}
        >
          {block.content}
        </ReactMarkdown>
      );
    }

    if (block.type === "table") {
      return (
        <div key={index} className="overflow-x-auto rounded-lg border border-gray-700">
          {block.title && (
            <div className="px-3 py-2 text-sm font-semibold text-gray-200 bg-[#252525] border-b border-gray-700">
              {block.title}
            </div>
          )}

          <table className="min-w-full text-sm text-left">
            <thead className="bg-[#2a2a2a] text-gray-300">
              <tr>
                {block.columns.map((col) => (
                  <th key={col} className="px-3 py-2 border-b border-gray-700 whitespace-nowrap">
                    {col}
                  </th>
                ))}
              </tr>
            </thead>

            <tbody>
              {block.rows.map((row, rowIndex) => (
                <tr key={rowIndex} className="border-b border-gray-800 last:border-b-0">
                  {block.columns.map((col) => (
                    <td key={col} className="px-3 py-2 text-gray-300 whitespace-nowrap">
                      {row[col] === null || row[col] === undefined
                        ? ""
                        : String(row[col])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    }

    if (block.type === "image") {
      const src = `data:image/${block.format || "png"};base64,${block.data}`;

      return (
        <div key={index} className="rounded-lg border border-gray-700 overflow-hidden">
          {block.title && (
            <div className="px-3 py-2 text-sm font-semibold text-gray-200 bg-[#252525] border-b border-gray-700">
              {block.title}
            </div>
          )}
          <img src={src} alt={block.title || "Generated chart"} className="max-w-full" />
        </div>
      );
    }

    return null;
  };

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"} group`}>
      <div className={`max-w-[85%] ${isUser ? "ml-12" : "mr-12"} relative`}>
        <div className="flex items-start gap-3">
          {!isUser && (
            <div className="flex-shrink-0 w-7 h-7 bg-[#252525] border border-gray-700 rounded-lg flex items-center justify-center mt-1">
              <Bot size={14} className="text-gray-400" />
            </div>
          )}

          <div
            className={`rounded-lg p-4 border transition-colors ${
              isUser
                ? "bg-white text-gray-900 border-gray-300"
                : "bg-[#202020] text-gray-200 border-gray-800 hover:border-gray-700"
            }`}
          >
            {parsedData.isStructured && parsedData.blocks.length > 0 ? (
              <div className="flex flex-col gap-4">
                {parsedData.blocks.map(renderBlock)}
              </div>
            ) : (
              <div className={isUser ? "text-sm whitespace-pre-wrap" : "prose prose-invert prose-sm max-w-none"}>
                {isUser ? (
                  parsedData.textContent
                ) : (
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {parsedData.textContent}
                  </ReactMarkdown>
                )}
              </div>
            )}
          </div>

          {isUser && (
            <div className="flex-shrink-0 w-7 h-7 bg-[#252525] border border-gray-700 rounded-lg flex items-center justify-center mt-1">
              <User size={14} className="text-gray-400" />
            </div>
          )}
        </div>

        {!isUser && (
          <div className="absolute -bottom-2 right-10 opacity-0 group-hover:opacity-100 transition-opacity flex items-center gap-1 bg-[#252525] border border-gray-700 rounded-lg p-1">
            <button
              onClick={() => onFeedback?.(message.id, "like")}
              className="p-1.5 hover:bg-[#2a2a2a] rounded-md transition-colors group/btn"
              title="Like this response"
            >
              <ThumbsUp size={12} className="text-gray-400 group-hover/btn:text-gray-300" />
            </button>

            <button
              onClick={() => onFeedback?.(message.id, "dislike")}
              className="p-1.5 hover:bg-[#2a2a2a] rounded-md transition-colors group/btn"
              title="Dislike this response"
            >
              <ThumbsDown size={12} className="text-gray-400 group-hover/btn:text-gray-300" />
            </button>
          </div>
        )}

        <div className={`flex items-center gap-2 mt-2 px-1 ${isUser ? "justify-end" : "justify-start ml-10"}`}>
          <span className="text-xs text-gray-500 opacity-0 group-hover:opacity-100 transition-opacity">
            {time}
          </span>
        </div>
      </div>
    </div>
  );
}